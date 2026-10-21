"""Windowless engine session: the Mod Editor's engine without IntegrationStudio, driven over ConsoleTre.

library/headless-bench.md explains use, evidence and the first live run.  Stage 2 of the headless
editor: ``EngineSession`` builds the engine command line the editor itself uses for its viewport
engine (enableWindow false, --editor, a ConsoleTre channel), gives each run a private root with its
own mod folders, hosts the ConsoleTre hub, launches the engine through ``quiet.start`` (private
desktop, below-normal priority, job kill), waits for the engine's Automation/ExecSsl listener and
runs SSL through it (``exec_ssl``, ``screenshot``), and stops the whole tree with a wall-clock limit.

**Hub: design B.**  The hub is a small .NET 8 helper (integrations/consoletre-hub) that hosts the
SDK's own ``Saber.ConsoleTre.Server.ConsoleServer`` - what IntegrationStudio runs for
``AutoStartConsoleTre = Host`` - and talks to the engine with the SDK's ``ConsoleClient``, exactly the
calls of the proven ExecSsl scripts (integrations/physics-bench/*.ps1; 765 replies in the D11 RC3
bench).  The SDK assemblies are loaded from the SDK folder at run time and never copied.  Python
speaks JSON lines to the helper over stdin/stdout; the helper runs under ``quiet.start`` too.
A pure-Python hub (design A) would re-implement framing, SyncTime, pings, passport matching and
routing from the decompile; every one of those is a place to differ from what the engine was tested
against, so B reproduces the editor with the least guesswork.  The Python codec in
tests/fake_engine.py exercises the real hub from the engine's side.

**Gates.**  ``EngineSession.start`` refuses unless ``owner_approved`` is a non-empty reason (the owner
approves each engine run), refuses while the game, the Mod Editor, its engine or another ConsoleTre
hub runs, and never writes into the owner's mod folders or the game folder.  Grades follow
library/README.md: SDK = read in the decompiled SDK (IntegrationStudio, Saber.ConsoleTre) or the
shipped editor.cfg, Build = observed in our own runs or tests, Inferred = expected from static
analysis of the engine but not yet run.
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from . import audio_mute, project_context, quiet

ENGINE_EXE = "Roadcraft ModEditor.exe"
HUB_PORT = 20563                   # ConsoleServer.DefaultServerPort; the engine has no port setting (Inferred)
DISCOVERY_PORT = 20663             # CONSOLE_IPDISCOVERY<port> datagrams (ClientDiscovery.cs)
EDITOR_CFG = "../../config/editor/editor.cfg"
WORKSPACE = "RoadBuilder"          # .project project-name, the ExecSsl listener's Workspace (Code)
# Process names that must not run while a windowless engine starts (substring, case-insensitive).
GUARDED_PROCESSES = ("roadcraft modeditor", "roadcraft - retail", "integrationstudio", "s3dconsoletreserver")
DEFAULT_GAME_ROOT = Path(r"C:\Program Files (x86)\Steam\steamapps\common\RoadCraft")
HUB_DIR = Path(__file__).resolve().parents[2] / "integrations" / "consoletre-hub"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_IEND = b"\x00\x00\x00\x00IEND\xaeB`\x82"


class EngineError(RuntimeError):
    """The engine session failed (launch, hub, transport)."""


class EngineRefused(EngineError):
    """A gate refused to start the engine (no approval, something already running, unsafe folder)."""


class EngineTimeout(EngineError):
    """No reply within the timeout."""


# ------------------------------------------------------------------ command line
@dataclass(frozen=True)
class EngineSet:
    """One ``--set /<root>/<path> <value>`` (root Config or DbgVars) with its evidence grade and reason."""
    path: str
    value: str
    grade: str
    why: str
    root: str = "Config"

    def argv(self) -> list[str]:
        return ["--set", f"/{self.root}/{self.path}", self.value]


# The user's RC3 bench project ran play mode with this DbgVar in its xgine-arguments (.project:
# --set "/DbgVars/Game/Startup/Start at truck on scene" true); the game's start state then calls
# StartAtExistingTruck -> TruckManagerRb.SetCurrent(start truck) instead of the spawn/garage/eagle flow
# (ssl main/game_session/game_context_fsm_state_start.ssc Enter).  scene_play.md step 0.
START_AT_TRUCK_ON_SCENE = EngineSet("Game/Startup/Start at truck on scene", "true", "SDK",
                                    "play mode starts at the scene's (setAsStartTruck) truck: RC3 bench .project "
                                    "xgine-arguments; game_context_fsm_state_start.ssc", root="DbgVars")


def standard_sets(*, channel: int, adapter_id: int, width: int, height: int) -> list[EngineSet]:
    """The fixed settings, in the order the editor emits its own (EngineViewportProcessStarter) then ours."""
    return [
        EngineSet("Video/WindowSizeY", str(height), "SDK",
                  "editor passes the viewport size (EngineViewportProcessStarter.GetProcessStartInfo, min 64)"),
        EngineSet("Video/WindowSizeX", str(width), "SDK", "as above; gives the windowless main viewport a real size"),
        EngineSet("Debug/ConsoleChannel", str(channel), "SDK",
                  "ConsoleTre channel the engine joins ('Channel <n>'); the editor passes its own PID"),
        EngineSet("CONFIG/enableWindow", "false", "SDK",
                  "the editor's windowless mode: renders off-screen, every window/focus call is gated on it "
                  "(focus_dialogs_native.md)"),
    ]


def tail_sets(*, adapter_id: int) -> list[EngineSet]:
    return [
        EngineSet("Video/API", "dx12", "SDK", "GenerateConfigFromGraphicsAPI (profile EngineGraphicsAPI Direct3D12)"),
        EngineSet("Video/AdapterId", str(adapter_id), "SDK", "GenerateConfigFromGraphicsAPI; pick the discrete GPU"),
        EngineSet("Video/WindowMode", "windowed", "Inferred",
                  "avoids SetWindowLongA(WS_POPUP|WS_VISIBLE) in non-windowed mode (0x1433e4530); 'windowed' is an "
                  "exe string, editor.cfg uses 'borderless'"),
        EngineSet("Debug/ErrorToConsoleOnly", "true", "Inferred",
                  "selects the non-UI error handler instead of the assert dialog (0x143be5ff4); used instead of "
                  "AutomationMode, which installs an extra Automation/EventFailure reporter"),
        EngineSet("VideoDriverVersionWarning/Show", "false", "Inferred", "outdated-driver TaskDialog (key in editor.cfg)"),
        EngineSet("Video/LowCpuMemoryWarning/Ignored", "true", "Inferred", "page-file TaskDialog (key in editor.cfg)"),
        EngineSet("Streaming/LowCpuMemoryWarning/Enabled", "false", "Inferred", "second switch of the same warning"),
        EngineSet("Input/ClipCursorDisabled", "true", "Inferred", "never clip the owner's cursor (key in editor.cfg)"),
        EngineSet("Asserts/IntegrationStudio/RunAutomaticallyOnError", "false", "Inferred",
                  "no 'Awaiting Integration Studio command' TOPMOST dialog on an SSL error"),
    ]


def mod_sets(layout: "RunLayout") -> list[EngineSet]:
    return [
        EngineSet("ResourceManager/ModDirs/local", layout.mods.as_posix(), "Inferred",
                  "installed-mod folder (editor.cfg local: ..\\../mods = the owner's root\\mods); per-run copy "
                  "holds only the candidate pak (physics_semantics.md Q-d: --set on a dictionary key untested)"),
        EngineSet("ResourceManager/ModDirs/pros", layout.mods_pros.as_posix(), "Inferred",
                  "second mod folder (<sandbox>/mods); emptied so no other mod loads"),
        EngineSet("external/ModsSourceLocal", layout.mods_source.as_posix(), "Inferred",
                  "FileSystem TagLayer $(external.ModsSourceLocal) (editor.cfg, Code); empty, or the private "
                  "project copy for the project-copy strategy"),
    ]


def timestep_sets(timestep: float | None) -> list[EngineSet]:
    if not timestep:
        return []
    fps = f"{1.0 / timestep:.6g}"
    return [EngineSet("EDITOR/FPS/FIXED/editorFixedFpsValue", fps, "Inferred",
                      "fixed frame rate in editor mode (editor.cfg EDITOR.FPS.FIXED, default 0 = variable)"),
            EngineSet("EDITOR/FPS/FIXED/playModeFixedFpsValue", fps, "Inferred",
                      "fixed frame rate in play mode (editor.cfg default 30)")]


def build_command(exe: str | Path, *, channel: int, layout: "RunLayout", adapter_id: int = 0,
                  width: int = 1280, height: int = 720, timestep: float | None = None, level: str | None = None,
                  extra_sets: Iterable[EngineSet] = ()) -> tuple[list[str], list[EngineSet]]:
    """argv for the windowless engine and the graded settings it carries.

    Order as the editor builds it: ``--startup`` then its inserts (size, channel, ``enableWindow false
    --editor``), ``--cfg`` and the graphics API, then ours.  ``--dont_send_crashdump`` and
    ``--crashdump_directory`` are engine argv names mapped to ShowErrors.* (Code: option table; the
    two-token form is Inferred).
    """
    head = standard_sets(channel=channel, adapter_id=adapter_id, width=width, height=height)
    tail = tail_sets(adapter_id=adapter_id) + mod_sets(layout) + timestep_sets(timestep)
    if level:
        tail.append(EngineSet("Level/File", level, "Inferred", "level loaded at start (CFG Level.File, argv --level)"))
    tail += list(extra_sets)
    argv = [str(exe), "--startup"]
    for s in head[:3]:
        argv += s.argv()
    argv += head[3].argv() + ["--editor", "--cfg", str(layout.cfg) if layout.cfg else EDITOR_CFG]
    for s in tail:
        argv += s.argv()
    argv += ["--dont_send_crashdump", "--crashdump_directory", str(layout.crash)]
    return argv, head + tail


# ------------------------------------------------------------------ per-run root
@dataclass
class RunLayout:
    root: Path
    strategy: str
    mods: Path
    mods_pros: Path
    mods_source: Path
    crash: Path
    logs: Path
    shots: Path
    pak: Path | None = None
    copied: list[str] = field(default_factory=list)
    cfg: Path | None = None   # private editor.cfg (project-copy): references the game's, overrides `external`

    def as_json(self) -> dict[str, Any]:
        return {"root": str(self.root), "strategy": self.strategy, "mods": str(self.mods),
                "modsPros": str(self.mods_pros), "modsSource": str(self.mods_source), "crash": str(self.crash),
                "logs": str(self.logs), "shots": str(self.shots), "pak": str(self.pak) if self.pak else None,
                "copied": self.copied, "cfg": str(self.cfg) if self.cfg else None}


STRATEGIES = ("moddirs", "project-copy")


def live_mod_folders(game_root: str | Path | None = None) -> list[Path]:
    """Folders the bench must never write into: the owner's installed mods and live mods_source."""
    game = Path(game_root) if game_root else project_context.game_root()
    home = Path.home()
    rows = [game / "root" / "mods", game / "root" / "mods_source", game]
    for docs in (home / "OneDrive" / "Documents", home / "Documents"):
        rows.append(docs / "Saber" / "IntegrationStudio" / "mods_source")
    return rows


