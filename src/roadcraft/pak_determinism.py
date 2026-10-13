"""Deterministic mod paks: rewrite only the fields that change between two builds of the same input.

``mod_pak_builder.exe`` is CPython 3.7 ``zipfile`` (``ZipFile(out, 'w', compresslevel=1)``) driven by
a resource-graph walk (library/deterministic-paks.md).  Member order, names, compression method and
the level-1 deflate streams are a deterministic function of the inputs, but each member is stamped
by ``ZipInfo.from_file`` with:

* the MS-DOS time/date of its *source file's* mtime (local header +10, central record +12).  Copied
  sources keep their own mtime, regenerated ``.resource``/``.cls`` files get the export time, and the
  ``pct/*.pct_mip``/``_tile`` slices and rewritten ``.pct.resource`` come from temp files written
  during the build, so even touching every input to a fixed time is not enough;
* ``external_attr = st_mode << 16`` (``0x81B60000`` for a writable file, ``0x81240000`` for a
  read-only one) and the host byte of "version made by" (0 on Windows, 3 elsewhere).

:func:`normalize` copies the archive and overwrites only those fixed-width fields in place: DOS
time/date to 1980-01-01 00:00:00 in every local and central header, the central ``external_attr``
to the regular-file value the SDK writes on Windows (``0x81B60000``; directories ``0x41FF0010``),
the central host byte to 0 (MS-DOS) and the time values inside timestamp extra fields
(``0x5455``, ``0x000A``, ``0x5855``) to zero.  No data is recompressed, no offset or size moves,
member order and duplicate occurrences (the SDK writes ``*.tpl_markup`` twice) stay byte for byte,
and ZIP64 archives keep their records.  The copy is then verified: every byte outside the patched
fields equals the source, each member's CRC-32 is checked on read and its decompressed SHA-256
equals the source member's.

Why the game still loads a normalized pak (evidence grade **Inferred** until a normalized pak is
loaded in game): retail paks under ``root/paks`` carry DOS date/time 0 in every header, so the
engine's pak layer cannot depend on member timestamps; its ``.pak.cache`` index records only offset,
sizes, method and CRC; and a user repack with different timestamps (Jimny v6, level-6 deflate) is
installed and loads.  Normalization changes nothing those readers use.

Read-only towards the source; the destination must not exist and is published atomically.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import struct
import sys
from typing import Any, Iterator, Sequence
from uuid import uuid4
import zipfile

from .core import RoadcraftError, _require_local_path, sha256_file

DOS_TIME = 0                                  # 00:00:00
DOS_DATE = (0 << 9) | (1 << 5) | 1            # 1980-01-01, the earliest valid DOS date
FILE_ATTR = 0x81B60000                        # S_IFREG | 0o666, what the SDK builder writes on Windows
DIR_ATTR = (0o40777 << 16) | 0x10             # S_IFDIR | 0o777 plus the MS-DOS directory bit
CREATE_SYSTEM = 0                             # MS-DOS host, as written by CPython on Windows
_CD_SIG, _LOCAL_SIG, _EOCD_SIG = b"PK\x01\x02", b"PK\x03\x04", b"PK\x05\x06"
_Z64_LOCATOR, _Z64_EOCD = b"PK\x06\x07", b"PK\x06\x06"


class PakDeterminismError(RoadcraftError):
    """The archive is malformed, unsupported, or failed verification."""


def _locate_central_directory(stream, size: int) -> tuple[int, int, int]:
    """(offset, size, entry count) of the central directory; ZIP64 aware."""
    tail = min(size, 0xFFFF + 22)
    stream.seek(size - tail)
    buf = stream.read(tail)
    at = buf.rfind(_EOCD_SIG)
    if at < 0 or at + 22 > len(buf):
        raise PakDeterminismError("no end-of-central-directory record")
    eocd = size - tail + at
    _, disk, cd_disk, _, total, cd_size, cd_off, _ = struct.unpack_from("<IHHHHIIH", buf, at)
    if 0xFFFFFFFF in (cd_off, cd_size) or total == 0xFFFF:
        if eocd < 20:
            raise PakDeterminismError("ZIP64 locator missing")
        stream.seek(eocd - 20)
        locator = stream.read(20)
        if locator[:4] != _Z64_LOCATOR:
            raise PakDeterminismError("ZIP64 locator missing")
        stream.seek(struct.unpack_from("<Q", locator, 8)[0])
        record = stream.read(56)
        if record[:4] != _Z64_EOCD:
            raise PakDeterminismError("ZIP64 end-of-central-directory record missing")
        disk, cd_disk = struct.unpack_from("<II", record, 16)
        total, cd_size, cd_off = struct.unpack_from("<QQQ", record, 32)
    if disk or cd_disk:
        raise PakDeterminismError("multi-disk archives are not supported")
    if cd_off + cd_size > eocd:
        raise PakDeterminismError("central directory overlaps its end record (prefixed archive?)")
    return cd_off, cd_size, total


def _iter_extra(data: bytes) -> Iterator[tuple[int, int, int]]:
    """(header id, payload start, payload length) of each well-formed extra block."""
    pos = 0
    while pos + 4 <= len(data):
        hid, length = struct.unpack_from("<HH", data, pos)
        if pos + 4 + length > len(data):
            return
        yield hid, pos + 4, length
        pos += 4 + length


def read_central_directory(path: str | Path) -> list[dict[str, Any]]:
    """Every central-directory record in archive order, duplicates included.

    Reads only the end records and the central directory (no member data), so it is cheap on
    multi-GB retail paks and on a network share.  ``index`` is the record's position, which equals
    the position in ``zipfile.ZipFile.infolist()``.
    """
    path = Path(path)
    try:
        with path.open("rb") as stream:
            size = stream.seek(0, os.SEEK_END)
            cd_off, cd_size, total = _locate_central_directory(stream, size)
            stream.seek(cd_off)
            cd = stream.read(cd_size)
    except OSError as exc:
        raise PakDeterminismError(f"cannot read {path}: {exc}") from exc
    rows: list[dict[str, Any]] = []
    pos = 0
    while pos < len(cd):
        if cd[pos:pos + 4] != _CD_SIG:
            raise PakDeterminismError(f"{path}: bad central directory record at +{pos}")
        (made, need, flags, method, dos_time, dos_date, crc, csize, usize, nlen, elen, clen,
         disk, iattr, eattr, lho) = struct.unpack_from("<HHHHHHIIIHHHHHII", cd, pos + 4)
        raw_name = cd[pos + 46:pos + 46 + nlen]
        extra = cd[pos + 46 + nlen:pos + 46 + nlen + elen]
        if 0xFFFFFFFF in (usize, csize, lho):
            for hid, start, length in _iter_extra(extra):
                if hid != 0x0001:
                    continue
                values = list(struct.unpack_from("<%dQ" % (length // 8), extra, start))
                if usize == 0xFFFFFFFF and values:
                    usize = values.pop(0)
                if csize == 0xFFFFFFFF and values:
                    csize = values.pop(0)
                if lho == 0xFFFFFFFF and values:
                    lho = values.pop(0)
                break
        rows.append({"index": len(rows), "name": raw_name.decode("utf-8" if flags & 0x800 else "cp437"),
                     "rawName": raw_name, "versionMadeBy": made, "versionNeeded": need, "flags": flags,
                     "method": method, "dosTime": dos_time, "dosDate": dos_date, "crc32": crc,
                     "compressedBytes": csize, "bytes": usize, "internalAttr": iattr,
                     "externalAttr": eattr, "localHeaderOffset": lho, "centralOffset": cd_off + pos,
                     "extra": extra})
        pos += 46 + nlen + elen + clen
    if len(rows) != total:
        raise PakDeterminismError(f"{path}: central directory holds {len(rows)} records, end record says {total}")
    return rows


def _zero_timestamp_extras(extra: bytes, base: int) -> list[tuple[int, bytes, str]]:
    """Patches that zero the time values of known timestamp extra blocks (sizes unchanged)."""
    patches = []
    for hid, start, length in _iter_extra(extra):
        if hid == 0x5455 and length >= 1:                       # extended timestamp: flags + u32 times
            count = (length - 1) // 4
            if count:
                patches.append((base + start + 1, bytes(4 * count), "timestampExtra"))
        elif hid == 0x000A and length >= 4:                     # NTFS: reserved, then tagged attributes
            pos = start + 4
            while pos + 4 <= start + length:
                tag, size = struct.unpack_from("<HH", extra, pos)
                if tag == 1 and size == 24 and pos + 4 + 24 <= start + length:
                    patches.append((base + pos + 4, bytes(24), "timestampExtra"))
                pos += 4 + size
        elif hid == 0x5855 and length >= 8:                     # old Info-ZIP Unix: atime, mtime
            patches.append((base + start, bytes(8), "timestampExtra"))
    return patches


def _plan(path: Path) -> tuple[list[dict[str, Any]], list[tuple[int, bytes, str, int]]]:
    """Central records and every (offset, new bytes, field, member index) patch that changes a byte."""
    entries = read_central_directory(path)
    patches: list[tuple[int, bytes, str, int]] = []
    with path.open("rb") as stream:
        for e in entries:
            if e["flags"] & 0x01:
                raise PakDeterminismError(f"encrypted member is not supported: {e['name']}")
            stream.seek(e["localHeaderOffset"])
            local = stream.read(30)
            if len(local) < 30 or local[:4] != _LOCAL_SIG:
                raise PakDeterminismError(f"bad local header for {e['name']} at {e['localHeaderOffset']}")
            lnlen, lelen = struct.unpack_from("<HH", local, 26)
            lname = stream.read(lnlen)
            lextra = stream.read(lelen)
            if lname != e["rawName"]:
                raise PakDeterminismError(f"local and central names differ: {e['name']}")
            lho, cdo = e["localHeaderOffset"], e["centralOffset"]
            stamp = struct.pack("<HH", DOS_TIME, DOS_DATE)
            wanted: list[tuple[int, bytes, str]] = [(lho + 10, stamp, "dosTimestamp")]
            wanted.append((cdo + 12, stamp, "dosTimestamp"))
            wanted.append((cdo + 5, bytes([CREATE_SYSTEM]), "createSystem"))
            attr = DIR_ATTR if e["name"].endswith("/") else FILE_ATTR
            wanted.append((cdo + 38, struct.pack("<I", attr), "externalAttr"))
            wanted += _zero_timestamp_extras(lextra, lho + 30 + lnlen)
            wanted += _zero_timestamp_extras(e["extra"], cdo + 46 + len(e["rawName"]))
            for offset, data, field in wanted:
                stream.seek(offset)
                if stream.read(len(data)) != data:
                    patches.append((offset, data, field, e["index"]))
    return entries, sorted(patches)


def _member_digests(path: Path) -> list[tuple[str, int, int, int, int, str]]:
    """(name, method, crc, compressed, size, sha256 of content) per member, CRC-checked by zipfile."""
    rows = []
    try:
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                digest = sha256()
                with archive.open(info) as member:
                    for block in iter(lambda: member.read(4 * 1024 * 1024), b""):
                        digest.update(block)
                rows.append((info.filename, info.compress_type, info.CRC, info.compress_size,
                             info.file_size, digest.hexdigest()))
    except (zipfile.BadZipFile, OSError, RuntimeError, NotImplementedError) as exc:
        raise PakDeterminismError(f"{path}: member verification failed: {exc}") from exc
    return rows


def _verify_bytes(source: Path, output: Path, patches: list[tuple]) -> None:
    """The output equals the source with exactly ``patches`` applied, and nothing else."""
    block = 4 * 1024 * 1024
    with source.open("rb") as a, output.open("rb") as b:
        start, cursor = 0, 0
        while True:
            left, right = a.read(block), b.read(block)
            if len(left) != len(right):
                raise PakDeterminismError("output size differs from the source")
            if not left:
                return
            end = start + len(left)
            expected = bytearray(left)
            index = cursor
            while index < len(patches) and patches[index][0] < end:
                offset, data = patches[index][0], patches[index][1]
                lo, hi = max(offset, start), min(offset + len(data), end)
                if lo < hi:
                    expected[lo - start:hi - start] = data[lo - offset:hi - offset]
                index += 1
            while cursor < len(patches) and patches[cursor][0] + len(patches[cursor][1]) <= end:
                cursor += 1
            if bytes(expected) != right:
                raise PakDeterminismError(
                    f"output differs from the source outside the patched fields in bytes {start}-{end}")
            start = end


def _publish(temporary: Path, destination: Path) -> None:
    """Move into place without ever replacing an existing destination."""
    if os.name == "nt":
        os.rename(temporary, destination)  # raises FileExistsError if the destination appeared
    else:
        os.link(temporary, destination)
        temporary.unlink()


def normalize(src_pak: str | Path, dst_pak: str | Path) -> dict[str, Any]:
    """Write a normalized copy of ``src_pak`` to ``dst_pak`` (which must not exist); see module doc."""
    source = Path(src_pak)
    if not source.is_file():
        raise PakDeterminismError(f"source pak does not exist: {source}")
    destination = _require_local_path(dst_pak).absolute()
    if destination.exists() or destination.is_symlink():
        raise PakDeterminismError(f"refusing to overwrite existing output: {destination}")
    if not destination.parent.is_dir():
        raise PakDeterminismError(f"output directory does not exist: {destination.parent}")
    before = source.stat()
    entries, patches = _plan(source)
    source_members = _member_digests(source)
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.partial")
    try:
        with source.open("rb") as reader, temporary.open("xb") as writer:
            shutil.copyfileobj(reader, writer, 4 * 1024 * 1024)
        after = source.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise PakDeterminismError("source changed while it was copied")
        with temporary.open("r+b") as stream:
            for offset, data, _, _ in patches:
                stream.seek(offset)
                stream.write(data)
        _verify_bytes(source, temporary, patches)
        if _member_digests(temporary) != source_members:
            raise PakDeterminismError("member content, CRC, size or order changed")
        result = check(temporary, hash_file=False)
        if not result["normalized"]:
            raise PakDeterminismError(f"output is still not normalized: {result['nonNormal']}")
        output_sha = sha256_file(temporary)
        _publish(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    fields: dict[str, int] = {}
    for _, _, field, _ in patches:
        fields[field] = fields.get(field, 0) + 1
    names = [e["name"] for e in entries]
    return {"source": str(source), "sourceSha256": sha256_file(source), "output": str(destination),
            "outputSha256": output_sha, "bytes": before.st_size, "members": len(entries),
            "duplicateOccurrences": len(names) - len(set(names)), "patchedFields": dict(sorted(fields.items())),
            "verified": {"bytesOutsidePatchedFields": "identical", "memberCrc32": "checked",
                         "memberContentSha256": "identical", "memberOrder": "identical"}}


def check(pak: str | Path, *, hash_file: bool = True) -> dict[str, Any]:
    """Whether ``pak`` already has every normalized field (no change would be made by normalize)."""
    path = Path(pak)
    entries, patches = _plan(path)
    members: dict[str, set[int]] = {}
    for _, _, field, index in patches:
        members.setdefault(field, set()).add(index)
    counts = {field: len(found) for field, found in sorted(members.items())}
    examples = {field: [entries[i]["name"] for i in sorted(found)[:5]] for field, found in sorted(members.items())}
    names = [e["name"] for e in entries]
    result = {"path": str(path), "bytes": path.stat().st_size, "members": len(entries),
              "duplicateOccurrences": len(names) - len(set(names)), "normalized": not patches,
              "nonNormal": counts, "examples": examples}
    if hash_file:
        result["sha256"] = sha256_file(path)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    """``[pak] normalize <src> <dst>`` or ``[pak] check <pak>...``; prints JSON."""
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["pak"]:
        args = args[1:]
    parser = argparse.ArgumentParser(prog="roadcraft pak", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="action", required=True)
    norm = sub.add_parser("normalize", help="write a normalized copy (refuses to overwrite)")
    norm.add_argument("src")
    norm.add_argument("dst")
    chk = sub.add_parser("check", help="report whether paks are already normalized")
    chk.add_argument("paks", nargs="+")
    chk.add_argument("--no-hash", action="store_true", help="skip the whole-file SHA-256")
    ns = parser.parse_args(args)
    try:
        if ns.action == "normalize":
            report: Any = normalize(ns.src, ns.dst)
            code = 0
        else:
            report = [check(p, hash_file=not ns.no_hash) for p in ns.paks]
            code = 0 if all(r["normalized"] for r in report) else 1
            report = report[0] if len(report) == 1 else report
    except (RoadcraftError, OSError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
