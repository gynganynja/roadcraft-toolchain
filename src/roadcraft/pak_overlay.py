"""Pak overlay: an editor project copy whose ``mods_source`` IS a built package, for the headless bench.

library/headless-bench.md "Benching a built package" explains use and evidence.  The editor engine reads no
mods folder (pakmount_001, 2026-10-13), so a package is benched by laying its members over a copy of an
editor project that holds the bench scene:

* the project (``.project``, ``game_launcher.cfg``, ``config/``, ``mods_source/``) is copied to a new folder,
  files hard-linked where the volume allows (a file that is changed is always unlinked and rewritten, so the
  source is never written); ``documents-dir`` and absolute project paths are pointed at the copy;
* every generated brand file under ``autogen*/`` whose staged copy ``ssl/<stem>_<suffix>`` is in the pak is
  removed (with its ``.resource``), so the old classes cannot load under their old names; generated files the
  pak does not ship (``auto_truck_library.sso``, ``auto_wheels_library.sso``, prefabs) stay and are retagged:
  the editor engine resolves the truck name through the project's truck library (KGS-25 launch 1,
  2026-10-13: without it ``SSL runtime error: key 'kgs25' is not found in dictionary`` while loading the
  scene's prefab);
* each removed generated ``.sso`` (truck, wheel and preview info) is written back at its project path with the
  pak's fields, its ``.resource`` keeping the project brand and file name: the editor engine registers trucks
  and wheel sets by scanning ``res://autogen_dw/trucks/auto_<t>/`` (retail
  ``ssl/game/autogen_libraries_creator.ssc``, key = folder name minus ``auto_``; KGS-25 launch 2:
  ``WheelsLibrary.Get`` key 'kgs25' not found);
* every pak member is written at its resource path (duplicate members must be byte-identical); the pak's
  root ``<name>.mod`` replaces ``mods/<name>.mod``;
* the kept generated files and every scene (``.scn`` and its ``.resource``) are retagged with class staging's own
  rules (``auto_kgs25`` -> ``auto_kgs25_kgs25``, ``res://autogen_dw/.../auto_kgs25.cls.resource`` ->
  ``res://ssl/auto_kgs25_kgs25.cls.resource``), the mapping being read from the pak's ``ssl/`` names and the
  project's generated files;
* optional ``markupBodies`` patches scalar fields of named bodies in the pak's ``.tpl_markup`` members
  (a bench variant of a built package, such as track-frame damping).

``overlay.json`` lists the pak hash, every member written with its sha256 (checked back from disk), the
removed files, the renames, the retagged files and the patches.  Read-only on the source project and pak.

    python -m roadcraft.pak_overlay --project <editor project> --pak <installed.pak> --out <new folder>
        [--suffix kgs25] [--markup-body "BoneTrackSusp_L_cdt:angularDamping=0.05,linearDamping=0"] [--json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Sequence

from . import class_staging as cs

SCHEMA_VERSION = 1
PROJECT_FILES = (".project", "game_launcher.cfg")


class OverlayError(ValueError):
    """The overlay inputs are unusable."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _link_or_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def _write_new(path: Path, data: bytes) -> None:
    """Replace ``path`` by a new file (never writes through a hard link to the source)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        path.unlink()
    path.write_bytes(data)


def read_members(pak: Path) -> dict[str, bytes]:
    """Every member of the pak by name; duplicate names must carry identical bytes."""
    members: dict[str, bytes] = {}
    with zipfile.ZipFile(pak) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or ".." in PurePosixPath(name).parts:
                raise OverlayError(f"unsafe member path {name!r} in {pak}")
            data = z.read(info)
            if name in members and members[name] != data:
                raise OverlayError(f"duplicate member {name} differs inside {pak}")
            members[name] = data
    return members


def staged_mapping(members: dict[str, bytes], generated: Sequence[str], suffix: str | None = None
                   ) -> tuple[str, dict[str, str], dict[str, str]]:
    """(suffix, renames old rel -> new rel, identifiers) for the project's generated files whose staged
    copy ``ssl/<stem>_<suffix><ext>`` is in the pak (class_staging's naming rules)."""
    staged = {n for n in members if n.startswith("ssl/") and n.count("/") == 1}
    if suffix is None:
        counts: dict[str, int] = {}
        for rel in generated:
            split = cs._brand_split(rel)
            if not split:
                continue
            stem, ext = split
            for name in staged:
                prefix = f"ssl/{stem}_"
                if name.startswith(prefix) and name.endswith(ext) and not name.endswith(ext + ".resource"):
                    cand = name[len(prefix):-len(ext)]
                    if cs.SUFFIX_RE.match(cand):
                        counts[cand] = counts.get(cand, 0) + 1
        if not counts:
            raise OverlayError("no generated project class has a staged copy in the pak; pass --suffix")
        suffix = max(sorted(counts), key=lambda s: counts[s])
    renames: dict[str, str] = {}
    identifiers: dict[str, str] = {}
    for rel in generated:
        split = cs._brand_split(rel)
        if not split:
            continue
        stem, ext = split
        new = f"ssl/{stem}_{suffix}{ext}"
        if new not in staged:
            continue
        renames[rel] = new
        if f"{new}.resource" in staged:
            renames[rel + ".resource"] = new + ".resource"
        identifiers[stem] = f"{stem}_{suffix}"
        if ext == ".sso":
            identifiers[cs.class_name(stem)] = cs.class_name(f"{stem}_{suffix}")
    return suffix, renames, identifiers


def patch_markup_fields(text: str, bone: str, fields: dict[str, float]) -> tuple[str, int]:
    """Set scalar fields (angularDamping, linearDamping, mass ...) in the physics property block of the
    object named ``bone`` in a ``.tpl_markup``; a missing field is added after ``mass``.  Returns (text, edits)."""
    m = re.search(r"name\s*=\s*\"" + re.escape(bone) + r"\"\r?\n((?:(?![^\r\n]*objectId)[^\r\n]*\r?\n)*?)[ \t]*\]\r?\n",
                  text)
    if not m:
        raise OverlayError(f"body {bone} not in the markup")
    block, edits = m.group(1), 0
    for key, value in fields.items():
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
            raise OverlayError(f"field name {key!r}")
        literal = repr(float(value)).rstrip("0").rstrip(".") if float(value) != int(value) else str(int(value))
        block, n = re.subn(r"(\b" + key + r"\s*=\s*)[-\d.eE+]+", r"\g<1>" + literal, block, count=1)
        if n == 0:
            block, n = re.subn(r"(\r?\n)([ \t]*)(mass\s*=\s*[-\d.eE+]+)", r"\1\2\3\1\2" + key + " = " + literal,
                               block, count=1)
        if n != 1:
            raise OverlayError(f"body {bone}: cannot set {key}")
        edits += 1
    return text[:m.start(1)] + block + text[m.end(1):], edits


def sync_library(text: str, staged_sso: dict[str, str]) -> tuple[str, list[str]]:
    """Replace each library entry whose ``__type`` is a staged ``.sso`` class (``AutoKgs25TruckWheelInfoKgs25``)
    by that class's own fields from the pak: the editor writes a library entry as the generated ``.sso``'s
    body with the class name as ``__type``, so an old project's library would otherwise keep the old build's
    entries (KGS-25: no ramp wheel).  ``staged_sso`` maps class name -> pak ``.sso`` text."""
    from .physics_bench import _close
    nl = "\r\n" if "\r\n" in text else "\n"
    synced: list[str] = []
    out, pos = [], 0
    for m in re.finditer(r"(?m)^([ \t]+)([A-Za-z_][A-Za-z0-9_]*)[ \t]+=[ \t]+\{[ \t]*\r?$", text):
        if m.start() < pos:
            continue
        ind, opening = m.group(1), m.end() - 1
        while text[opening] != "{":
            opening -= 1
        closing = _close(text, opening)
        body = text[opening + 1:closing]
        types = re.findall(r"(?m)^" + re.escape(ind) + r"[ \t]{3}__type[ \t]+=[ \t]+\"([^\"]+)\"", body)
        cls = types[-1] if types else None
        if cls not in staged_sso:
            continue
        src = staged_sso[cls].replace("\r\n", "\n").rstrip("\n").split("\n")
        if src and re.match(r'^__type\s+=\s+"[^"]*"$', src[-1].strip()) and not src[-1].startswith((" ", "\t")):
            src = src[:-1]
        src.append(f'__type   =   "{cls}"')
        inner = nl.join(ind + "   " + line if line else line for line in src)
        out.append(text[pos:opening + 1] + nl + inner + nl + ind)
        pos = closing
        synced.append(m.group(2))
    out.append(text[pos:])
    return "".join(out), synced


def overlay(project_dir: str | Path, pak: str | Path, out_dir: str | Path, *, suffix: str | None = None,
            markup_bodies: dict[str, dict[str, float]] | None = None) -> dict[str, Any]:
    project, pak, out = Path(project_dir).resolve(), Path(pak).resolve(), Path(out_dir).resolve()
    mods = project / "mods_source"
    if not mods.is_dir():
        raise OverlayError(f"{project} has no mods_source")
    if not pak.is_file():
        raise OverlayError(f"no pak {pak}")
    if out.exists() and any(out.iterdir()):
        raise OverlayError(f"{out} exists and is not empty")
    if out == project or project in out.parents or out in project.parents:
        raise OverlayError("the overlay folder must be outside the project")
    pak_bytes = pak.read_bytes()
    members = read_members(pak)
    files = sorted(p for p in mods.rglob("*") if p.is_file())
    rels = [cs._rel(p, mods) for p in files]
    generated = [r for r in rels if cs._brand_split(r)]
    suffix, renames, identifiers = staged_mapping(members, generated, suffix)
    renamer = cs.Renamer(renames, identifiers)

    report: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION, "tool": "roadcraft pak overlay", "project": str(project),
        "pak": str(pak), "pakSha256": _sha(pak_bytes), "out": str(out), "suffix": suffix,
        "renames": renames, "identifiers": identifiers, "removed": [], "written": [], "retagged": [],
        "projectFiles": [], "patched": [], "problems": []}

    # 1. the project copy (hard links), minus the generated files the pak ships staged
    for path, rel in zip(files, rels):
        if rel in renames:
            report["removed"].append(rel)
            continue
        _link_or_copy(path, out / "mods_source" / rel)
    for name in PROJECT_FILES:
        if (project / name).is_file():
            text = (project / name).read_text(encoding="utf-8")
            new, info = cs._retarget_project_text(text, project, out)
            _write_new(out / name, new.encode("utf-8"))
            report["projectFiles"].append({"file": name, **info})
    if (project / "config").is_dir():
        for path in sorted((project / "config").rglob("*")):
            if path.is_file():
                rel = cs._rel(path, project)
                text = cs._read_text(path)
                if text is None:
                    _link_or_copy(path, out / rel)
                    continue
                new, info = cs._retarget_project_text(text, project, out)
                # a copied bench project may still name the machine it came from (KGS kit: the desktop path)
                new, n_ms = re.subn(r"(?m)^([ \t]*ModsSourceLocal:[ \t]*).*$",
                                    lambda m: m.group(1) + (out / "mods_source").as_posix(), new)
                new, n_pp = re.subn(r"(?m)^([ \t]*ProjectPath:[ \t]*).*$",
                                    lambda m: m.group(1) + (out / ".project").as_posix(), new)
                info.update(modsSourceLocal=n_ms, projectPath=n_pp)
                _write_new(out / rel, new.encode("utf-8"))
                report["projectFiles"].append({"file": rel, **info})

    # 2. the pak's members (the .mod at the root replaces mods/<name>.mod)
    target_of: dict[str, str] = {}
    for name in sorted(members):
        rel = f"mods/{name}" if "/" not in name and name.endswith(".mod") else name
        target_of[name] = rel
    patches: dict[str, bytes] = {}
    for bone, fields in (markup_bodies or {}).items():
        hits = 0
        for name, data in members.items():
            if name.endswith(".tpl_markup"):
                text = data.decode("utf-8")
                if f'name = "{bone}"' not in text:
                    continue
                new, edits = patch_markup_fields(text, bone, fields)
                members[name] = new.encode("utf-8")
                patches[name] = new.encode("utf-8")
                report["patched"].append({"member": name, "body": bone, "fields": fields, "edits": edits})
                hits += 1
        if not hits:
            raise OverlayError(f"body {bone} is in no .tpl_markup of the pak")
    report["keptLinked"] = 0
    for name, rel in target_of.items():
        dst = out / "mods_source" / rel
        if dst.is_file() and dst.stat().st_size == len(members[name]) and dst.read_bytes() == members[name]:
            report["keptLinked"] += 1   # the project already holds these bytes: keep the hard link (disk)
            continue
        _write_new(dst, members[name])
    # registration shims: the editor engine registers trucks and wheel sets by scanning
    # res://autogen_dw/trucks/auto_<t>/auto_<t>_truck_info.sso, ..._truck_wheel_info.sso and trucks/preview/
    # (retail ssl/game/autogen_libraries_creator.ssc: AddTagsForTruckDir, key = folder minus "auto_"), not the
    # .mod; so each removed generated .sso is written back at its project path with the pak's own fields
    # (which name the staged classes) and its .resource keeps the project brand and file name
    report["registrationShims"] = []
    for old, new in sorted(renames.items()):
        if not old.endswith(".sso"):
            continue
        _write_new(out / "mods_source" / old, members[new])
        resource = members.get(new + ".resource")
        if resource is not None:
            stem = PurePosixPath(old).name[:-len(".sso")]
            text = resource.decode("utf-8")
            text = re.sub(r"(?m)^brandName:[ \t]*\S+", "brandName: " + cs.class_name(stem), text, count=1)
            text = re.sub(r"(?m)^sso:[ \t]*\S+", "sso: " + stem + ".sso", text, count=1)
            _write_new(out / "mods_source" / (old + ".resource"), text.encode("utf-8"))
        report["registrationShims"].append({"path": old, "from": new})
    for name, rel in target_of.items():
        data = (out / "mods_source" / rel).read_bytes()
        report["written"].append({"member": name, "path": rel, "sha256": _sha(data), "bytes": len(data),
                                  "patched": name in patches})
        if data != members[name]:
            report["problems"].append(f"{rel} does not read back as written")

    # 3. retag the kept generated files (libraries, prefabs) and every scene so the vehicle is the pak's class;
    #    library entries take the pak's own .sso fields
    report["librarySynced"] = []
    staged_sso = {cs.class_name(n[len("ssl/"):-len(".sso")]): members[n].decode("utf-8")
                  for n in members if n.startswith("ssl/") and n.endswith(".sso") and n.count("/") == 1}
    for path in sorted((out / "mods_source").rglob("*")):
        if not path.is_file():
            continue
        rel = cs._rel(path, out / "mods_source")
        base = rel[:-len(".resource")] if rel.endswith(".resource") else rel
        if not (base.endswith(".scn") or cs._brand_split(base)) or base in renames:   # shims stay as written
            continue
        text = cs._read_text(path)
        if text is None:
            continue
        new, paths, ids = renamer.apply(text)
        if base.endswith(".sso") and not rel.endswith(".resource"):
            new, synced = sync_library(new, staged_sso)
            if synced:
                report["librarySynced"].append({"file": rel, "entries": synced})
        if new != text:
            _write_new(path, new.encode("utf-8"))
            report["retagged"].append({"file": rel, "paths": paths, "identifiers": ids})
    missing = [n for n in renames.values() if not (out / "mods_source" / n).is_file()]
    if missing:
        report["problems"].append(f"staged files missing after the overlay: {missing}")
    (out / "overlay.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


def _parse_markup_body(values: Sequence[str]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for value in values or []:
        bone, _, pairs = value.partition(":")
        if not bone or not pairs:
            raise OverlayError(f"--markup-body {value!r}: BONE:key=value[,key=value]")
        for pair in pairs.split(","):
            key, _, number = pair.partition("=")
            out.setdefault(bone.strip(), {})[key.strip()] = float(number)
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="roadcraft.pak_overlay", description=__doc__.split("\n")[0])
    parser.add_argument("--project", required=True, help="editor project folder (holds mods_source, the bench scene)")
    parser.add_argument("--pak", required=True, help="built package to lay over the project copy")
    parser.add_argument("--out", required=True, help="new folder for the overlaid project")
    parser.add_argument("--suffix", help="the pak's class suffix (default: read from its ssl/ names)")
    parser.add_argument("--markup-body", action="append", default=[],
                        help="BONE:key=value[,key=value] patch of a body's physics fields in the pak's markups")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = overlay(args.project, args.pak, args.out, suffix=args.suffix,
                         markup_bodies=_parse_markup_body(args.markup_body))
    except (OverlayError, OSError, zipfile.BadZipFile) as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}))
        return 2
    if args.json:
        print(json.dumps(report, indent=1))
    else:
        print(f"{report['out']}: {len(report['written'])} members, {len(report['removed'])} generated files removed, "
              f"{len(report['retagged'])} retagged, suffix {report['suffix']}, problems {len(report['problems'])}")
    return 1 if report["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