def _inside(path: Path, folder: Path) -> bool:
    try:
        path.resolve().relative_to(folder.resolve())
        return True
    except ValueError:
        return False


def check_run_root(root: str | Path, game_root: str | Path | None = None) -> Path:
    root = Path(root)
    if not root.is_absolute():
        raise EngineRefused(f"run folder must be absolute: {root}")
    for folder in live_mod_folders(game_root):
        if _inside(root, folder) or _inside(folder, root):
            raise EngineRefused(f"run folder {root} overlaps {folder} (owner's game or mod folder)")
    return root


def plan_layout(root: str | Path, *, strategy: str = "moddirs", pak: str | Path | None = None,
                game_root: str | Path | None = None) -> RunLayout:
    """Where a run's private folders go (nothing is written)."""
    if strategy not in STRATEGIES:
        raise EngineError(f"strategy must be one of {STRATEGIES}")
    root = check_run_root(root, game_root)
    pak = Path(pak) if pak else None
    return RunLayout(root=root, strategy=strategy, mods=root / "mods", mods_pros=root / "mods_pros",
                     mods_source=root / "mods_source", crash=root / "crash", logs=root / "logs", shots=root / "shots",
                     pak=(root / "mods" / pak.name) if pak else None,
                     cfg=(root / "config" / "editor.cfg") if strategy == "project-copy" else None)


