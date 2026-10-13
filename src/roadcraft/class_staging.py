"""Class staging: turn an ordinary editor project into the flat ``ssl/<brand>_<suffix>`` layout every mod pak ships.

library/headless-build.md "Class staging" explains use, evidence and limits (``roadcraft pak stage`` and
``roadcraft pak build --stage-classes --suffix S``).

An editor project keeps the generated truck classes under ``mods_source/autogen_dw/...``
(``trucks/auto_<t>/auto_<t>.cls``, ``auto_wheel_<t>_<w>.cls``, ``auto_<t>_truck_info.sso``, ...,
``trucks/preview/auto_<t>/...``).  Every installed mod pak carries them only as
``ssl/<stem>_<suffix><ext>`` with every reference retagged.  The rules here are the editor's
``BatchAssetRenamer`` (decompiled ``ModEditorCommands.cs``), with the suffix chosen per mod instead of the
editor's per-launch GUID, which is what the mods' own retail-export scripts do (Jimny ``tools/package.py``,
Roamer 105 Ute ``build_native.py package``):

* **What is staged** (``Prebuild``/``CollectAllUsedAssets``): the brand files (``.cls .sso .prop .lwi
  .prefab``) reachable from the ``.mod`` assets (or the given roots) through ``res://`` links, limited to
  the generated ``autogen*/`` folders; files already under ``ssl/`` are kept.  Unreachable generated files
  (``auto_truck_library.sso``, ``auto_wheels_library.sso``, ``<t>_prefab.prefab``) stay where they are,
  exactly as no installed pak ships them.
* **Names** (``Prebuild``/``RenameBrands``/``RenameMod``): ``<dir>/<stem><ext>`` ->
  ``ssl/<stem>_<suffix><ext>`` (+ ``.resource``), flat.
* **Identifiers** (``_shortNames``/``_brandRenames``/``_classRenames`` in ``ProcessString``/``ProcessSection``
  and ``PatchGenericResource``): every whole-word ``<stem>`` becomes ``<stem>_<suffix>``; for ``.sso``
  brands the class name ``SSLUtils.ConvertBrandToClassName(stem)`` becomes
  ``ConvertBrandToClassName(stem_suffix)`` (``AutoKgs25TruckInfo`` -> ``AutoKgs25TruckInfoKgs25``;
  this covers ``brandName`` and ``__type``).
* **Links**: every ``autogen.../<stem><ext>[.resource]`` path (``res://`` tags in ``.resource`` lists, class
  bodies, markups, the ``.mod`` assets) becomes ``ssl/<stem>_<suffix><ext>[.resource]``.

The editor re-serialises each class through its type system (``PsSystem.SavePsToFile``); installed mods are
token-renamed instead, which keeps every other byte (CRLF, spacing, order).  This module does the latter
and was checked byte for byte against installed paks (KGS-25, Jimny, Roamer 105 Ute).

The source project is never written.  The copy goes to a new folder; the ``.project``/``*.cfg``
``documents-dir`` and absolute project paths are pointed at the copy, otherwise the packer would read the
original ``mods_source``.  Output is deterministic (sorted walks, no timestamps in the report).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Sequence

BRAND_EXTS = (".cls", ".sso", ".prop", ".lwi", ".prefab")   # BatchAssetRenamer.Prebuild brand families
TEXT_EXTS = {".resource", ".cls", ".sso", ".prop", ".lwi", ".prefab", ".tpl_markup", ".mi", ".mod", ".scn",
             ".ssl", ".ssc", ".ssolib"}
PROJECT_FILE_NAMES = (".project", ".project-local")
PROJECT_FILE_EXTS = (".cfg", ".prjenv")
DEFAULT_SKIP = (".blend", ".blend1")                        # authoring files; never a resource
SUFFIX_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
LINK = re.compile(r"res://([^\s\"',\]\}]+)")
WORD = "A-Za-z0-9_"
SCHEMA_VERSION = 1


class StagingError(ValueError):
    """The staging inputs are unusable."""


# --- SSLUtils.ConvertBrandToClassName (decompiled IntegrationCommon2, Saber.IntegrationCommon.V2.SSL) ---

def _upper_first(part: str) -> str:
    return part[:1].upper() + part[1:].lower()


def _ref_part(part: str) -> str:
    words = [_upper_first(w) for w in re.split(r"_|::", part) if w]
    if not words:
        return ""
    out = words[0]
    for word in words[1:]:          # MergeParts: two digits meeting across a split keep their underscore
        out += ("_" if out[-1].isdigit() and word[0].isdigit() else "") + word
    return out


def class_name(brand: str) -> str:
    """``auto_kgs25_truck_info`` -> ``AutoKgs25TruckInfo``; ``auto_r105_2`` -> ``AutoR105_2``."""
    return "_".join(_ref_part(p) for p in brand.split("|"))


# --- helpers ---

def _rel(path: Path, base: Path) -> str:
    return path.relative_to(base).as_posix()


def _tag_path(tag: str) -> str:
    tag = tag.strip()
    if tag.startswith("res://"):
        tag = tag[len("res://"):]
    return tag.replace("\\", "/").lstrip("/")


def _brand_split(rel: str) -> tuple[str, str] | None:
    """``autogen_dw/x/auto_k.cls`` -> (``auto_k``, ``.cls``) for a generated brand file, else None."""
    parts = PurePosixPath(rel).parts
    if len(parts) < 2 or not parts[0].lower().startswith("autogen"):
        return None
    name = parts[-1]
    for ext in BRAND_EXTS:
        if name.endswith(ext) and len(name) > len(ext):
            return name[: -len(ext)], ext
    return None


def _read_text(path: Path) -> str | None:
    try:
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _is_text(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1].lower()
    return any(name.endswith(ext) for ext in TEXT_EXTS)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_mod_assets(text: str) -> list[str]:
    """The ``assets`` block/flow list of a ``.mod`` (same reader rules as pak_build)."""
    from .pak_build import read_mod_file_text
    return [str(a) for a in read_mod_file_text(text).get("assets") or []]


class Renamer:
    """The rename tables and the text transform (path links first, then whole-word identifiers)."""

    def __init__(self, renames: dict[str, str], identifiers: dict[str, str]):
        self.renames = renames            # old rel -> new rel, both the brand file and its .resource
        self.identifiers = identifiers    # stem -> stem_suffix, ClassName -> ClassNameSuffix
        olds = sorted(renames, key=lambda s: (-len(s), s))
        # a whole tag (res://autogen_dw/...) or a bare project-relative path (.mod assets); never the tail of a
        # longer path such as mods_source/autogen_dw/...
        self._paths = re.compile(r"(?:(?<=res://)|(?<![" + WORD + r"./\\-]))(" + "|".join(map(re.escape, olds))
                                 + r")(?![" + WORD + r"])") if olds else None
        ids = sorted(identifiers, key=lambda s: (-len(s), s))
        # '/' and '\\' are excluded on both sides: a folder named like a brand (autogen_dw/trucks/auto_k/...) is a
        # path to a file that is NOT renamed (prefab, library) and must keep resolving
        self._ids = re.compile(r"(?<![" + WORD + r"/\\])(" + "|".join(map(re.escape, ids)) + r")(?![" + WORD + r"/\\])") \
            if ids else None

    def apply(self, text: str) -> tuple[str, int, int]:
        paths = ids = 0
        if self._paths is not None:
            text, paths = self._paths.subn(lambda m: self.renames[m.group(1)], text)
        if self._ids is not None:
            text, ids = self._ids.subn(lambda m: self.identifiers[m.group(1)], text)
        return text, paths, ids


def _path_pattern(path: Path) -> re.Pattern[str]:
    """An absolute path in any slash style and case, allowing a YAML line fold at each space."""
    text = str(path.resolve()).replace("\\", "/").rstrip("/")
    pieces = []
    for ch in text:
        if ch == "/":
            pieces.append(r"[\\/]")
        elif ch == " ":
            pieces.append(r"(?:[ \t]*\r?\n[ \t]+|[ \t]+)")
        else:
            pieces.append(re.escape(ch))
    return re.compile("".join(pieces) + r"(?![" + WORD + r"])", re.IGNORECASE)


DOCUMENTS_DIR = re.compile(r"(?m)^documents-dir:[ \t]*(.*(?:\r?\n[ \t]+\S.*)*)")


def _retarget_project_text(text: str, source: Path, target: Path) -> tuple[str, dict[str, Any]]:
    """Point ``documents-dir`` and absolute source-project paths at the staged copy (GenerateTempProject's job)."""
    dst = str(target.resolve()).replace("\\", "/")
    info: dict[str, Any] = {}
    match = DOCUMENTS_DIR.search(text)
    if match:
        old = " ".join(part.strip() for part in match.group(1).splitlines())
        info["documentsDir"] = {"from": old, "to": dst}
        old_path = old.strip("\"'")
        try:
            same = Path(old_path).resolve() == source.resolve()
        except OSError:
            same = False
        if not same:
            info["documentsDirWasElsewhere"] = True
        text = text[: match.start()] + "documents-dir: " + dst + text[match.end():]
    text, count = _path_pattern(source).subn(lambda _m: dst, text)
    info["pathReplacements"] = count
    return text, info


# --- the staging plan ---

def _closure(mods: Path, roots: Iterable[str]) -> tuple[list[str], list[str]]:
    """Local resources reachable from the roots through res:// links (.resource files and their text blobs)."""
    seen: set[str] = set()
    missing: set[str] = set()
    queue = [_tag_path(t) for t in roots]
    while queue:
        rel = queue.pop()
        if rel in seen:
            continue
        path = mods / rel
        if not path.is_file():
            if rel.split("/", 1)[0].lower().startswith("autogen"):
                missing.add(rel)
            continue                                   # a retail tag, resolved from the game's paks
        seen.add(rel)
        sources = [path]
        if rel.endswith(".resource"):
            blob = mods / rel[: -len(".resource")]
            if blob.is_file():
                sources.append(blob)
        for source in sources:
            if not _is_text(_rel(source, mods)):
                continue
            text = _read_text(source)
            if text is None:
                continue
            for link in LINK.findall(text):
                queue.append(_tag_path(link))
    return sorted(seen), sorted(missing)


def _walk(root: Path, skip_dirs: Sequence[Path]) -> list[Path]:
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        dirnames[:] = sorted(d for d in dirnames if (here / d).resolve() not in skip_dirs)
        files.extend(here / f for f in sorted(filenames))
    return files


def stage(project_dir: str | Path, out_dir: str | Path, suffix: str, *, mod_file: str | Path | None = None,
          roots: Sequence[str] | None = None, dry_run: bool = False,
          skip_suffixes: Sequence[str] = DEFAULT_SKIP) -> dict[str, Any]:
    """Copy ``project_dir`` to the new ``out_dir`` with the generated classes staged under ``ssl/``.

    Returns the report: ``renames``, ``identifiers``, ``rewritten`` (file, path and identifier counts),
    ``projectFiles``, ``notStaged``, ``unmapped``, ``roots`` (the staged root tags), ``modFile`` and
    ``problems``.  With problems nothing is written; with ``dry_run`` nothing is written either.
    """
    project = Path(project_dir).resolve()
    out = Path(out_dir).resolve()
    mods = project / "mods_source"
    problems: list[str] = []
    suffix = (suffix or "").strip()
    if suffix.startswith("_"):
        suffix = suffix[1:]
    if not SUFFIX_RE.match(suffix):
        problems.append(f"suffix {suffix!r} must be lower-case letters/digits (with single underscores), "
                        "for example 'kgs25' or 'gd11'")
    if not (project / ".project").is_file():
        problems.append(f"{project} has no .project")
    if not mods.is_dir():
        problems.append(f"{project} has no mods_source folder")
    if out == project or project in out.parents:
        problems.append(f"staging folder {out} is inside the project; choose a folder outside it")
    if out in project.parents:
        problems.append(f"staging folder {out} contains the project")
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        problems.append(f"staging folder {out} exists and is not empty (staging never overwrites)")

    mod_path = Path(mod_file).resolve() if mod_file else None
    mod_text = None
    if mod_path is not None:
        mod_text = _read_text(mod_path) if mod_path.is_file() else None
        if mod_text is None:
            problems.append(f"mod file {mod_path} is missing or not UTF-8 text")
    if roots is not None:
        root_tags = [r.strip() for r in roots if r.strip()]
    elif mod_text is not None:
        root_tags = ["res://" + _tag_path(a) for a in read_mod_assets(mod_text)]
    else:
        root_tags = []
    if not root_tags and not problems:
        problems.append("no roots: pass the .mod (its assets are the roots) or explicit roots")

    report: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION, "tool": "roadcraft class staging", "dryRun": dry_run,
        "project": str(project), "out": str(out), "suffix": suffix,
        "rules": "BatchAssetRenamer (ModEditorCommands.cs) with a per-mod suffix; library/headless-build.md",
        "renames": [], "identifiers": {}, "rewritten": [], "projectFiles": [], "notStaged": [], "unmapped": [],
        "skipped": [], "roots": [], "modFile": None, "copied": {"files": 0, "bytes": 0}, "problems": problems,
    }
    if problems:
        return report

    closure, missing = _closure(mods, root_tags)
    for rel in missing:
        report["unmapped"].append({"file": None, "link": "res://" + rel, "reason": "linked generated file is missing"})
    renames: dict[str, str] = {}
    identifiers: dict[str, str] = {}
    stems: dict[tuple[str, str], str] = {}
    brands: list[tuple[str, str, str]] = []
    for rel in closure:
        main = rel[: -len(".resource")] if rel.endswith(".resource") else rel
        split = _brand_split(main)
        if split is None or main in {b[0] for b in brands}:
            continue
        stem, ext = split
        if not (mods / main).is_file() or not (mods / (main + ".resource")).is_file():
            problems.append(f"{main}: the brand file and its .resource must both exist")
            continue
        if (stem, ext) in stems:
            problems.append(f"two generated brands named {stem}{ext}: {stems[(stem, ext)]} and {main} "
                            "(the editor's Prebuild refuses this too)")
            continue
        stems[(stem, ext)] = main
        brands.append((main, stem, ext))
    for main, stem, ext in sorted(brands):
        new_stem = f"{stem}_{suffix}"
        new = f"ssl/{new_stem}{ext}"
        if (mods / new).exists() or (mods / (new + ".resource")).exists():
            problems.append(f"{new} already exists in the project")
        renames[main] = new
        renames[main + ".resource"] = new + ".resource"
        if stem in identifiers and identifiers[stem] != new_stem:
            problems.append(f"identifier {stem} would map twice")
        identifiers[stem] = new_stem
        if ext == ".sso":
            identifiers[class_name(stem)] = class_name(new_stem)
            simple = "".join(w[:1].upper() + w[1:] for w in stem.split("_") if w)
            if simple != class_name(stem):
                report.setdefault("notes", []).append(
                    f"{stem}: class name {class_name(stem)} (editor rule), not {simple} (naive camel case)")
        report["renames"].append({"from": main, "to": new, "kind": ext[1:]})
        report["renames"].append({"from": main + ".resource", "to": new + ".resource", "kind": ext[1:] + ".resource"})
    report["identifiers"] = dict(sorted(identifiers.items()))
    staged_mains = {b[0] for b in brands}
    for path in _walk(mods, []):
        rel = _rel(path, mods)
        split = _brand_split(rel[: -len(".resource")] if rel.endswith(".resource") else rel)
        if split and not rel.endswith(".resource") and rel not in staged_mains:
            report["notStaged"].append({"file": rel, "reason": "not reachable from the roots; left in place, not packed"})
    if problems:
        return report

    renamer = Renamer(renames, identifiers)
    skip = tuple(s.lower() for s in skip_suffixes)
    mod_inside = mod_path is not None and project in mod_path.parents
    written: list[tuple[Path, bytes | Path]] = []
    for path in _walk(project, [out]):
        rel_project = _rel(path, project)
        if path.name.lower().endswith(skip):
            report["skipped"].append(rel_project)
            continue
        in_mods = mods in path.parents
        rel = _rel(path, mods) if in_mods else None
        target_rel = rel_project
        if in_mods and rel in renames:
            target_rel = "mods_source/" + renames[rel]
        data: bytes | None = None
        if in_mods and _is_text(rel):
            text = _read_text(path)
            if text is not None:
                new_text, n_paths, n_ids = renamer.apply(text)
                if new_text != text or target_rel != rel_project:
                    data = new_text.encode("utf-8")
                if new_text != text:
                    report["rewritten"].append({"file": target_rel, "from": rel_project, "paths": n_paths,
                                                "identifiers": n_ids, "sha256": _sha(data)})
        elif not in_mods and (path.name in PROJECT_FILE_NAMES or path.suffix.lower() in PROJECT_FILE_EXTS):
            text = _read_text(path)
            if text is not None:
                new_text, info = _retarget_project_text(text, project, out)
                if new_text != text:
                    data = new_text.encode("utf-8")
                info["file"] = rel_project
                report["projectFiles"].append(info)
        written.append((out / target_rel, data if data is not None else path))

    if mod_path is not None and not mod_inside:
        new_text, n_paths, n_ids = renamer.apply(mod_text or "")
        staged_mod = out / mod_path.name
        written.append((staged_mod, new_text.encode("utf-8")))
        report["rewritten"].append({"file": mod_path.name, "from": str(mod_path), "paths": n_paths,
                                    "identifiers": n_ids, "sha256": _sha(new_text.encode("utf-8"))})
        report["modFile"] = {"source": str(mod_path), "staged": str(staged_mod)}
    elif mod_path is not None:
        report["modFile"] = {"source": str(mod_path), "staged": str(out / _rel(mod_path, project))}

    staged_roots = []
    for tag in root_tags:
        rel = _tag_path(tag)
        staged_roots.append("res://" + renames.get(rel, rel))
    report["roots"] = staged_roots
    if roots is None and mod_text is not None:
        staged_assets = ["res://" + _tag_path(a) for a in read_mod_assets(renamer.apply(mod_text)[0])]
        if staged_assets != staged_roots:
            problems.append("the staged .mod assets do not match the staged roots")

    # links that still point into autogen*/ from a file the packer will read
    staged_text: dict[str, str] = {}
    for target, source in written:
        if target.relative_to(out).parts[0] != "mods_source":
            continue
        rel = target.relative_to(out / "mods_source").as_posix()
        if _is_text(rel):
            staged_text[rel] = source.decode("utf-8") if isinstance(source, bytes) else (_read_text(source) or "")
    reachable = _staged_closure(staged_text, staged_roots)
    for rel in reachable:
        for link in sorted(set(LINK.findall(staged_text.get(rel, "")))):
            link_rel = _tag_path(link)
            if link_rel.split("/", 1)[0].lower().startswith("autogen"):
                report["unmapped"].append({"file": rel, "link": "res://" + link_rel,
                                           "reason": "still links into autogen*/ after staging"})
            elif f"_{suffix}." in link_rel.rsplit("/", 1)[-1] and link_rel not in staged_text \
                    and not (mods / link_rel).exists():
                report["unmapped"].append({"file": rel, "link": "res://" + link_rel, "reason": "dangling suffixed link"})
    leftovers = []
    pattern = _path_pattern(project)
    for target, source in written:
        if target.relative_to(out).parts[0] == "mods_source":
            continue
        if target.name in PROJECT_FILE_NAMES or target.suffix.lower() in PROJECT_FILE_EXTS:
            text = source.decode("utf-8", "replace") if isinstance(source, bytes) else (_read_text(source) or "")
            if pattern.search(text):
                leftovers.append(target.relative_to(out).as_posix())
    for rel in leftovers:
        report["unmapped"].append({"file": rel, "link": str(project), "reason": "still names the source project"})
    if not report["renames"]:
        report.setdefault("notes", []).append("no generated class is reachable from the roots: nothing to stage")

    if problems or dry_run:
        return report
    out.mkdir(parents=True, exist_ok=True)
    total = 0
    for target, source in written:
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(source, bytes):
            target.write_bytes(source)
            total += len(source)
        else:
            shutil.copyfile(source, target)
            total += target.stat().st_size
    report["copied"] = {"files": len(written), "bytes": total}
    return report


