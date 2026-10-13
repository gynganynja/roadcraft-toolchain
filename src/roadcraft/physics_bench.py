"""Physics bench: measure a vehicle's handling in the Mod Editor before installing a change.

library/physics-bench.md explains use and limits (``roadcraft bench init|apply|run|batch|analyse|compare``).
KGS25 (2026-10-02): a suspension change designed from the library's formulas was installed unmeasured
and the owner reported "it does it worse now"; this bench then measured why (springs 25-40x softer
than predicted, a track sinking 19 cm in pivot turns) and compared six variants before the next install.

* ``init_bench`` copies a mod's editor project (``mods_source``, ``.project``, configs), the editor data
  and profiles into a bench folder with the project's absolute paths rewritten, so the source project
  is never written, and writes ``bench.json`` and a play scenario that echoes a ready marker.
* ``apply_variant`` restores pristine copies of the text resources, then patches them: suspension
  axles by collection name, a track's real/fake wheel lists, a slot's axle, wheel-class fields, body
  masses/centres of mass in the markup, and the test vehicle's spawn position.
* ``run``/``batch`` launch the editor (integrations/physics-bench/launch_editor.ps1), sample every body
  and wheel at 7-10 Hz through the read-only ExecSsl receiver (series_probe.ps1) while driving a fixed
  input schedule (input_override.ps1), close the editor and write a per-phase summary
  (``analyse``/``compare``).

Patchers and analysis were checked against the KGS25 bench script: identical files for its ten
variants, identical summaries for its five recorded runs.  Editor runs take the PC (GPU, CPU,
focus): ask the owner first.  Bench numbers are editor-pad evidence (grade Game, "editor play
mode"), not retail acceptance.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from .bench_stability import phase_stability

INTEGRATION = Path(__file__).resolve().parents[2] / "integrations" / "physics-bench"
PWSH = "pwsh"
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# (start second, input); names label the phases for the analysis
SCHEDULES: dict[str, dict[str, Any]] = {
    "normal": {"duration": 64, "names": ["rest", "forward", "stop", "pivot+", "settle+", "pivot-", "settle-",
                                         "reverse", "final"],
               "steps": [(0, (0, 0, "On", "AUTO")), (10, (0.35, 0, "Off", "AUTO")), (14, (0, 0, "On", "AUTO")),
                         (22, (0.3, 0.8, "Off", "AUTO")), (26, (0, 0, "On", "AUTO")),
                         (36, (0.3, -0.8, "Off", "AUTO")), (40, (0, 0, "On", "AUTO")),
                         (50, (-0.35, 0, "Off", "REVERSE")), (54, (0, 0, "On", "AUTO"))]},
    "harsh": {"duration": 56, "names": ["rest", "fast", "brake", "lock+", "settle+", "lock-", "settle-",
                                        "fastrev", "final"],
              "steps": [(0, (0, 0, "On", "AUTO")), (6, (1.0, 0, "Off", "AUTO")), (14, (0, 0, "On", "AUTO")),
                        (20, (0.6, 1.0, "Off", "AUTO")), (25, (0, 0, "On", "AUTO")),
                        (31, (0.6, -1.0, "Off", "AUTO")), (36, (0, 0, "On", "AUTO")),
                        (42, (-1.0, 0, "Off", "REVERSE")), (48, (0, 0, "On", "AUTO"))]},
}


# Longer, zero-steer travel plus parked/unbraked idle cover faults hidden by brief pivot schedules.
SCHEDULES["straight"] = {"duration": 80, "names": ["rest", "forward", "stop", "reverse", "final"],
    "steps": [(0, (0, 0, "On", "AUTO")), (12, (.35, 0, "Off", "AUTO")),
              (32, (0, 0, "On", "AUTO")), (44, (-.35, 0, "Off", "REVERSE")),
              (64, (0, 0, "On", "AUTO"))]}
# Same duration and zero steering at full pedal: keep its baseline separate.
SCHEDULES["straightfull"] = {"duration": 80, "names": ["rest", "forward", "stop", "reverse", "final"],
    "steps": [(0, (0, 0, "On", "AUTO")), (12, (1, 0, "Off", "AUTO")),
              (32, (0, 0, "On", "AUTO")), (44, (-1, 0, "Off", "REVERSE")),
              (64, (0, 0, "On", "AUTO"))]}
SCHEDULES["idle"] = {"duration": 76,
    "names": ["rest", "idle", "forward", "coast", "reverse", "coast_reverse", "final"],
    "steps": [(0, (0, 0, "On", "AUTO")), (10, (0, 0, "Off", "AUTO")),
              (26, (.35, 0, "Off", "AUTO")), (30, (0, 0, "Off", "AUTO")),
              (46, (-.35, 0, "Off", "REVERSE")), (50, (0, 0, "Off", "AUTO")),
              (66, (0, 0, "On", "AUTO"))]}


class BenchError(ValueError):
    """A bench folder, variant or recorded run is unusable."""


# ------------------------------------------------------------------ text patchers
def _close(text: str, opening: int) -> int:
    """Index of the bracket closing the one at ``opening`` (``{`` or ``[``)."""
    depth = 0
    for i in range(opening, len(text)):
        if text[i] in "{[":
            depth += 1
        elif text[i] in "}]":
            depth -= 1
            if depth == 0:
                return i
    raise BenchError("unbalanced brackets")


def _block(text: str, key: str) -> tuple[int, int]:
    """(after the opening bracket, closing bracket) of the first ``key = {...}`` or ``key = [...]``."""
    m = re.search(r"\b" + key + r"\s*=\s*[\[{]", text)
    if not m:
        raise BenchError(f"no {key} block")
    return m.end(), _close(text, m.end() - 1)


def _entries(body: str) -> list[tuple[int, int]]:
    """(start, end) spans of the top-level ``{ ... }`` entries of a list body."""
    spans, i = [], 0
    while True:
        i = body.find("{", i)
        if i < 0:
            return spans
        j = _close(body, i)
        spans.append((i, j + 1))
        i = j + 1


def _literal(value: Any) -> str:
    return {True: "True", False: "False"}[value] if isinstance(value, bool) else str(value)


def axle_names(class_text: str) -> dict[str, int]:
    """``suspensionCollectionMap`` of a compiled truck class: axle name -> index in suspensionAxleCollection."""
    a, b = _block(class_text, "suspensionCollectionMap")
    return {n: int(v) for n, v in re.findall(r"(\w+)\s*=\s*\{\s*__value\s*=\s*(\d+)\s*\}", class_text[a:b])}


def patch_axles(class_text: str, axles: dict[str, dict[str, Any]]) -> str:
    """Rewrite named SuspensionAxle entries of a compiled truck class (min, max, height, strength,
    damping; keys left out take the engine defaults), keeping the file's spacing and line ends."""
    index = axle_names(class_text)
    missing = sorted(set(axles) - set(index))
    if missing:
        raise BenchError(f"axles not in suspensionCollectionMap: {missing}")
    a, b = _block(class_text, "suspensionAxleCollection")
    body = class_text[a:b]
    spans = _entries(body)
    if any(index[name] >= len(spans) for name in axles):
        raise BenchError("suspensionCollectionMap points past suspensionAxleCollection")
    eq = re.search(r"suspensionAxleCollection(\s*=\s*)", class_text).group(1)
    nl = "\r\n" if "\r\n" in body else "\n"
    pieces, last = [], 0
    for i, (s, e) in enumerate(spans):
        pieces.append(body[last:s])
        name = next((n for n in axles if index[n] == i), None)
        if name is None:
            pieces.append(body[s:e])
        else:
            indent = re.search(r"([ \t]*)\Z", body[:s]).group(1)
            keys = [k for k in ("min", "max", "height", "strength", "damping") if k in axles[name]]
            unknown = sorted(set(axles[name]) - set(keys))
            if unknown:
                raise BenchError(f"unknown axle fields for {name}: {unknown}")
            lines = "".join(f"{nl}{indent}   {k}{eq}{axles[name][k]}" for k in keys)
            pieces.append("{" + lines + nl + indent + "}")
        last = e
    pieces.append(body[last:])
    return class_text[:a] + "".join(pieces) + class_text[b:]


def patch_track_lists(class_text: str, track: int, wheel_ids: list[int] | None = None,
                      fake_ids: list[int] | None = None) -> str:
    """Set the ``track``-th track's wheelIds/fakeWheelIds, keeping inline or one-per-line list style."""
    def rewrite(text: str, key: str, ids: list[int]) -> str:
        matches = list(re.finditer(r"\b" + key + r"(\s*=\s*)\[([^\]]*)\]", text))
        if track >= len(matches):
            raise BenchError(f"no {key} list for track {track}")
        m = matches[track]
        inner = m.group(2)
        if "\n" in inner:
            item = re.match(r"\r?\n([ \t]*)", inner).group(1)
            close = re.search(r"\n([ \t]*)\Z", inner).group(1)
            nl = "\r\n" if "\r\n" in inner else "\n"
            body = ",".join(f"{nl}{item}{n}" for n in ids) + f"{nl}{close}"
        else:
            body = " " + ", ".join(map(str, ids)) + " " if ids else " "
        return text[:m.start()] + f"{key}{m.group(1)}[{body}]" + text[m.end():]
    if wheel_ids is not None:
        class_text = rewrite(class_text, "wheelIds", wheel_ids)
    if fake_ids is not None:
        class_text = rewrite(class_text, "fakeWheelIds", fake_ids)
    return class_text


def patch_slot_axle(class_text: str, geom_name: str, axle_index: int) -> str:
    """suspensionCollectionAxleIndex of the wheel slot named ``geom_name``."""
    pattern = (r"(geomName\s*=\s*\"" + re.escape(geom_name) + r"\"\r?\n(?:(?![^\r\n]*geomName)[^\r\n]*\r?\n)*?"
               r"[ \t]*suspensionCollectionAxleIndex\s*=\s*)\d+")
    new, n = re.subn(pattern, r"\g<1>" + str(axle_index), class_text, count=1)
    if n != 1:
        raise BenchError(f"wheel slot {geom_name} has no suspensionCollectionAxleIndex")
    return new


def patch_wheel_fields(wheel_class_text: str, fields: dict[str, Any]) -> str:
    """Set top-level ``prop_truck_wheel`` fields (mass, softForceScale, isSoftContactEnabled, ...) of a
    compiled wheel class; absent fields are added after the last scalar before the nested blocks."""
    a, b = _block(wheel_class_text, "prop_truck_wheel")
    lines = wheel_class_text[a:b].splitlines(keepends=True)
    depth, seen, insert_at, indent, eq = 0, set(), None, None, " = "
    for i, line in enumerate(lines):
        m = re.match(r"([ \t]*)(\w+)(\s*=\s*)([^\r\n]*)", line)
        if depth == 0 and m:
            indent = m.group(1) if indent is None else indent
            eq = m.group(3)
            if m.group(4).rstrip().endswith(("{", "[")):
                insert_at = i if insert_at is None else insert_at
            elif m.group(2) in fields:
                lines[i] = line[:m.start(4)] + _literal(fields[m.group(2)]) + line[m.end(4):]
                seen.add(m.group(2))
        depth += sum(line.count(c) for c in "{[") - sum(line.count(c) for c in "}]")
    nl = "\r\n" if "\r\n" in wheel_class_text else "\n"
    extra = [f"{indent or '      '}{k}{eq}{_literal(v)}{nl}" for k, v in fields.items() if k not in seen]
    if insert_at is None:      # no nested block: before the closing bracket's own line
        insert_at = len(lines) - 1 if lines and not lines[-1].strip() else len(lines)
    lines[insert_at:insert_at] = extra
    return wheel_class_text[:a] + "".join(lines) + wheel_class_text[b:]


def patch_markup_body(markup_text: str, bone: str, mass: float | None = None, com: list[float] | None = None) -> str:
    """Body mass and/or hkCenterOfMassOffset (engine axes, Y up) of one object in a ``.tpl_markup``;
    the offset is inserted when absent."""
    m = re.search(r"name\s*=\s*\"" + re.escape(bone) + r"\"\r?\n((?:(?![^\r\n]*objectId)[^\r\n]*\r?\n)*?)[ \t]*\]\r?\n",
                  markup_text)
    if not m:
        raise BenchError(f"body {bone} not in the markup")
    block = m.group(1)
    if mass is not None:
        block, n = re.subn(r"(\bmass\s*=\s*)[\d.]+", r"\g<1>" + str(mass), block, count=1)
        if n != 1:
            raise BenchError(f"body {bone} has no explicit mass")
    if com is not None:
        text = "[ " + ", ".join(str(c) for c in com) + " ]"
        if "hkCenterOfMassOffset" in block:
            block = re.sub(r"hkCenterOfMassOffset\s*=\s*\[[^\]]*\]", "hkCenterOfMassOffset = " + text, block, count=1)
        else:
            block, n = re.subn(r"(\r?\n)([ \t]*)(__type\s*=\s*\"tpl_markup_object_property_physics\")",
                               r"\1\2\3\1\2hkCenterOfMassOffset = " + text, block, count=1)
            if n != 1:
                raise BenchError(f"body {bone} has no physics property block")
    return markup_text[:m.start(1)] + block + markup_text[m.end(1):]


def place_vehicle(scene_text: str, vehicle: str, position: list[float]) -> str:
    """Spawn position of a named vehicle object in a scene file."""
    pattern = r"(\b" + re.escape(vehicle) + r"\s*=\s*\{\s*transform\s*=\s*\{\s*position\s*=\s*)\[[^\]]*\]"
    new, n = re.subn(pattern, r"\g<1>[ " + ", ".join(str(v) for v in position) + " ]", scene_text, count=1)
    if n != 1:
        raise BenchError(f"vehicle {vehicle} has no transform position in the scene")
    return new


# ------------------------------------------------------------------ bench folder
CONFIG_FILES = (".project", "game_launcher.cfg")


def _rewrite_bytes(data: bytes, old: Path, new: Path) -> bytes:
    """Replace a folder path in either slash style, keeping encoding and line ends."""
    text = data.decode("utf-8")
    for a, b in ((old.as_posix(), new.as_posix()), (str(old), str(new))):
        text = text.replace(a, b)
        # SDK YAML emitters fold long plain path scalars at a space. Match that
        # one folded separator too, or a copied bench keeps its source project.
        parts = re.split(r"[ \t]+", a)
        if len(parts) > 1:
            pattern = r"(?:[ \t]+|\r?\n[ \t]+)".join(re.escape(part) for part in parts)
            text = re.sub(pattern, lambda match: b, text)
    return text.encode("utf-8")


def _project_configs(project: Path) -> list[Path]:
    return [project / n for n in CONFIG_FILES if (project / n).is_file()] + sorted((project / "config").glob("*.cfg"))


def init_bench(project: str | Path, data_dir: str | Path, profiles_dir: str | Path, bench: str | Path, *,
               scene: str, vehicle: str, editor: str | Path, files: dict[str, Any],
               sdk_editor_directory: str | Path) -> dict[str, Any]:
    """Copy an editor project into ``bench/project`` (absolute paths in .project and config rewritten),
    with editor data and profiles, and write bench.json and play.scenario.  ``scene`` and ``files`` are
    relative to ``mods_source``; ``files`` = {"class": ..., "markup": ..., "wheelClasses": {kind: ...}}.
    ``sdk_editor_directory`` is the SDK's ``tools/bin/ModEditor`` (the probes load Saber.ConsoleTre.dll)."""
    project, bench = Path(project).resolve(), Path(bench).resolve()
    if bench.exists() and any(bench.iterdir()):
        raise BenchError(f"bench folder {bench} is not empty")
    for rel in [scene, files["class"], files["markup"], *(files.get("wheelClasses") or {}).values()]:
        if not (project / "mods_source" / rel).is_file():
            raise BenchError(f"not in the project's mods_source: {rel}")
    target = bench / "project"
    shutil.copytree(project / "mods_source", target / "mods_source")
    for src in _project_configs(project):
        dst = target / src.relative_to(project)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(_rewrite_bytes(src.read_bytes(), project, target))
    shutil.copytree(data_dir, bench / "data")
    shutil.copytree(profiles_dir, bench / "profiles")
    marker = "BENCH_GAME_MODE_READY"
    (bench / "play.scenario").write_text(
        f'open "{(target / "mods_source" / scene).as_posix()}"\ncommand GameEditorCommands StartEngine\n'
        "wait-viewport\nwait-scene-loading\ncommand GameEditorCommands FocusViewport\ncommand GameEditorCommands Play\n"
        f"delay 00:00:25\nwait-viewport\nwait-scene-loading\necho {marker}\ndelay 00:30:00\n"
        "command GameEditorCommands Stop\nexit\n", encoding="utf-8", newline="\n")
    config = {"schemaVersion": 1, "bench": str(bench), "project": str(target), "dataDir": str(bench / "data"),
              "profilesDir": str(bench / "profiles"), "scenario": str(bench / "play.scenario"), "readyMarker": marker,
              "editor": str(editor), "scene": scene, "vehicle": vehicle, "files": files,
              "sdkEditorDirectory": str(sdk_editor_directory)}
    (bench / "bench.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    leftovers = [str(p) for p in _project_configs(target)
                 if any(s in p.read_bytes().decode("utf-8", "ignore") for s in (project.as_posix(), str(project)))]
    return {"config": str(bench / "bench.json"), "leftoverReferences": leftovers}


def load_config(path: str | Path) -> dict[str, Any]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    for key in ("bench", "project", "dataDir", "profilesDir", "scenario", "editor", "scene", "vehicle", "files"):
        if key not in config:
            raise BenchError(f"bench.json lacks {key}")
    return config


def load_variant(path: str | Path) -> dict[str, Any]:
    """A variant file: {"name": ..., "variant": {...}} or the variant itself (named after the file)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if "variant" in data:
        return {"name": data.get("name") or Path(path).stem, "variant": data["variant"]}
    return {"name": Path(path).stem, "variant": data}


VARIANT_KEYS = {"axles", "tracks", "slotAxles", "wheels", "bodies", "spawn", "note"}


def apply_variant(config: dict[str, Any], variant: dict[str, Any]) -> list[str]:
    """Restore pristine copies, then apply ``variant``: {"axles": {name: axle}, "tracks": [{"track",
    "wheelIds", "fakeWheelIds"}], "slotAxles": {geomName: index}, "wheels": {kind: fields}, "bodies":
    {bone: {"mass", "com"}}, "spawn": [x, y, z]}.  An empty variant restores the pristine project.
    Returns the files written (relative to mods_source)."""
    unknown = sorted(set(variant) - VARIANT_KEYS)
    if unknown:
        raise BenchError(f"unknown variant keys: {unknown}")
    mods = Path(config["project"]) / "mods_source"
    pristine = Path(config["bench"]) / "pristine"
    files = config["files"]
    paths = {"class": files["class"], "markup": files["markup"], "scene": config["scene"],
             **{f"wheel:{k}": v for k, v in (files.get("wheelClasses") or {}).items()}}
    for rel in paths.values():
        keep = pristine / rel
        if not keep.exists():      # first use: the project as copied is the pristine state
            keep.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(mods / rel, keep)
    text = {key: (pristine / rel).read_bytes().decode("utf-8") for key, rel in paths.items()}
    if variant.get("axles"):
        text["class"] = patch_axles(text["class"], variant["axles"])
    for row in variant.get("tracks") or []:
        text["class"] = patch_track_lists(text["class"], row["track"], row.get("wheelIds"), row.get("fakeWheelIds"))
    for geom, index in (variant.get("slotAxles") or {}).items():
        text["class"] = patch_slot_axle(text["class"], geom, index)
    for kind, fields in (variant.get("wheels") or {}).items():
        if f"wheel:{kind}" not in text:
            raise BenchError(f"bench.json files.wheelClasses lacks {kind}")
        text[f"wheel:{kind}"] = patch_wheel_fields(text[f"wheel:{kind}"], fields)
    for bone, change in (variant.get("bodies") or {}).items():
        text["markup"] = patch_markup_body(text["markup"], bone, change.get("mass"), change.get("com"))
    if variant.get("spawn"):
        text["scene"] = place_vehicle(text["scene"], config["vehicle"], variant["spawn"])
    for key, rel in paths.items():
        (mods / rel).write_bytes(text[key].encode("utf-8"))
    return sorted(paths.values())


# ------------------------------------------------------------------ running
def _ps(script: Path, *args, timeout: float = 60) -> subprocess.CompletedProcess:
    cmd = [PWSH, "-NoProfile", "-File", str(script), *map(str, args)]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, creationflags=NO_WINDOW)


def _ps_to_file(script: Path, log: Path, *args, timeout: float = 900) -> int:
    """For scripts that start long-lived children: a captured pipe would be inherited and never close."""
    cmd = [PWSH, "-NoProfile", "-File", str(script), *map(str, args)]
    with open(log, "w") as fh:
        p = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
        return p.wait(timeout=timeout)


def _sdk(config: dict[str, Any]) -> list[str]:
    if not config.get("sdkEditorDirectory"):
        raise BenchError("bench.json lacks sdkEditorDirectory (<SDK root>/tools/bin/ModEditor)")
    return ["-SdkEditorDirectory", config["sdkEditorDirectory"]]


def drive(config: dict[str, Any], folder: Path, engine_pid: int, schedule: str = "normal") -> list[dict[str, Any]]:
    """Record series.jsonl while applying the schedule's inputs (each retried up to 3 times)."""
    plan = SCHEDULES[schedule]
    folder = Path(folder).resolve()      # the probe and input scripts need absolute output paths
    with open(folder / "series.stdout", "w") as out:
        probe = subprocess.Popen([PWSH, "-NoProfile", "-File", str(INTEGRATION / "series_probe.ps1"),
                                  "-EngineProcessId", str(engine_pid), "-OutputPath", str(folder / "series.jsonl"),
                                  "-Count", "20000", "-IntervalMs", "40", "-DurationSeconds", str(plan["duration"]),
                                  *_sdk(config)], stdout=out, stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
        t0, log = time.time(), []
        for step, (at, (pedal, steer, brake, gear)) in enumerate(plan["steps"]):
            while time.time() - t0 < at:
                time.sleep(0.05)
            for attempt in range(3):      # the console server occasionally times out a registration
                r = _ps(INTEGRATION / "input_override.ps1", "-Mode", "Apply", "-Method", "Debug", "-EngineProcessId",
                        engine_pid, "-OutputPath", folder / f"input_{step:02d}_{attempt}.json", "-Pedal", pedal,
                        "-Steer", steer, "-Handbrake", brake, "-StartEngine", "-GearState", gear,
                        "-TimeoutSeconds", 5, *_sdk(config))
                if r.returncode == 0:
                    break
            log.append({"at": round(time.time() - t0, 2), "pedal": pedal, "steer": steer, "brake": brake,
                        "gear": gear, "rc": r.returncode, "attempts": attempt + 1, "err": r.stderr[-300:]})
        probe.wait(timeout=plan["duration"] + 60)
    (folder / "inputs.json").write_text(json.dumps(log, indent=1), encoding="utf-8")
    return log


def run(config: dict[str, Any], name: str, variant: dict[str, Any], schedule: str = "normal") -> dict[str, Any]:
    """Apply a variant, launch the editor, drive, close the editor, analyse.  Writes
    runs/<name>_<schedule>_<HHMMSS>/ (variant.json, launch.json, stdout.log, series.jsonl, inputs.json,
    summary.json).  The project is left with the variant applied; ``apply_variant(config, {})`` restores it."""
    if schedule not in SCHEDULES:
        raise BenchError(f"unknown schedule {schedule}")
    _sdk(config)
    apply_variant(config, variant)
    folder = Path(config["bench"]) / "runs" / f"{name}_{schedule}_{time.strftime('%H%M%S')}"
    folder.mkdir(parents=True)
    meta = {"name": name, "schedule": schedule, "variant": variant, "hull": config.get("hull"),
            "frames": config.get("frames")}
    (folder / "variant.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    _ps_to_file(INTEGRATION / "launch_editor.ps1", folder / "launch.stdout", "-RunDir", folder,
                "-Project", config["project"], "-DataDir", config["dataDir"], "-ProfilesDir", config["profilesDir"],
                "-Scenario", config["scenario"], "-Editor", config["editor"],
                "-ReadyMarker", config.get("readyMarker", "BENCH_GAME_MODE_READY"))
    launch_file = folder / "launch.json"
    launch = json.loads(launch_file.read_text(encoding="utf-8-sig")) if launch_file.exists() else {}
    try:
        if not launch.get("ready") or not launch.get("enginePid"):
            raise BenchError(f"editor not ready, see {folder}")
        time.sleep(5)
        drive(config, folder, launch["enginePid"], schedule)
    finally:
        if launch.get("studioPid"):
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(launch["studioPid"])], capture_output=True)
        time.sleep(3)
    return analyse(folder)


def batch(config: dict[str, Any], variants: list[dict[str, Any]], schedule: str = "normal") -> list[dict[str, Any]]:
    """Run named variants one after another, keep going past failures, restore the pristine project."""
    results = []
    try:
        for item in variants:
            try:
                results.append({"name": item["name"], "summary": run(config, item["name"], item["variant"], schedule)})
            except (BenchError, OSError, subprocess.SubprocessError, ValueError) as exc:
                results.append({"name": item["name"], "error": str(exc)})
    finally:
        apply_variant(config, {})
    return results


# ------------------------------------------------------------------ analysis
def parse_series(path: str | Path) -> list[dict[str, Any]]:
    """Samples of series.jsonl: t, frame, speed, pedal, steer, bodies {name: pos/up/fwd} and wheels
    [{travel, pos, ground}] (series_probe.ps1 reply lines F, B and W).  Replies of the 2026-10-04 probe add
    ``engine`` {gear, rpm, handbrake, running, brakePull} (line G), each body's ``mass``, ``comLocal`` and
    ``comWorld`` (line C: the engine's own centre of mass, body frame Y up) and per wheel ``spin`` (rad/s),
    ``wheelSpeed`` (m/s), ``physicalRadius``, ``mudDepth`` and ``onTerrain``; older recordings parse as before."""
    samples = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        text = row.get("r") or ""
        if not text.startswith("F "):
            continue
        s: dict[str, Any] = {"t": row["t"], "bodies": {}, "wheels": []}
        for ln in text.splitlines():
            p = ln.split()
            if not p:
                continue
            if p[0] == "F":
                s["frame"], s["speed"], s["pedal"], s["steer"] = int(p[1]), float(p[2]), float(p[3]), float(p[4])
            elif p[0] == "G" and len(p) >= 4:
                s["engine"] = {"gear": int(p[1]), "rpm": float(p[2]), "handbrake": p[3] == "1"}
                if len(p) >= 6:
                    s["engine"].update(running=p[4] == "1", brakePull=p[5] == "1")
            elif p[0] == "B":
                v = list(map(float, p[2:11]))
                s["bodies"].setdefault(p[1], {}).update(pos=v[0:3], up=v[3:6], fwd=v[6:9])
            elif p[0] == "C" and len(p) >= 9:
                v = list(map(float, p[2:9]))
                s["bodies"].setdefault(p[1], {}).update(mass=v[0], comLocal=v[1:4], comWorld=v[4:7])
            elif p[0] == "W" and len(p) >= 6:
                w = {"travel": float(p[1]), "pos": list(map(float, p[2:5])), "ground": p[5] == "1"}
                if len(p) >= 11:
                    w.update(spin=float(p[6]), wheelSpeed=float(p[7]), physicalRadius=float(p[8]),
                             mudDepth=float(p[9]), onTerrain=p[10] == "1")
                s["wheels"].append(w)
        samples.append(s)
    return samples


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _angle(a, b):
    return math.degrees(math.acos(max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b))))))