def private_cfg_text(layout: "RunLayout", game_root: str | Path | None = None) -> str:
    """The run's editor.cfg for the project-copy strategy, in the form of the RC3 bench project's
    config/editor.cfg (``references: - user_documents: <game editor.cfg>`` + ``external``).  That file is
    what made IntegrationStudio's engine mount the bench mods_source (its engine log lists the project's
    mods_source as a FileSystem layer root); ``--set /Config/external/ModsSourceLocal`` did not change
    the layer in smoke_003 (engine.log still shows the game's ../../mods_source).  scene_play.md step 0."""
    game = Path(game_root) if game_root else project_context.game_root()
    base = (game / "root" / "config" / "editor" / "editor.cfg").as_posix()
    return ("references:\n"
            f"- user_documents: {base}\n"
            "external:\n"
            f"  ModsSourceLocal: {layout.mods_source.as_posix()}\n"
            f"  ProjectPath: {(game / 'root' / '.project').as_posix()}\n")


def _link_or_copy2(src: str, dst: str) -> str:
    """copytree copy_function: a hard link where the volume allows, else a copy."""
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)
    return dst


def prepare_layout(layout: RunLayout, *, pak: str | Path | None = None, project: str | Path | None = None,
                   game_root: str | Path | None = None, link: bool = False) -> RunLayout:
    """Create the private folders.  ``moddirs``: the candidate pak alone in ``mods``; ``project-copy``:
    a copy of the project's ``mods_source`` (as physics_bench.init_bench) with no pak; ``link`` makes that
    copy of hard links (the bench unlinks a file before it edits it: the spawn scene).  The source pak
    and project are only read."""
    if layout.root.exists() and any(layout.root.iterdir()):
        raise EngineError(f"run folder {layout.root} is not empty")
    for folder in (layout.mods, layout.mods_pros, layout.crash, layout.logs, layout.shots):
        folder.mkdir(parents=True, exist_ok=True)
    if layout.strategy == "moddirs":
        layout.mods_source.mkdir(parents=True, exist_ok=True)
        if pak is None:  # a smoke run: no mod at all
            return layout
        pak = Path(pak)
        if not pak.is_file() or pak.suffix.lower() != ".pak":
            raise EngineError(f"not a .pak file: {pak}")
        shutil.copy2(pak, layout.mods / pak.name)
        layout.pak = layout.mods / pak.name
        layout.copied.append(str(pak))
    else:
        if project is None:
            raise EngineError("the project-copy strategy needs --project (folder holding mods_source)")
        source = Path(project) / "mods_source"
        if not source.is_dir():
            raise EngineError(f"no mods_source in {project}")
        shutil.copytree(source, layout.mods_source, copy_function=_link_or_copy2 if link else shutil.copy2)
        layout.copied.append(str(source))
        if layout.cfg:
            layout.cfg.parent.mkdir(parents=True, exist_ok=True)
            layout.cfg.write_text(private_cfg_text(layout, game_root), encoding="utf-8")
    return layout


# ------------------------------------------------------------------ gates
def running_guarded_processes() -> tuple[list[dict[str, Any]], str | None]:
    """Game/editor/engine/hub processes now running ([] and an error text when inspection fails)."""
    from .core import _editor_processes
    return _editor_processes(tokens=GUARDED_PROCESSES)


def port_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
        except OSError:
            return False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:  # an editor hub listens on 0.0.0.0
        s.settimeout(0.3)
        return s.connect_ex((host, port)) != 0


def check_gates(owner_approved: str | None, *, process_check: Callable[[], tuple[list, str | None]],
                hub_port: int) -> dict[str, Any]:
    if not isinstance(owner_approved, str) or not owner_approved.strip():
        raise EngineRefused("engine runs need the owner's go-ahead: pass owner_approved='<who/when/why>' "
                            "(CLI: --owner-approved \"<text>\")")
    found, error = process_check()
    if error:
        raise EngineRefused(f"cannot inspect running processes, refusing to start: {error}")
    if found:
        names = ", ".join(f"{row['name']} ({row['pid']})" for row in found)
        raise EngineRefused(f"refusing to start while the game, editor or an engine runs: {names}")
    if not port_free(hub_port):
        raise EngineRefused(f"port {hub_port} is in use (another ConsoleTre hub, e.g. a running editor)")
    return {"ownerApproved": owner_approved.strip(), "processesChecked": True, "hubPort": hub_port}


# ------------------------------------------------------------------ PNG
def png_complete(path: str | Path) -> bool:
    try:
        data = Path(path).read_bytes()
    except OSError:
        return False
    return len(data) > len(PNG_SIGNATURE) + len(PNG_IEND) and data.startswith(PNG_SIGNATURE) and data.endswith(PNG_IEND)


