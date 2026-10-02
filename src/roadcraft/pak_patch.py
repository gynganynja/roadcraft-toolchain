"""Patch text members of a built mod package without a native rebuild, copying every other member
byte for byte (raw compressed data, headers, order and duplicate occurrences preserved).

The game reads several text resources from the package at load: the compiled truck class
(``ssl/auto_<truck>_<mod>.cls``: suspension, tracks, wheels), wheel classes and the model markup
(``models/mods/<tpl>.tpl.asset/<tpl>.tpl_markup``: body masses, centres of mass, constraints; the
compiled ``.tpl`` holds none of them).  KGS25 fixes 1 and 2 (2026-10-02) were built this way from the
installed candidate.  Retail exports may hold a markup twice: every occurrence is patched.

This changes a package only; keep the editor sources (BRO, generated classes, markup) in step and
regenerate natively when the project's own pipeline is next run.  library/build-pipeline.md.
"""

from __future__ import annotations

import hashlib
import struct
import zipfile
import zlib
from pathlib import Path
from typing import Callable

TextPatch = Callable[[str], str]


class PakPatchError(ValueError):
    """The archive layout is unsupported, a patch did not apply, or verification failed."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_entries(path: str | Path) -> tuple[list[dict], bytes]:
    """Central-directory entries with their local header fields and raw (compressed) data."""
    blob = Path(path).read_bytes()
    eocd = blob.rfind(b"PK\x05\x06")
    if eocd < 0:
        raise PakPatchError("no end of central directory")
    _, disk, cd_disk, n_disk, n_total, _, cd_off, comment_len = struct.unpack_from("<IHHHHIIH", blob, eocd)
    if disk or cd_disk or n_disk != n_total or cd_off == 0xFFFFFFFF:
        raise PakPatchError("multi-disk or zip64 archives are not supported")
    entries, pos = [], cd_off
    for _ in range(n_total):
        (sig, ver_made, ver_need, flag, method, mtime, mdate, crc, csize, usize, nlen, elen, clen, disk_start,
         iattr, eattr, loff) = struct.unpack_from("<IHHHHHHIIIHHHHHII", blob, pos)
        if sig != 0x02014B50:
            raise PakPatchError("bad central directory record")
        name = blob[pos + 46:pos + 46 + nlen]
        extra = blob[pos + 46 + nlen:pos + 46 + nlen + elen]
        comment = blob[pos + 46 + nlen + elen:pos + 46 + nlen + elen + clen]
        lsig, _, lflag, _, _, _, _, _, _, lnlen, lelen = struct.unpack_from("<IHHHHHIIIHH", blob, loff)
        if lsig != 0x04034B50 or lflag & 0x08 or flag & 0x01:
            raise PakPatchError("encrypted members or data descriptors are not supported")
        data_off = loff + 30 + lnlen + lelen
        entries.append({"name": name, "extra": extra, "comment": comment, "ver_made": ver_made,
                        "ver_need": ver_need, "flag": flag, "method": method, "mtime": mtime, "mdate": mdate,
                        "crc": crc, "usize": usize, "disk_start": disk_start, "iattr": iattr, "eattr": eattr,
                        "lname": blob[loff + 30:loff + 30 + lnlen], "lextra": blob[loff + 30 + lnlen:data_off],
                        "raw": blob[data_off:data_off + csize]})
        pos += 46 + nlen + elen + clen
    return entries, blob[eocd + 22:eocd + 22 + comment_len]


def _uncompressed(entry: dict) -> bytes:
    if entry["method"] == 0:
        return entry["raw"]
    if entry["method"] == 8:
        return zlib.decompress(entry["raw"], -15)
    raise PakPatchError(f"unsupported compression method {entry['method']}")


def _write(path: Path, entries: list[dict], comment: bytes) -> None:
    out, central = bytearray(), bytearray()
    for e in entries:
        offset = len(out)
        out += struct.pack("<IHHHHHIIIHH", 0x04034B50, e["ver_need"], e["flag"], e["method"], e["mtime"],
                           e["mdate"], e["crc"], len(e["raw"]), e["usize"], len(e["lname"]), len(e["lextra"]))
        out += e["lname"] + e["lextra"] + e["raw"]
        central += struct.pack("<IHHHHHHIIIHHHHHII", 0x02014B50, e["ver_made"], e["ver_need"], e["flag"],
                               e["method"], e["mtime"], e["mdate"], e["crc"], len(e["raw"]), e["usize"],
                               len(e["name"]), len(e["extra"]), len(e["comment"]), e["disk_start"], e["iattr"],
                               e["eattr"], offset)
        central += e["name"] + e["extra"] + e["comment"]
    cd_off = len(out)
    out += central
    out += struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, len(entries), len(entries), len(central), cd_off, len(comment))
    out += comment
    if len(out) >= 0xFFFFFFFF:
        raise PakPatchError("the result would need zip64")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(out)
    tmp.replace(path)


def patch_text_members(source: str | Path, output: str | Path, patches: dict[str, TextPatch], *,
                       expected_source_sha256: str | None = None, level: int = 9) -> dict:
    """Write ``output``: ``source`` with each named UTF-8 text member passed through its patch.
    Every occurrence of a named member is patched; every patch must change something."""
    source, output = Path(source), Path(output)
    if output.resolve() == source.resolve():
        raise PakPatchError("output must not overwrite the source package")
    source_sha = _sha(source.read_bytes())
    if expected_source_sha256 and source_sha != expected_source_sha256:
        raise PakPatchError(f"source package is {source_sha}, expected {expected_source_sha256}")
    entries, comment = read_entries(source)
    changed, seen = [], {}
    for e in entries:
        name = e["name"].decode("utf-8")
        if name not in patches:
            continue
        before = _uncompressed(e)
        if zlib.crc32(before) & 0xFFFFFFFF != e["crc"]:
            raise PakPatchError(f"CRC mismatch in the source: {name}")
        after = patches[name](before.decode("utf-8")).encode("utf-8")
        if after == before:
            raise PakPatchError(f"patch changed nothing: {name}")
        if e["method"] == 8:
            comp = zlib.compressobj(level, zlib.DEFLATED, -15)
            e["raw"] = comp.compress(after) + comp.flush()
        else:
            e["raw"] = after
        e.update(crc=zlib.crc32(after) & 0xFFFFFFFF, usize=len(after))
        seen[name] = seen.get(name, 0) + 1
        changed.append({"member": name, "occurrence": seen[name], "beforeSha256": _sha(before),
                        "afterSha256": _sha(after)})
    missing = sorted(set(patches) - set(seen))
    if missing:
        raise PakPatchError("members not in the package: " + ", ".join(missing))
    _write(output, entries, comment)
    report = compare_archives(source, output)
    if report["changedMembers"] != sorted(set(seen)):
        raise PakPatchError(f"unexpected changes: {report['changedMembers']}")
    return {"source": str(source), "sourceSha256": source_sha, "output": str(output),
            "outputSha256": _sha(output.read_bytes()), "changes": changed, **report}


def compare_archives(source: str | Path, output: str | Path) -> dict:
    """Member order, metadata and per-member content of two packages; CRC-tested."""
    with zipfile.ZipFile(source) as a, zipfile.ZipFile(output) as b:
        if b.testzip() is not None:
            raise PakPatchError("CRC failure in the output")
        ia, ib = a.infolist(), b.infolist()
        if [i.filename for i in ia] != [i.filename for i in ib]:
            raise PakPatchError("member list or order differs")
        changed, identical = set(), 0
        for x, y in zip(ia, ib):
            if (x.date_time, x.external_attr, x.compress_type) != (y.date_time, y.external_attr, y.compress_type):
                raise PakPatchError(f"metadata changed: {x.filename}")
            if a.open(x).read() == b.open(y).read():
                identical += 1
            else:
                changed.add(x.filename)
    return {"members": len(ib), "identicalMembers": identical, "changedMembers": sorted(changed)}