def _staged_closure(texts: dict[str, str], roots: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    queue = [_tag_path(r) for r in roots]
    while queue:
        rel = queue.pop()
        if rel in seen or rel not in texts:
            continue
        seen.add(rel)
        for candidate in (rel, rel[: -len(".resource")] if rel.endswith(".resource") else None):
            if candidate and candidate in texts:
                seen.add(candidate)
                queue.extend(_tag_path(l) for l in LINK.findall(texts[candidate]))
    return sorted(seen)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="roadcraft pak stage", description=__doc__.split("\n\n")[0])
    parser.add_argument("--project", required=True, help="editor project folder (contains .project and mods_source)")
    parser.add_argument("--out", required=True, help="new staging folder (must not exist or be empty)")
    parser.add_argument("--suffix", required=True, help="the mod's short class suffix, e.g. kgs25 (ssl/<stem>_<suffix>)")
    parser.add_argument("--mod-file", help="the mod's .mod (its assets are the roots; a staged copy is written)")
    parser.add_argument("--root", action="append", help="a res:// root tag instead of the .mod assets (repeatable)")
    parser.add_argument("--apply", action="store_true", help="write the staging folder (default: dry-run plan)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = stage(args.project, args.out, args.suffix, mod_file=args.mod_file, roots=args.root,
                   dry_run=not args.apply)
    if args.json:
        print(json.dumps(report, indent=1, sort_keys=True))
    else:
        print(f"{'planned' if report['dryRun'] else 'staged'}: {len(report['renames']) // 2} class(es), "
              f"{len(report['rewritten'])} file(s) rewritten, {len(report['unmapped'])} unmapped, "
              f"{len(report['problems'])} problem(s)")
        for item in report["problems"]:
            print("  problem:", item)
        for item in report["unmapped"]:
            print("  unmapped:", item)
    if report["problems"]:
        return 2
    return 1 if report["unmapped"] else 0


if __name__ == "__main__":
    sys.exit(main())