def wait_png(path: str | Path, timeout: float = 20.0, poll: float = 0.25) -> dict[str, Any]:
    """SaveScreenshot is asynchronous: wait for signature, IEND and a size stable over two polls."""
    path = Path(path)
    deadline = time.monotonic() + timeout
    last = -1
    while time.monotonic() < deadline:
        size = path.stat().st_size if path.exists() else -1
        if size > 0 and size == last and png_complete(path):
            return {"path": str(path), "bytes": size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        last = size
        time.sleep(poll)
    raise EngineTimeout(f"no complete PNG at {path} within {timeout:.0f} s")


def ssl_string(text: str) -> str:
    if any(c in text for c in '"\\\n\r') or not text.isprintable():
        raise EngineError(f"refusing to quote {text!r} into SSL")
    return f'"{text}"'


def screenshot_script(path: str | Path, hud: bool = False) -> str:
    """SaveScreenshot to an absolute path (prior_notes.md: absolute paths work; bare names land in bin/pc).

    The engine appends the format's extension itself (scene_001 2026-10-13: ``scene.png`` was written as
    ``scene.png.png``), so the name is passed without its ``.png``."""
    path = Path(path)
    if not path.is_absolute():
        raise EngineError("screenshots need an absolute path (a bare name lands in the game's bin/pc)")
    stem = path.with_suffix("") if path.suffix.lower() == ".png" else path
    return (f"SaveScreenshot(ScreenshotSaveTarget.FILE,{ssl_string(stem.as_posix())},"
            f"{'true' if hud else 'false'},ScreenshotFormat.PNG)")


# ------------------------------------------------------------------ hub helper
def default_sdk_editor_dir(game_root: str | Path | None = None) -> Path:
    return (Path(game_root) if game_root else project_context.game_root()) / "tools" / "bin" / "ModEditor"


def hub_cache_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".cache")
    return Path(base) / "roadcraft-toolchain" / "consoletre-hub"


def hub_build_key(sdk_editor_dir: str | Path) -> str:
    digest = hashlib.sha256()
    for name in ("ConsoleTreHub.csproj", "Program.cs"):
        digest.update((HUB_DIR / name).read_bytes())
    for name in ("Saber.ConsoleTre.dll", "Saber.Json.dll"):
        dll = Path(sdk_editor_dir) / name
        digest.update(dll.read_bytes() if dll.is_file() else b"missing")
    return digest.hexdigest()[:16]


def hub_build_command(sdk_editor_dir: str | Path, output: str | Path) -> list[str]:
    return ["dotnet", "build", str(HUB_DIR / "ConsoleTreHub.csproj"), "-c", "Release", "-nologo",
            "-nodeReuse:false", "-p:UseSharedCompilation=false", f"-p:RoadCraftSdkEditorDir={sdk_editor_dir}",
            "-o", str(output)]


def hub_executable(output: str | Path) -> Path:
    name = "roadcraft-consoletre-hub.exe" if sys.platform == "win32" else "roadcraft-consoletre-hub"
    return Path(output) / name


def build_hub(sdk_editor_dir: str | Path, *, timeout: float = 300) -> Path:
    """Build the helper once per (source, SDK DLL) pair into the per-user cache; quietly."""
    sdk_editor_dir = Path(sdk_editor_dir)
    for dll in ("Saber.ConsoleTre.dll", "Saber.Json.dll"):
        if not (sdk_editor_dir / dll).is_file():
            raise EngineError(f"{dll} not found in {sdk_editor_dir}")
    if shutil.which("dotnet") is None:
        raise EngineError("the .NET 8 SDK (dotnet) is needed to build the ConsoleTre hub helper")
    output = hub_cache_dir() / hub_build_key(sdk_editor_dir)
    exe = hub_executable(output)
    if exe.is_file():
        return exe
    result = quiet.run(hub_build_command(sdk_editor_dir, output), cwd=HUB_DIR, timeout=timeout, desktop="private")
    if result.returncode != 0 or not exe.is_file():
        tail = (result.stdout or "")[-2000:] + (result.stderr or "")[-1000:]
        raise EngineError(f"hub helper build failed (exit {result.returncode}):\n{tail}")
    for dll in ("Saber.ConsoleTre.dll", "Saber.Json.dll"):  # the helper must load the SDK's copies
        if (output / dll).exists():
            raise EngineError(f"{dll} was copied into the helper output; refusing to use it")
    return exe


def hub_command(exe: str | Path, sdk_editor_dir: str | Path, *, port: int, discovery: bool) -> list[str]:
    return [str(exe), "--sdk", str(sdk_editor_dir), "--port", str(port), "--bind", "127.0.0.1",
            "--discovery", "127.0.0.1" if discovery else "none"]