def _yaw(body):
    return math.degrees(math.atan2(body["fwd"][0], body["fwd"][2]))


def phase_of(t: float, schedule: str = "normal") -> str:
    plan = SCHEDULES[schedule]
    index = 0
    for k, (at, _) in enumerate(plan["steps"]):
        if t >= at:
            index = k
    return plan["names"][index]


def guess_bodies(samples: list[dict[str, Any]]) -> tuple[str, tuple[str, ...]]:
    """Hull (BoneChassis_cdt, else the first body named *chassis*) and track frames/bogies."""
    names = list(dict.fromkeys(n for s in samples for n in s["bodies"]))
    hull = "BoneChassis_cdt" if "BoneChassis_cdt" in names else next((n for n in names if "chassis" in n.lower()), None)
    if hull is None:
        raise BenchError("no hull body in the series; name it in bench.json 'hull'")
    frames = tuple(n for n in names if n != hull and any(k in n.lower() for k in ("tracksusp", "trackframe", "bogie")))
    return hull, frames


def summarise(samples: list[dict[str, Any]], schedule: str = "normal", hull: str | None = None,
              frames: tuple[str, ...] | None = None) -> dict[str, Any]:
    """Per phase: hull roll/pitch extremes and ranges (deg), height range and median against rest (mm),
    largest frame-to-hull twist (deg), wheel travel, wheels off the ground; ``motion`` gives yaw change,
    distance and top speed for each driven phase (to its next phase + 1.5 s), so a steady variant that
    no longer turns or drives is not mistaken for a fix."""
    guessed = guess_bodies(samples)
    hull = hull or guessed[0]
    frames = guessed[1] if frames is None else tuple(frames)
    plan = SCHEDULES[schedule]
    rows = []
    for s in samples:
        h = s["bodies"].get(hull)
        if not h:
            continue
        left = _cross(h["up"], h["fwd"])
        twists = [_angle(s["bodies"][f]["up"], h["up"]) for f in frames if f in s["bodies"]]
        wheels = s["wheels"]
        rows.append({"t": s["t"], "phase": phase_of(s["t"], schedule), "y": h["pos"][1],
                     "roll": math.degrees(math.asin(max(-1, min(1, left[1])))),
                     "pitch": math.degrees(math.asin(max(-1, min(1, h["fwd"][1])))),
                     "twist": max(twists) if twists else 0.0,
                     "maxTravel": max((w["travel"] for w in wheels), default=0.0),
                     "meanTravel": statistics.mean(w["travel"] for w in wheels) if wheels else 0.0,
                     "airborne": sum(1 for w in wheels if not w["ground"])})
    if not rows:
        raise BenchError(f"no samples of {hull}")
    rest = [r["y"] for r in rows if r["phase"] == plan["names"][0]] or [rows[0]["y"]]
    base = statistics.median(rest)
    phases = {}
    for name in plan["names"]:
        rs = [r for r in rows if r["phase"] == name]
        if not rs:
            continue

        def spread(key):
            return round(max(r[key] for r in rs) - min(r[key] for r in rs), 3)

        phases[name] = {
            "n": len(rs), "rollMaxAbs": round(max(abs(r["roll"]) for r in rs), 2), "rollRange": spread("roll"),
            "pitchMaxAbs": round(max(abs(r["pitch"]) for r in rs), 2), "pitchRange": spread("pitch"),
            "heightRangeMm": round(1000 * (max(r["y"] for r in rs) - min(r["y"] for r in rs)), 1),
            "heightVsRestMm": round(1000 * (statistics.median(r["y"] for r in rs) - base), 1),
            "twistMax": round(max(r["twist"] for r in rs), 2), "maxTravel": round(max(r["maxTravel"] for r in rs), 3),
            "meanTravel": round(statistics.mean(r["meanTravel"] for r in rs), 3),
            "maxAirborne": max(r["airborne"] for r in rs)}
    motion = {}
    steps = plan["steps"]
    for k, (start, (pedal, _, _, _)) in enumerate(steps):
        if not pedal:
            continue
        end = (steps[k + 1][0] if k + 1 < len(steps) else plan["duration"]) + 1.5
        window = [s for s in samples if start <= s["t"] <= end and hull in s["bodies"]]
        if len(window) < 2:
            continue
        a, b = window[0]["bodies"][hull], window[-1]["bodies"][hull]
        motion[plan["names"][k]] = {
            "yaw": round((_yaw(b) - _yaw(a) + 180) % 360 - 180, 1),
            "moved": round(math.dist((a["pos"][0], a["pos"][2]), (b["pos"][0], b["pos"][2])), 2),
            "vmax": round(max(abs(s.get("speed", 0.0)) for s in window), 2)}
    span = rows[-1]["t"] - rows[0]["t"]
    return {"hull": hull, "frames": list(frames), "samples": len(rows),
            "sampleHz": round((len(rows) - 1) / span, 1) if span > 0 else None, "phases": phases, "motion": motion,
            "stabilityBrakeBounded": phase_stability(samples, plan, hull, settle_seconds=0, end_margin_seconds=0,
                                                       observed_windows=True, include_pedal_ramp=True)
                                     if schedule in ("straight", "straightfull", "stateprobe") else {},
            "stability": phase_stability(samples, plan, hull),
            "stabilityObserved": phase_stability(samples, plan, hull, observed_windows=True),
            "stabilityPlannedWholePhase": phase_stability(samples, plan, hull, settle_seconds=0, end_margin_seconds=0),
            "stabilityWholePhase": phase_stability(samples, plan, hull, settle_seconds=0, end_margin_seconds=0,
                                                   observed_windows=True)}


