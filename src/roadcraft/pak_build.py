"""Build a mod package without the Mod Editor: the editor's Build Mod packer step, quiet and deterministic.

library/headless-build.md explains use, evidence and limits (``roadcraft pak build``).

The Mod Editor's Build Mod (``ModEditorCommands.ExecuteBuildMod``, decompiled ModEditorPlugin) ends in
``ModBuilder.RunBuilderAsync``, which runs the project variable ``mod-builder-exe``
(``tools/bin/ModPakBuilder/mod_pak_builder.exe``) as
``--project <dir> --resource-roots <tags>... --output <pak> --mod_file <mod>``.  The released mods
(D11 RC3-RC5, Roamer 105, WALL-E) already skip the editor and call the packer on a staged project with
``--resource-roots-file``; this module is that route made reusable:

* the roots default to the ``.mod`` file's ``scenes`` + ``assets`` with ``res://`` prepended (the
  editor passes ``exportedScenes.Concat(newModData.Data.Assets)``); a blank root is refused, because the
  packer turns it into an empty tag;
* the packer runs through :mod:`roadcraft.quiet` (private desktop, no window, no crash dialogs, the
  whole process tree killed on timeout) with TEMP/TMP/TMPDIR redirected into the work folder: its
  ``.pct`` slicer leaves ``NamedTemporaryFile(delete=False)`` files behind;
* the packer exits 0 even when a blob is missing (``There isn't blob '{}' in layers.`` is only logged,
  recovered from its bytecode): those lines fail this build;
* the raw package is normalized with :mod:`roadcraft.pak_determinism` (member timestamps are the only
  bytes that differ between rebuilds of the same input), so the same input gives the same bytes;
* a receipt (``build.json``) records the input hashes, the packer's identity, the log findings, any
  window the packer tree showed on the user's desktop, and the output hash.

Scene export (``furnace scene``) and the editor's asset renaming are not part of this step: every
released mod packs assets only (``scenes: []``).  A ``.mod`` that lists scenes is refused with a pointer
to the library article.  Nothing here installs a package; use ``roadcraft install``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from . import pak_determinism, quiet

PACKER = Path("tools/bin/ModPakBuilder/mod_pak_builder.exe")
MISSING_BLOB = re.compile(r"There isn't blob '([^']*)' in layers")
PAK_LAYER_BLOB = re.compile(r"This blob '([^']*)' in pak layer")
DUPLICATE = re.compile(r"Duplicate name: '([^']*)'")
EMPTY_INPUTS = "resource inputs is empty"
DEFAULT_TIMEOUT = 3600.0


class PakBuildError(ValueError):
    """The build inputs are unusable or the packer failed."""


@dataclass
class BuildPlan:
    project: Path
    mod_file: Path
    roots: list[str]
    output: Path
    work: Path
    packer: Path
    game_root: Path
    normalize: bool = True
    timeout: float = DEFAULT_TIMEOUT
    roots_source: str = "mod"
    problems: list[str] = field(default_factory=list)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_mod_file(path: Path) -> dict[str, Any]:
    """Read the ``title``/``description``/``scenes``/``assets`` of a ``.mod`` (YAML, block or flow lists)."""
    data: dict[str, Any] = {}
    current: str | None = None
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("- ") or line.startswith("  - "):
            if current is None or not isinstance(data.get(current), list):
                raise PakBuildError(f"{path}: list item outside a list: {raw!r}")
            data[current].append(_scalar(line.split("- ", 1)[1]))
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise PakBuildError(f"{path}: unreadable line {raw!r}")
        key, value = key.strip(), value.strip()
        current = key
        if value == "":
            data[key] = []
        elif value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            data[key] = [_scalar(v) for v in inner.split(",")] if inner else []
        else:
            data[key] = _scalar(value)
    return data


def _scalar(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text


def roots_from_mod(mod: dict[str, Any]) -> list[str]:
    tags = []
    for key in ("scenes", "assets"):
        for entry in mod.get(key) or []:
            entry = str(entry).strip()
            tags.append(entry if entry.startswith("res://") else "res://" + entry.replace("\\", "/"))
    return tags


def plan(project: str | Path, mod_file: str | Path, output: str | Path, *, roots_file: str | Path | None = None,
         roots: Sequence[str] | None = None, work: str | Path | None = None, game_root: str | Path | None = None,
         normalize: bool = True, timeout: float = DEFAULT_TIMEOUT) -> BuildPlan:
    """Check the inputs without running anything; ``problems`` lists every reason the build would be refused."""
    project, mod_file, output = Path(project).resolve(), Path(mod_file).resolve(), Path(output).resolve()
    game = Path(game_root).resolve() if game_root else _default_game_root()
    work_dir = Path(work).resolve() if work else output.parent / (output.stem + ".build")
    problems: list[str] = []
    if not (project / ".project").is_file():
        problems.append(f"{project} has no .project (a staged SDK project folder is required)")
    mod: dict[str, Any] = {}
    if not mod_file.is_file():
        problems.append(f"mod file {mod_file} does not exist")
    else:
        try:
            mod = read_mod_file(mod_file)
        except PakBuildError as error:
            problems.append(str(error))
    if mod.get("scenes"):
        problems.append("the .mod lists scenes; headless scene export (furnace scene) is not wired yet "
                        "(library/headless-build.md)")
    source = "mod"
    if roots_file is not None:
        source = str(Path(roots_file).resolve())
        tags = Path(roots_file).read_text(encoding="utf-8-sig").splitlines()
    elif roots:
        source, tags = "argv", list(roots)
    else:
        tags = roots_from_mod(mod)
    if not tags:
        problems.append("no resource roots (the packer would log 'resource inputs is empty' and stop)")
    for number, tag in enumerate(tags, 1):
        if not tag.strip():
            problems.append(f"root {number} is blank (the packer would turn it into an empty tag)")
        elif not tag.startswith("res://"):
            problems.append(f"root {number} {tag!r} is not a res:// tag")
    packer = game / PACKER
    if not packer.is_file():
        problems.append(f"packer not found: {packer}")
    if output.exists():
        problems.append(f"{output} exists; move it away first (builds never overwrite)")
    if output.suffix.lower() != ".pak":
        problems.append(f"{output} is not a .pak path")
    return BuildPlan(project, mod_file, [t.strip() for t in tags], output, work_dir, packer, game, normalize,
                     timeout, source, problems)


def _default_game_root() -> Path:
    env = os.environ.get("ROADCRAFT_ROOT")
    if env:
        return Path(env).resolve()
    return Path(r"C:\Program Files (x86)\Steam\steamapps\common\RoadCraft")


def scan_log(text: str) -> dict[str, Any]:
    missing = sorted(set(MISSING_BLOB.findall(text)))
    return {"missingBlobs": missing, "retailBlobsSkipped": len(set(PAK_LAYER_BLOB.findall(text))),
            "duplicateNames": len(DUPLICATE.findall(text)), "emptyInputs": EMPTY_INPUTS in text,
            "errorLines": [line for line in text.splitlines() if "[ERROR]" in line or "Traceback" in line][:50]}


def build(p: BuildPlan) -> dict[str, Any]:
    """Run the packer quietly, check its log, normalize the package and write the receipt; returns the receipt."""
    if p.problems:
        raise PakBuildError("; ".join(p.problems))
    if p.work.exists() and any(p.work.iterdir()):
        raise PakBuildError(f"work folder {p.work} is not empty; move it away first")
    scratch = p.work / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    roots_path = p.work / "roots.txt"
    roots_path.write_text("\n".join(p.roots), encoding="utf-8")
    raw = p.work / "packer_output.pak"
    log_path = p.work / "mod_pak_builder.log"
    env = dict(os.environ, ROADCRAFT_ROOT=str(p.game_root), TEMP=str(scratch), TMP=str(scratch),
               TMPDIR=str(scratch))
    argv = [str(p.packer), "--project", str(p.project), "--resource-roots-file", str(roots_path),
            "--output", str(raw), "--mod_file", str(p.mod_file)]
    started = time.time()
    with log_path.open("wb") as log:
        result = quiet.run(argv, cwd=scratch, env=env, timeout=p.timeout, capture=False, log=log,
                           crash_dump_dir=p.work / "crash")
    text = log_path.read_text(encoding="utf-8", errors="replace")
    findings = scan_log(text)
    receipt: dict[str, Any] = {
        "schemaVersion": 1, "tool": "roadcraft pak build", "started": round(started, 3),
        "seconds": result.seconds, "argv": argv,
        "inputs": {"project": str(p.project), "modFile": {"path": str(p.mod_file), "sha256": _sha256(p.mod_file)},
                   "roots": {"source": p.roots_source, "count": len(p.roots),
                             "sha256": hashlib.sha256("\n".join(p.roots).encode()).hexdigest()},
                   "packer": {"path": str(p.packer), "sha256": _sha256(p.packer)}},
        "packer": {"returncode": result.returncode, "timedOut": result.timed_out, "log": str(log_path),
                   "leakedWindows": result.leaked_windows, "privateWindows": result.private_windows,
                   "orphansKilled": result.orphans_killed},
        "log": findings, "output": None, "ok": False,
    }
    failures = []
    if result.timed_out:
        failures.append(f"packer timed out after {p.timeout:.0f} s")
    if result.returncode != 0:
        failures.append(f"packer exit code {result.returncode}")
    if findings["missingBlobs"]:
        failures.append(f"{len(findings['missingBlobs'])} missing blob(s), first {findings['missingBlobs'][0]!r}")
    if findings["emptyInputs"]:
        failures.append("packer reported empty resource inputs")
    if not raw.is_file():
        failures.append("packer wrote no package")
    if not failures:
        if p.normalize:
            receipt["normalize"] = pak_determinism.normalize(raw, p.output)
        else:
            shutil.copyfile(raw, p.output)
        receipt["output"] = {"path": str(p.output), "sha256": _sha256(p.output), "bytes": p.output.stat().st_size,
                             "normalized": p.normalize}
    receipt["failures"] = failures
    receipt["ok"] = not failures
    (p.work / "build.json").write_text(json.dumps(receipt, indent=1, sort_keys=True), encoding="utf-8")
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="roadcraft pak build", description=__doc__.split("\n\n")[0])
    parser.add_argument("--project", required=True, help="staged SDK project folder (contains .project)")
    parser.add_argument("--mod-file", required=True, help="the mod's .mod file")
    parser.add_argument("--output", required=True, help="package to create (never overwritten)")
    roots = parser.add_mutually_exclusive_group()
    roots.add_argument("--roots-file", help="one res:// tag per line (default: the .mod scenes + assets)")
    roots.add_argument("--root", action="append", help="a res:// root tag (repeatable)")
    parser.add_argument("--work", help="work folder for the log, scratch and receipt (default: <output>.build)")
    parser.add_argument("--game-root", help="RoadCraft install with tools/bin (default: ROADCRAFT_ROOT or Steam)")
    parser.add_argument("--no-normalize", action="store_true", help="keep the packer's timestamps")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--apply", action="store_true", help="run the packer (default: preflight only)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    p = plan(args.project, args.mod_file, args.output, roots_file=args.roots_file, roots=args.root, work=args.work,
             game_root=args.game_root, normalize=not args.no_normalize, timeout=args.timeout)
    if not args.apply:
        report = {"preflight": True, "ready": not p.problems, "problems": p.problems, "roots": len(p.roots),
                  "rootsSource": p.roots_source, "output": str(p.output), "work": str(p.work),
                  "packer": str(p.packer)}
        print(json.dumps(report, indent=1) if args.json else
              ("ready" if not p.problems else "not ready:\n  " + "\n  ".join(p.problems)))
        return 0 if not p.problems else 2
    try:
        receipt = build(p)
    except PakBuildError as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(receipt, indent=1, sort_keys=True))
    else:
        print(("built " + receipt["output"]["path"] + " " + receipt["output"]["sha256"]) if receipt["ok"]
              else "FAILED: " + "; ".join(receipt["failures"]))
        if receipt["packer"]["leakedWindows"]:
            print(f"warning: {len(receipt['packer']['leakedWindows'])} window(s) reached the desktop")
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