class HubClient:
    """JSON-lines client of the hub helper (one request at a time)."""

    def __init__(self, argv: Sequence[str], *, log: Path | None = None, cwd: str | Path | None = None):
        self.argv = list(argv)
        self._log_file = open(log, "ab") if log else None
        self.process = quiet.start(self.argv, cwd=cwd, desktop="private", priority="below_normal", pipes=True,
                                   log=self._log_file, capture=self._log_file is None)
        self.events: list[dict[str, Any]] = []
        self._responses: "queue.Queue[dict[str, Any]]" = queue.Queue()
        self._event_cv = threading.Condition()
        self._next_id = 0
        self._lock = threading.Lock()
        self._closed = False
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _read(self) -> None:
        stream = self.process.stdout
        buffer = b""
        try:
            while True:
                chunk = stream.read(65536)
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line.decode("utf-8"))
                    except ValueError:
                        row = {"event": "garbage", "text": line[:200].decode("utf-8", "replace")}
                    if "event" in row:
                        with self._event_cv:
                            self.events.append(row)
                            self._event_cv.notify_all()
                    else:
                        self._responses.put(row)
        except (OSError, ValueError):
            pass
        with self._event_cv:
            self.events.append({"event": "eof"})
            self._event_cv.notify_all()

    def wait_event(self, predicate: Callable[[dict[str, Any]], bool], timeout: float,
                   start: int = 0) -> dict[str, Any] | None:
        """First event from index ``start`` on that satisfies ``predicate`` (None on timeout or EOF)."""
        deadline = time.monotonic() + timeout
        seen = start
        with self._event_cv:
            while True:
                for row in self.events[seen:]:
                    if predicate(row):
                        return row
                seen = len(self.events)
                if any(r.get("event") == "eof" for r in self.events):
                    return None
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._event_cv.wait(min(remaining, 0.25))

    def request(self, op: str, *, wait: float = 30.0, **params) -> dict[str, Any]:
        with self._lock:
            if self._closed:
                raise EngineError("hub helper is closed")
            self._next_id += 1
            rid = self._next_id
            line = json.dumps({"id": rid, "op": op, **params}) + "\n"
            try:
                self.process.stdin.write(line.encode("utf-8"))
                self.process.stdin.flush()
            except (OSError, ValueError) as exc:
                raise EngineError(f"hub helper is gone: {exc}") from exc
            deadline = time.monotonic() + wait
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise EngineTimeout(f"hub helper did not answer {op} within {wait:.0f} s")
                try:
                    row = self._responses.get(timeout=min(remaining, 0.5))
                except queue.Empty:
                    if self.process.poll() is not None:
                        raise EngineError(f"hub helper exited ({self.process.poll()}) during {op}")
                    continue
                if row.get("id") == rid:
                    return row

    def close(self) -> None:
        if self._closed:
            return
        try:
            self.request("close", wait=5)
        except EngineError:
            pass
        self._closed = True
        try:
            self.process.wait(5)
        except subprocess.TimeoutExpired:
            pass
        self.process.kill()
        self.process.close()
        if self._log_file:
            self._log_file.close()


# ------------------------------------------------------------------ IntegrationStudio "Game editor" messages
# C:\RC_RE\research\scene_play.md has the recipe and the grades.  A message is (name, fields); each field
# is (type, value) with type str|int|bool|float, serialised by the hub helper as TreEngineMessage does
# (NativeWriter: string = int32 byte length + UTF-8 without NUL, bool = 1 byte, int/float = 4 bytes LE).
GAME_EDITOR = "Game editor"     # GameEditor.CreateConnector (XginePlugin GameEditor.cs:260), protocol 1
DEFAULT_SERVER_ADDRESS = "localhost"   # GameEditor.LoadState default "server-addr"
FIELD_TYPES = ("str", "int", "bool", "float")
Field = tuple[str, Any]
Message = tuple[str, list[Field]]


@dataclass(frozen=True)
class SceneLoadData:
    """XgineViewportSceneLoadData for a scene file: SceneName = file name (ClassDocumentSource.Name),
    SceneData = the scene PS, ResTag = res:// + path of ``<scene>.resource`` relative to its mods_source
    layer, lower case (ResourceTag.MakeFrom), Resource = the ``.resource`` text (ResourceInstance.SaveToString
    of the unmodified file's database entry)."""
    name: str
    ps: str
    res_tag: str
    resource: str
    path: str

    def as_json(self) -> dict[str, Any]:
        return {"name": self.name, "resTag": self.res_tag, "path": self.path,
                "psBytes": len(self.ps.encode("utf-8")), "resourceBytes": len(self.resource.encode("utf-8")),
                "psSha256": hashlib.sha256(self.ps.encode("utf-8")).hexdigest()}


def scene_load_data(scene: str | Path, mods_source: str | Path, *, ps: str = "file") -> SceneLoadData:
    """``scene`` is a .scn path relative to ``mods_source`` (as in a .mod file: xscenes/mods/<x>/<x>.scn) or
    absolute inside it.  ``ps``: "file" sends the scene text as the editor does (it sends the whole
    document as psOverrides), "empty" sends "" (XgineSceneLoader then passes no override)."""
    if ps not in ("file", "empty"):
        raise EngineError("scene ps must be 'file' or 'empty'")
    root = Path(mods_source).resolve()
    path = Path(scene)
    path = (path if path.is_absolute() else root / path).resolve()
    if not _inside(path, root):
        raise EngineError(f"scene {path} is not inside {root}")
    if path.suffix.lower() != ".scn" or not path.is_file():
        raise EngineError(f"not a scene file: {path}")
    resource = path.with_name(path.name + ".resource")
    if not resource.is_file():
        raise EngineError(f"scene resource missing: {resource}")
    rel = resource.relative_to(root).as_posix().lower()
    return SceneLoadData(name=path.name, ps=path.read_text(encoding="utf-8") if ps == "file" else "",
                         res_tag="res://" + rel, resource=resource.read_text(encoding="utf-8"), path=str(path))


def _scene_fields(data: SceneLoadData, *, with_name: bool) -> list[Field]:
    head: list[Field] = [("str", data.name)] if with_name else []
    return head + [("str", data.ps), ("str", data.res_tag), ("str", data.resource), ("bool", False)]  # no prefab


def load_scene_message(data: SceneLoadData, *, play: bool, server: str = DEFAULT_SERVER_ADDRESS,
                       game_mode: str = "", unloaded_blocks: Sequence[str] = ()) -> Message:
    """GameEditor.LoadScene: LoadScenePlay (sent on connect after PlayAfterConnect, i.e. the editor's Play
    button) = name, ps, tag, resource, isPrefab, serverAddress, gameMode; LoadScene = ..., isPrefab,
    int n, n x unloaded block names.  Engine: XginePlayMode.ProcessLoadScenePlay / XgineEditMode.ProcessLoadScene."""
    fields = _scene_fields(data, with_name=True)
    if play:
        fields += [("str", server), ("str", game_mode)]
    else:
        fields += [("int", len(unloaded_blocks))] + [("str", b) for b in unloaded_blocks]
    return ("LoadScenePlay" if play else "LoadScene"), fields