def analyse(folder: str | Path, schedule: str | None = None) -> dict[str, Any]:
    """Summarise a recorded run folder into summary.json."""
    folder = Path(folder)
    meta_file = folder / "variant.json"
    meta = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.exists() else {}
    schedule = schedule or meta.get("schedule") or "normal"
    summary = summarise(parse_series(folder / "series.jsonl"), schedule, meta.get("hull"), meta.get("frames"))
    inputs_file = folder / "inputs.json"
    inputs = json.loads(inputs_file.read_text(encoding="utf-8")) if inputs_file.exists() else []
    summary.update(name=meta.get("name", folder.name), schedule=schedule,
                   inputsApplied=f"{sum(1 for i in inputs if i.get('rc') == 0)}/{len(inputs)}")
    (folder / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return summary


COLUMNS = [("rollMaxAbs", "roll"), ("pitchMaxAbs", "pitch"), ("rollRange", "rollRng"), ("heightRangeMm", "hRng mm"),
           ("heightVsRestMm", "h-rest mm"), ("twistMax", "twist"), ("maxTravel", "maxTrav"), ("maxAirborne", "air")]


def compare(folders: list[str | Path]) -> str:
    """Phase tables of several analysed runs (degrees, metres unless marked), motion line under each."""
    out = []
    for folder in map(Path, folders):
        path = folder / "summary.json"
        if not path.exists():
            out.append(f"== {folder.name}: no summary.json")
            continue
        d = json.loads(path.read_text(encoding="utf-8"))
        out.append(f"== {folder.name}  samples={d.get('samples')} ~{d.get('sampleHz')} Hz  inputs={d.get('inputsApplied')}")
        out.append(f"{'phase':9}" + "".join(f"{label:>10}" for _, label in COLUMNS))
        for phase, row in d["phases"].items():
            out.append(f"{phase:9}" + "".join(f"{row.get(k, ''):>10}" for k, _ in COLUMNS))
        if d.get("motion"):
            out.append("motion: " + " | ".join(f"{k} yaw {m['yaw']:+.1f} moved {m['moved']:.2f} vmax {m['vmax']:.2f}"
                                               for k, m in d["motion"].items()))
    return "\n".join(out)
