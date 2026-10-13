"""Install/override manifest: what every member of one or more mod paks does against retail and other mods.

Read-only.  Only end records and central directories are read (:func:`pak_determinism.read_central_directory`),
so a 650 MB pak on a network share costs a few seeks; member data is streamed only to confirm that two
same-named members with equal CRC-32 and size really hold identical bytes.

Keys are engine resource tags: ``res://`` + member path with ``\\`` -> ``/``, lowercased
(``ResourceTag.MakeFrom``).  Each member occurrence gets a ``status``:

``new``                  no retail pak and no other mod provides the tag
``identical-to-retail``  a retail pak has the tag with identical content (redundant copy)
``shadows-retail``       a retail pak has the tag with different content (``retail`` names pak:member)
``conflicts-with-mod``   no retail copy, but another mod in the set ships the tag (``modConflicts``,
                         each marked identical or different)

``modConflicts`` is filled for every status.  Engine precedence (library/install-manifest.md): mod paks
are appended as layers in index mode 1, which replaces an existing tag only when the tag's directory is
one of ``TagDirsToCache`` (``res://``, ``res://ssl/``, ``res://pct/``, ``res://td/``,
``res://sounds/events/``, matched on the tag's immediate directory) and otherwise keeps the earlier
layer's entry.  So a member that shadows retail is flagged ``effective`` in those directories and
``probably ignored`` elsewhere, grade **Inferred** (decompiled retail executable, not tested in game).
A mod-vs-mod conflict is ``order-dependent`` (mod load order is **Open**); the game logs
"Resource %s also exists in mod %s" for both sides (**Retail**, decompiled).

The retail index can be cached under a caller-chosen directory; the cache is keyed by every retail
pak's relative path, size and mtime plus the configured layer order, and is rebuilt on any change.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Sequence
from uuid import uuid4
import zipfile

from .core import RoadcraftError, read_config
from .pak_determinism import read_central_directory

INDEX_SCHEMA = 1
MANIFEST_SCHEMA = 1
CACHED_DIRS = ("res://", "res://ssl/", "res://pct/", "res://td/", "res://sounds/events/")
EFFECT_SOURCE = "Retail.exe FUN_14282adc0 (mod layer, index mode 1) vs FUN_14282a930 (retail, mode 0)"


def tag_of(member: str) -> str:
    return "res://" + member.replace("\\", "/").lower()


def _tag_dir(tag: str) -> str:
    return tag.rsplit("/", 1)[0] + "/"


def paks_dir(game_root: str | Path) -> Path:
    """``<game>/root/paks`` (or ``<root>/paks`` when given the ``root`` folder itself)."""
    game_root = Path(game_root)
    for candidate in (game_root / "root" / "paks", game_root / "paks"):
        if candidate.is_dir():
            return candidate
    raise RoadcraftError(f"no root/paks folder under {game_root}")


def retail_pak_order(game_root: str | Path) -> list[str]:
    """Retail paks (posix paths relative to root/paks): ``ResourceManager.TagLayers`` ``PakName``
    entries of ``root/config/editor/convert.cfg`` first, then every other ``*.pak``, sorted."""
    base = paks_dir(game_root)
    found = sorted(p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file()
                   and p.suffix.lower() == ".pak")
    by_lower = {p.lower(): p for p in found}
    order: list[str] = []
    cfg = base.parent / "config" / "editor" / "convert.cfg"
    if cfg.is_file():
        in_layers = False
        for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
            if re.match(r"^\s{2}TagLayers:\s*$", line):
                in_layers = True
                continue
            if in_layers and re.match(r"^\s{2}\S", line) and not line.strip().startswith("-"):
                break
            match = re.search(r"PakName:\s*(.+?\.pak)\s*$", line) if in_layers else None
            if match:
                rel = by_lower.get(match.group(1).replace("\\", "/").lower())
                if rel and rel not in order:
                    order.append(rel)
    return order + [p for p in found if p not in order]


def _index_key(game_root: str | Path) -> list[list[Any]]:
    base = paks_dir(game_root)
    key = []
    for rel in retail_pak_order(game_root):
        info = (base / rel).stat()
        key.append([rel, info.st_size, info.st_mtime_ns])
    return key


def build_retail_index(game_root: str | Path) -> dict[str, Any]:
    """Every retail member: ``tags[tag] = [[pak index, member, crc32, size, cd index], ...]``."""
    base = paks_dir(game_root)
    key = _index_key(game_root)
    tags: dict[str, list[list[Any]]] = {}
    paks = []
    for number, (rel, size, mtime_ns) in enumerate(key):
        rows = read_central_directory(base / rel)
        for row in rows:
            tags.setdefault(tag_of(row["name"]), []).append(
                [number, row["name"], row["crc32"], row["bytes"], row["index"]])
        paks.append({"pak": rel, "bytes": size, "mtimeNs": mtime_ns, "members": len(rows)})
    return {"schemaVersion": INDEX_SCHEMA, "key": key, "paks": paks, "tags": tags}


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def retail_index(game_root: str | Path, cache_dir: str | Path | None = None) -> dict[str, Any]:
    """The retail index, from ``cache_dir`` when its key still matches the installation."""
    key = _index_key(game_root)
    if cache_dir is None:
        return build_retail_index(game_root)
    cache_dir = Path(cache_dir)
    if _inside(cache_dir, Path(game_root)) or _inside(cache_dir, paks_dir(game_root).parent):
        raise RoadcraftError("the retail index cache must not live inside the game folder")
    digest = sha256(json.dumps(key, separators=(",", ":")).encode()).hexdigest()[:16]
    cache = cache_dir / f"retail-index-v{INDEX_SCHEMA}-{digest}.json.gz"
    if cache.is_file():
        try:
            with gzip.open(cache, "rt", encoding="utf-8") as stream:
                index = json.load(stream)
            if index.get("schemaVersion") == INDEX_SCHEMA and index.get("key") == key:
                index["cache"] = {"path": str(cache), "hit": True}
                return index
        except (OSError, ValueError):
            pass
    index = build_retail_index(game_root)
    cache_dir.mkdir(parents=True, exist_ok=True)
    temporary = cache.with_name(f".{cache.name}.{uuid4().hex}.partial")
    with gzip.open(temporary, "wt", encoding="utf-8") as stream:
        json.dump(index, stream, separators=(",", ":"))
    os.replace(temporary, cache)
    index["cache"] = {"path": str(cache), "hit": False}
    return index


class _ContentHasher:
    """SHA-256 of one member occurrence's content, streamed, with open archives reused."""

    def __init__(self) -> None:
        self._archives: dict[str, zipfile.ZipFile] = {}
        self._digests: dict[tuple[str, int], str] = {}

    def __call__(self, path: str | Path, cd_index: int) -> str:
        key = (str(path), cd_index)
        if key not in self._digests:
            archive = self._archives.get(str(path))
            if archive is None:
                archive = self._archives[str(path)] = zipfile.ZipFile(path)
            digest = sha256()
            with archive.open(archive.infolist()[cd_index]) as member:
                for block in iter(lambda: member.read(4 * 1024 * 1024), b""):
                    digest.update(block)
            self._digests[key] = digest.hexdigest()
        return self._digests[key]

    def close(self) -> None:
        for archive in self._archives.values():
            archive.close()
        self._archives.clear()