def play_message(data: SceneLoadData, *, server: str = DEFAULT_SERVER_ADDRESS, game_mode: str = "") -> Message:
    """GameEditor.Play (in-place; the shipped editor restarts the engine instead, IsSceneLoadNeedRestart):
    ps, tag, resource, isPrefab, serverAddress, gameMode; the engine uses its current scene name."""
    return "Play", _scene_fields(data, with_name=False) + [("str", server), ("str", game_mode)]


def stop_message(data: SceneLoadData) -> Message:
    return "Stop", _scene_fields(data, with_name=False) + [("int", 0)]


def start_frame_sharing_message(viewport: int = 0, width: int = 1280, height: int = 720) -> Message:
    """BaseViewportInputController.StartFrameSharing: id, max(64,w), max(64,h), rect x, y, w, h, visible.
    Engine: XgineViewportsController.ProcessStartFrameSharing creates the viewport (camera, shared frame),
    applies the resolution and answers FrameShared(handle, id, bgra)."""
    w, h = max(64, int(width)), max(64, int(height))
    return "StartFrameSharing", [("int", int(viewport)), ("int", w), ("int", h), ("int", 0), ("int", 0),
                                 ("int", w), ("int", h), ("bool", True)]


def minimize_on_deactivate_message(value: bool = False) -> Message:
    """Sent first on connect (GameEditor.OnConnected); false -> SetEditorWindowBackground(false)."""
    return "MinimizeEditorOnDeactivate", [("bool", bool(value))]


def check_message(message: Message) -> dict[str, Any]:
    name, fields = message
    if not isinstance(name, str) or not name:
        raise EngineError("message name required")
    rows = []
    for kind, value in fields:
        if kind not in FIELD_TYPES:
            raise EngineError(f"unknown field type {kind}")
        ok = {"str": isinstance(value, str), "bool": isinstance(value, bool),
              "int": isinstance(value, int) and not isinstance(value, bool) and -2**31 <= value < 2**31,
              "float": isinstance(value, (int, float)) and not isinstance(value, bool)}[kind]
        if not ok:
            raise EngineError(f"{name}: {value!r} is not a {kind}")
        rows.append({"t": kind, "v": value})
    return {"name": name, "fields": rows}


def is_scene_loaded(event: dict[str, Any]) -> bool:
    """LoadingsState("Scene", 1, "Loaded") from XgineSceneLoadingStepsNotifier.OnLeveLoaded."""
    return (event.get("event") == "editor_message" and event.get("name") == "LoadingsState"
            and (event.get("fields") or [None])[0] == "Scene" and (event.get("fields") or [None])[-1] == "Loaded")


def is_frame_shared(event: dict[str, Any]) -> bool:
    return event.get("event") == "editor_message" and event.get("name") == "FrameShared"


# ------------------------------------------------------------------ session
def native_guid_text(raw16: bytes) -> str:
    """{XXXXXXXX-XXXX-xxxx-XXXX-XXXXXXXXXXXX} from .NET Guid.ToByteArray() bytes."""
    import uuid
    p = str(uuid.UUID(bytes_le=bytes(raw16))).split("-")
    return "{" + "-".join([p[0].upper(), p[1].upper(), p[2].lower(), p[3].upper(), p[4].upper()]) + "}"