def _effect(status: str, cached: bool) -> tuple[str, str]:
    if status == "new":
        return "effective", "Game"
    if status == "conflicts-with-mod":
        return "order-dependent", "Inferred"
    return ("effective" if cached else "probably ignored"), "Inferred"


def _expand(targets: Iterable[str | Path]) -> list[Path]:
    """Paks named directly, plus every ``*.pak`` directly inside each named folder (sorted)."""
    paks: list[Path] = []
    for target in targets:
        target = Path(target)
        if target.is_dir():
            paks += sorted((p for p in target.iterdir() if p.is_file() and p.suffix.lower() == ".pak"),
                           key=lambda p: p.name.lower())
        elif target.is_file():
            paks.append(target)
        else:
            raise RoadcraftError(f"not a pak or folder: {target}")
    unique: dict[str, Path] = {}
    for pak in paks:
        unique.setdefault(os.path.normcase(os.path.abspath(pak)), pak)
    return list(unique.values())


def _labels(paks: Sequence[Path]) -> dict[str, str]:
    names = defaultdict(int)
    for pak in paks:
        names[pak.name.lower()] += 1
    return {str(p): (p.name if names[p.name.lower()] == 1 else str(p)) for p in paks}


def _install_receipts(transaction_root: Path, paks: Sequence[Path], labels: dict[str, str]) -> dict[str, Any]:
    """Latest transaction receipt (roadcraft.transaction) for each pak installed at that path."""
    wanted = {os.path.normcase(os.path.abspath(p)): p for p in paks}
    found: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for receipt in sorted(transaction_root.glob("*/receipt.json")):
        try:
            data = json.loads(receipt.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        installed = os.path.normcase(os.path.abspath(str(data.get("installedPath", ""))))
        if installed in wanted:
            events = data.get("events") or [{}]
            found[installed].append({"transactionId": data.get("transactionId"), "state": data.get("state"),
                                     "candidateSha256": data.get("candidateSha256"),
                                     "at": events[-1].get("at")})
    result = {}
    for key, pak in wanted.items():
        rows = sorted(found.get(key, []), key=lambda r: (str(r["at"]), str(r["transactionId"])))
        if not rows:
            continue
        latest = rows[-1]
        current = None
        if latest["state"] == "INSTALLED" and latest["candidateSha256"]:
            digest = sha256()
            with pak.open("rb") as stream:
                for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                    digest.update(block)
            current = digest.hexdigest() == latest["candidateSha256"]
        result[labels[str(pak)]] = {**latest, "receipts": len(rows), "currentBytesMatchCandidate": current}
    return result


def manifest(targets: Sequence[str | Path], game_root: str | Path, *, cache_dir: str | Path | None = None,
             installed: Sequence[str | Path] = (), hash_matches: bool = True,
             transaction_root: str | Path | None = None) -> dict[str, Any]:
    """Per-member manifest for each target pak (folders expand to their ``*.pak``), conflicts against
    each other and against ``installed`` paks (which get no rows of their own), and the whole-set
    cross-mod conflict view.  Output is deterministic for unchanged inputs."""
    mods = _expand(targets)
    if not mods:
        raise RoadcraftError("no mod paks given")
    pool = _expand(list(mods) + list(installed))
    labels = _labels(pool)
    index = retail_index(game_root, cache_dir)
    base = paks_dir(game_root)
    retail_paks = [p["pak"] for p in index["paks"]]
    hasher = _ContentHasher()
    try:
        entries = {str(p): read_central_directory(p) for p in pool}
        providers: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(dict)
        for pak in pool:
            for row in entries[str(pak)]:
                providers[tag_of(row["name"])].setdefault(str(pak), []).append(row)

        def same(a_path: str | Path, a: dict, b_path: str | Path, b_crc: int, b_size: int, b_index: int) -> bool:
            if (a["crc32"], a["bytes"]) != (b_crc, b_size):
                return False
            return not hash_matches or hasher(a_path, a["index"]) == hasher(b_path, b_index)

        reports = []
        for pak in mods:
            rows, counts, occurrence = [], defaultdict(int), defaultdict(int)
            for row in entries[str(pak)]:
                tag = tag_of(row["name"])
                occurrence[tag] += 1
                retail_hits = index["tags"].get(tag, [])
                retail = None
                status = "new"
                if retail_hits:
                    number, member, crc, size, cd_index = retail_hits[0]
                    identical = same(pak, row, base / retail_paks[number], crc, size, cd_index)
                    status = "identical-to-retail" if identical else "shadows-retail"
                    retail = {"pak": retail_paks[number], "member": member, "target": f"{retail_paks[number]}:{member}",
                              "identical": identical, "otherRetailCopies": len(retail_hits) - 1}
                conflicts = []
                for other, other_rows in sorted(providers[tag].items(), key=lambda kv: labels[kv[0]].lower()):
                    if other == str(pak):
                        continue
                    conflicts.append({"mod": labels[other], "member": other_rows[0]["name"],
                                      "identical": all(same(pak, row, other, o["crc32"], o["bytes"], o["index"])
                                                       for o in other_rows)})
                if conflicts and status == "new":
                    status = "conflicts-with-mod"
                cached = _tag_dir(tag) in CACHED_DIRS
                effect, grade = _effect(status, cached)
                counts[status] += 1
                rows.append({"member": row["name"], "occurrence": occurrence[tag], "tag": tag,
                             "crc32": f"{row['crc32']:08x}", "bytes": row["bytes"],
                             "compressedBytes": row["compressedBytes"], "method": row["method"],
                             "status": status, "retail": retail, "modConflicts": conflicts,
                             "engineCachedDir": cached, "effect": effect, "effectGrade": grade})
            reports.append({"mod": labels[str(pak)], "path": str(pak), "bytes": pak.stat().st_size,
                            "members": len(rows), "summary": dict(sorted(counts.items())),
                            "duplicateTags": sorted(t for t, n in occurrence.items() if n > 1),
                            "rows": rows})

        conflicts_view, pairs = [], defaultdict(lambda: {"tags": 0, "identical": 0, "different": 0})
        for tag in sorted(t for t, owners in providers.items() if len(owners) > 1):
            owners = sorted(providers[tag].items(), key=lambda kv: labels[kv[0]].lower())
            first_path, first_rows = owners[0]
            identical = all(same(first_path, first_rows[0], path, r["crc32"], r["bytes"], r["index"])
                            for path, rows_ in owners for r in rows_)
            retail_hits = index["tags"].get(tag, [])
            conflicts_view.append({
                "tag": tag, "identical": identical, "engineCachedDir": _tag_dir(tag) in CACHED_DIRS,
                "alsoRetail": f"{retail_paks[retail_hits[0][0]]}:{retail_hits[0][1]}" if retail_hits else None,
                "providers": [{"mod": labels[path], "member": rows_[0]["name"], "occurrences": len(rows_),
                               "crc32": f"{rows_[0]['crc32']:08x}", "bytes": rows_[0]["bytes"]}
                              for path, rows_ in owners]})
            names = [labels[path] for path, _ in owners]
            for i, left in enumerate(names):
                for right in names[i + 1:]:
                    pair = pairs[(left, right)]
                    pair["tags"] += 1
                    pair["identical" if identical else "different"] += 1
        receipts = (_install_receipts(Path(transaction_root), pool, labels)
                    if transaction_root is not None else None)
    finally:
        hasher.close()
    result = {
        "schemaVersion": MANIFEST_SCHEMA,
        "retail": {"paksDir": str(base), "paks": len(retail_paks),
                   "tags": len(index["tags"]), "order": retail_paks},
        "contentComparison": "crc32+size, confirmed by streamed sha256" if hash_matches else "crc32+size",
        "precedence": {
            "engineCachedDirs": list(CACHED_DIRS),
            "rule": ("mod layer replaces an existing tag only in engineCachedDirs (immediate directory); "
                     "elsewhere the earlier (retail) layer keeps it"),
            "grade": "Inferred", "source": EFFECT_SOURCE,
            "modLoadOrder": "Open",
            "conflictLog": "Resource %s also exists in mod %s (Retail.exe FUN_14280f090; grade Retail)"},
        "mods": reports,
        "install": {"mods": [labels[str(p)] for p in pool], "conflictingTags": len(conflicts_view),
                    "pairs": [{"mods": list(k), **v} for k, v in sorted(pairs.items())],
                    "conflicts": conflicts_view}}
    if receipts is not None:
        result["install"]["receipts"] = receipts
    return result


def dumps(report: dict[str, Any]) -> str:
    """Deterministic JSON (sorted keys, no timestamps)."""
    return json.dumps(report, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def _text(report: dict[str, Any]) -> str:
    lines = [f"retail: {report['retail']['paks']} paks, {report['retail']['tags']} tags"]
    for mod in report["mods"]:
        lines.append(f"{mod['mod']}: {mod['members']} members {mod['summary']} "
                     f"duplicateTags={len(mod['duplicateTags'])}")
        for row in mod["rows"]:
            if row["status"] == "new":
                continue
            where = row["retail"]["target"] if row["retail"] else ", ".join(
                f"{c['mod']}({'identical' if c['identical'] else 'DIFFERENT'})" for c in row["modConflicts"])
            lines.append(f"  {row['status']:20} {row['member']} -> {where} [{row['effect']}, {row['effectGrade']}]")
    install = report["install"]
    lines.append(f"install: {len(install['mods'])} mods, {install['conflictingTags']} conflicting tags")
    for pair in install["pairs"]:
        lines.append(f"  {pair['mods'][0]} <-> {pair['mods'][1]}: {pair['tags']} tags "
                     f"({pair['identical']} identical, {pair['different']} different)")
    for name, receipt in sorted(install.get("receipts", {}).items()):
        lines.append(f"  receipt {name}: {receipt['state']} {receipt['transactionId']} "
                     f"currentMatchesCandidate={receipt['currentBytesMatchCandidate']}")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """``[pak] manifest <pak|mods-dir>... [--json] [--game DIR] [--cache DIR] [--installed DIR]``."""
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["pak"]:
        args = args[1:]
    if args[:1] == ["manifest"]:
        args = args[1:]
    parser = argparse.ArgumentParser(prog="roadcraft pak manifest", description=__doc__.split("\n\n")[0])
    parser.add_argument("targets", nargs="+", help="mod paks and/or mods folders")
    parser.add_argument("--game", help="game folder (with root/paks); default: sdkRoot of --config")
    parser.add_argument("--config", help="machine configuration JSON providing sdkRoot")
    parser.add_argument("--cache", help="directory for the cached retail index")
    parser.add_argument("--installed", action="append", default=[],
                        help="pak or folder checked for conflicts without its own rows (repeatable)")
    parser.add_argument("--transactions", help="transaction root: report each pak's latest install receipt")
    parser.add_argument("--no-hash", action="store_true", help="compare equal-CRC members by CRC32+size only")
    parser.add_argument("--json", action="store_true", help="print the deterministic JSON manifest")
    parser.add_argument("--output", help="write the JSON manifest to this file")
    ns = parser.parse_args(args)
    try:
        game = ns.game
        if game is None and ns.config:
            game = read_config(ns.config).get("sdkRoot")
        if game is None:
            raise RoadcraftError("manifest needs --game or sdkRoot in --config")
        report = manifest(ns.targets, game, cache_dir=ns.cache, installed=ns.installed,
                          hash_matches=not ns.no_hash, transaction_root=ns.transactions)
    except (RoadcraftError, OSError, zipfile.BadZipFile) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    text = dumps(report)
    if ns.output:
        Path(ns.output).write_text(text, encoding="utf-8")
    sys.stdout.write(text if ns.json else _text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