class EngineSession:
    """One windowless engine run.  Use as a context manager; ``start`` needs ``owner_approved``.

    ``engine_argv`` replaces the engine executable (tests run tests/fake_engine.py there); the command
    line after it is always built by ``build_command``.  ``hub_argv`` replaces the helper command.
    """

    def __init__(self, layout: RunLayout, *, game_root: str | Path | None = None,
                 sdk_editor_dir: str | Path | None = None, channel: int | None = None, adapter_id: int = 0,
                 size: tuple[int, int] = (1280, 720), timestep: float | None = None, level: str | None = None,
                 hub_port: int = HUB_PORT, discovery: bool = True, wall_clock: float = 900.0,
                 startup_timeout: float = 300.0, engine_argv: Sequence[str] | None = None,
                 hub_argv: Sequence[str] | None = None, env: dict[str, str] | None = None,
                 process_check: Callable[[], tuple[list, str | None]] = running_guarded_processes,
                 extra_sets: Iterable[EngineSet] = ()):
        self.layout = layout
        self.game_root = Path(game_root) if game_root else project_context.game_root()
        self.sdk_editor_dir = Path(sdk_editor_dir or default_sdk_editor_dir(self.game_root))
        self.exe = self.game_root / "root" / "bin" / "pc" / ENGINE_EXE
        self.cwd = self.exe.parent
        self.channel = channel if channel is not None else os.getpid()
        self.hub_port, self.discovery = hub_port, discovery
        self.wall_clock, self.startup_timeout = wall_clock, startup_timeout
        self.process_check = process_check
        self.env = env
        self._engine_prefix = list(engine_argv) if engine_argv else None
        self._hub_argv = list(hub_argv) if hub_argv else None
        argv, self.sets = build_command(self.exe, channel=self.channel, layout=layout, adapter_id=adapter_id,
                                        width=size[0], height=size[1], timestep=timestep, level=level,
                                        extra_sets=extra_sets)
        self.argv = (self._engine_prefix + argv[1:]) if self._engine_prefix else argv
        self.hub: HubClient | None = None
        self.engine: Any = None
        self.target: dict[str, Any] | None = None
        self.record: dict[str, Any] = {"schemaVersion": 1, "events": []}
        self.wall_clock_hit = False
        self._deadline: float | None = None
        self._watchdog: threading.Thread | None = None
        self._stopped = threading.Event()
        self._engine_log = None

    # -- planning
    def hub_output(self) -> Path:
        try:
            return hub_cache_dir() / hub_build_key(self.sdk_editor_dir)
        except OSError:
            return hub_cache_dir() / "<build key>"

    def hub_plan(self) -> list[str]:
        if self._hub_argv:
            return self._hub_argv
        return hub_command(hub_executable(self.hub_output()), self.sdk_editor_dir, port=self.hub_port,
                           discovery=self.discovery)

    def plan(self) -> dict[str, Any]:
        """Everything ``start`` would run, without running it."""
        return {
            "engine": {"argv": self.argv, "commandLine": subprocess.list2cmdline(self.argv),
                       "cwd": str(self.cwd), "desktop": "private (quiet.start)", "priority": "below_normal",
                       "env": {**quiet.SILENT_ENV, "S3D_TOOLS_CRASHDUMP_DIR": str(self.layout.crash)},
                       "sets": [s.__dict__ for s in self.sets], "wallClockSeconds": self.wall_clock},
            "hub": {"build": hub_build_command(self.sdk_editor_dir, self.hub_output()),
                    "argv": self.hub_plan(), "port": self.hub_port, "bind": "127.0.0.1",
                    "discovery": f"CONSOLE_IPDISCOVERY{self.hub_port} -> 127.0.0.1:{DISCOVERY_PORT}"
                    if self.discovery else None},
            "layout": self.layout.as_json(), "channel": f"Channel {self.channel}",
        }

    # -- lifecycle
    def _event(self, name: str, **data) -> None:
        self.record["events"].append({"t": round(time.monotonic() - self._t0, 3), "event": name, **data})

    def start(self, owner_approved: str | None = None) -> dict[str, Any]:
        self.record["gates"] = check_gates(owner_approved, process_check=self.process_check, hub_port=self.hub_port)
        if not self._engine_prefix and not self.exe.is_file():
            raise EngineError(f"engine not found: {self.exe}")
        self._t0 = time.monotonic()
        self._deadline = self._t0 + self.wall_clock
        self.record.update(plan=self.plan(), startedUtc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        try:
            hub_argv = self._hub_argv or hub_command(build_hub(self.sdk_editor_dir), self.sdk_editor_dir,
                                                     port=self.hub_port, discovery=self.discovery)
            self.layout.logs.mkdir(parents=True, exist_ok=True)
            self.hub = HubClient(hub_argv, log=self.layout.logs / "hub.stderr.log")
            ready = self.hub.wait_event(lambda e: e.get("event") in ("ready", "error"), 60)
            if not ready or ready.get("event") != "ready":
                raise EngineError(f"hub helper did not start: {ready}")
            self._event("hub-ready", **{k: ready.get(k) for k in ("port", "consoleTre", "runtime")})
            self._engine_log = open(self.layout.logs / "engine.log", "ab")
            self.engine = quiet.start(self.argv, cwd=self.cwd if not self._engine_prefix else None, env=self.env,
                                      desktop="private", priority="below_normal", log=self._engine_log,
                                      crash_dump_dir=self.layout.crash)
            self._event("engine-started", pid=self.engine.pid, desktop=self.engine.desktop_name)
            # owner 2026-10-20: the editor engine must always be silent (it has no mute setting of its own)
            self._muter = audio_mute.start_background(pids=[self.engine.pid], wait=self.wall_clock + 60,
                                                      log=self.layout.logs / "audio_mute.log")
            self._event("audio-mute", started=self._muter is not None)
            self._watchdog = threading.Thread(target=self._watch, daemon=True)
            self._watchdog.start()
            self.target = self._wait_listener()
            self._event("execssl-attached", target=self.target,
                        workspaceIsEditors=self.target.get("workspace") == WORKSPACE)
            return self.target
        except BaseException:
            self.stop()
            raise

    def snapshot_clients(self, key: str = "clients") -> list[dict[str, Any]]:
        """Record every hub client with its listener and speaker passports (what the engine registered)."""
        if self.hub is None:
            return []
        try:
            clients = self.hub.request("clients", wait=10).get("clients") or []
        except EngineError:
            return []
        self.record[key] = clients
        return clients

    def _announce(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
            udp.sendto(f"CONSOLE_IPDISCOVERY{self.hub_port}".encode("ascii"), ("127.0.0.1", DISCOVERY_PORT))

    def _check_alive(self) -> None:
        if self.wall_clock_hit:
            raise EngineError(f"wall-clock limit of {self.wall_clock:.0f} s reached; engine killed")
        if self.engine is not None and self.engine.poll() is not None:
            raise EngineError(f"engine exited with {self.engine.poll()} (see {self.layout.logs / 'engine.log'})")

    def _wait_listener(self) -> dict[str, Any]:
        deadline = time.monotonic() + self.startup_timeout
        last_announce = time.monotonic()
        while True:
            self._check_alive()
            pids = sorted(self.engine.pids() | {self.engine.pid})
            clients = self.hub.request("clients", wait=10).get("clients") or []
            mine = [c for c in clients if c.get("pid") in pids]
            if any(_has_execssl(c) for c in mine):
                self._event("engine-registered", clients=[{k: c.get(k) for k in ("name", "pid", "channel")}
                                                          for c in mine])
                answer = self.hub.request("attach", wait=30, pids=pids, timeout=12.0)
                if not answer.get("ok"):
                    raise EngineError(f"attach to the ExecSsl listener failed: {answer.get('error')}")
                return answer["target"]
            if time.monotonic() > deadline:
                raise EngineTimeout(f"engine did not register an Automation/ExecSsl listener within "
                                    f"{self.startup_timeout:.0f} s")
            if self.discovery and time.monotonic() - last_announce > 5:
                self._announce()
                last_announce = time.monotonic()
            time.sleep(0.5)

    def _watch(self) -> None:
        while not self._stopped.wait(0.25):
            if self._deadline is not None and time.monotonic() > self._deadline:
                self.wall_clock_hit = True
                self._event("wall-clock-kill", seconds=self.wall_clock)
                if self.engine is not None:
                    self.engine.kill()
                return

    def exec_ssl(self, script: str, timeout: float = 12.0) -> str:
        """Run SSL in the engine and return its reply string."""
        if self.hub is None or self.target is None:
            raise EngineError("session not started")
        self._check_alive()
        if self._deadline is not None:
            timeout = max(0.5, min(timeout, self._deadline - time.monotonic()))
        answer = self.hub.request("exec", wait=timeout + 10, script=script, timeout=float(timeout))
        if answer.get("ok"):
            return answer["reply"]
        self._check_alive()
        if answer.get("error") == "timeout":
            raise EngineTimeout(f"no ExecSsl reply within {timeout:.1f} s")
        raise EngineError(f"ExecSsl failed: {answer.get('error')}")

    def screenshot(self, path: str | Path, *, hud: bool = False, timeout: float = 20.0) -> dict[str, Any]:
        path = Path(path)
        if path.exists():
            raise EngineError(f"refusing to overwrite {path}")
        if not path.parent.is_dir():
            raise EngineError(f"folder does not exist: {path.parent}")
        reply = self.exec_ssl(screenshot_script(path, hud))
        result = wait_png(path, timeout)
        result["reply"] = reply
        return result

    # -- IntegrationStudio connector ("Game editor"), scene_play.md
    def attach_editor(self, connector: str = GAME_EDITOR, *, wait: float = 120.0) -> dict[str, Any]:
        """Open the editor's connector next to ExecSsl: a speaker mirroring the engine's
        {Module=IntegrationStudio, Type=<connector>} listener and listeners for the engine's
        {Module=IntegrationStudioProxy} <connector> and Manager speakers.  The engine registers that listener
        when its SSL GameEditorController initialises, so this retries until ``wait``.  Keep it attached:
        the engine exits 3 s after its last editor connection goes (GameEditorController.OnEditorDisconnected)."""
        if self.hub is None or self.target is None:
            raise EngineError("session not started")
        deadline = time.monotonic() + wait
        last: dict[str, Any] = {}
        while True:
            self._check_alive()
            last = self.hub.request("editor_attach", wait=30, connector=connector, timeout=12.0)
            if last.get("ok") and last.get("connected"):
                self._event("editor-attached", connector=connector, engineListener=last.get("engineListener"),
                            engineSpeaker=last.get("engineSpeaker"), manager=last.get("manager"))
                return last
            if last.get("ok"):  # attached but the engine listener did not connect: start over
                self.hub.request("detach", wait=10)
                self.target = None
                self.target = self._wait_listener()
            elif "engine has 0 " not in str(last.get("error")):  # only a missing listener is worth waiting for
                self.record["editorAttachFailure"] = {k: v for k, v in last.items() if k != "id"}
                raise EngineError(f"'{connector}' connector: {last.get('error')}")
            if time.monotonic() > deadline:
                self.record["editorAttachFailure"] = {k: v for k, v in last.items() if k != "id"}
                raise EngineTimeout(f"no engine '{connector}' connector within {wait:.0f} s: {last.get('error')}")
            time.sleep(1.0)

    def send_editor(self, message: Message, connector: str = GAME_EDITOR) -> dict[str, Any]:
        if self.hub is None:
            raise EngineError("session not started")
        self._check_alive()
        body = check_message(message)
        answer = self.hub.request("editor_send", wait=30, connector=connector, **body)
        if not answer.get("ok"):
            raise EngineError(f"{message[0]} not sent: {answer.get('error')}")
        self._event("editor-sent", message=message[0], bytes=answer.get("bytes"))
        return answer

    def editor_mark(self) -> int:
        """Index for ``wait_editor(since=...)``: only events after this point count."""
        return len(self.hub.events) if self.hub else 0

    def wait_editor(self, predicate: Callable[[dict[str, Any]], bool], timeout: float,
                    since: int = 0) -> dict[str, Any] | None:
        if self.hub is None:
            raise EngineError("session not started")
        if self._deadline is not None:
            timeout = max(0.0, min(timeout, self._deadline - time.monotonic()))
        row = self.hub.wait_event(lambda e: e.get("event") == "editor_message" and predicate(e), timeout, start=since)
        self._check_alive()
        return row

    def editor_messages(self) -> list[dict[str, Any]]:
        return [{k: v for k, v in e.items() if k != "event"} for e in (self.hub.events if self.hub else [])
                if e.get("event") == "editor_message"]

    def stop(self) -> dict[str, Any]:
        """Detach, close the hub, kill the engine tree.  Safe to call twice."""
        if self._stopped.is_set():
            return self.record.get("result", {})
        self._stopped.set()
        result: dict[str, Any] = {"wallClockHit": self.wall_clock_hit}
        if self.hub is not None:
            messages = self.editor_messages()
            if messages:
                self.record["editorMessages"] = messages[:500]
            try:
                self.hub.request("detach", wait=5)
            except EngineError:
                pass
            self.hub.close()
        if self.engine is not None:
            self.engine.sweep()
            self.engine.kill()
            try:
                self.engine.wait(15)
            except subprocess.TimeoutExpired:
                pass
            result.update(engineExit=self.engine.poll(), leakedWindows=self.engine.leaked_windows,
                          privateWindows=self.engine.private_windows)
            self.engine.close()
        muter = getattr(self, "_muter", None)
        if muter is not None and muter.poll() is None:
            muter.kill()
        if self._engine_log:
            self._engine_log.close()
        if hasattr(self, "_t0"):
            self._event("stopped", **{k: v for k, v in result.items() if k != "privateWindows"})
        self.record["result"] = result
        return result

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.stop()


def _has_execssl(client: dict[str, Any]) -> bool:
    for listener in client.get("listeners") or []:
        names = {(c.get("name"), c.get("value")) for c in listener.get("passport") or [] if not c.get("absent")}
        if ("Module", "Automation") in names and ("Type", "ExecSsl") in names:
            return True
    return False
