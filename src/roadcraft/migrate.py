"""Copy a pinned accepted source tree into a new asset checkout safely.

The source manifest is authoritative.  Dry run is the default.  An applied
migration verifies every source file before writing, enforces space for the
remaining copy plus a 30 GiB reserve by default, and copies bytes into new
files without preserving hardlinks.  A durable receipt permits resumption
after an interruption; source files are never changed or deleted.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import stat
from typing import Any, Iterator, Mapping
from uuid import uuid4


GIB = 1024 ** 3
DEFAULT_MINIMUM_FREE_BYTES = 30 * GIB
_SHA = re.compile(r"^[0-9a-f]{64}$")


class MigrationError(RuntimeError):
    """The manifest, source, or destination cannot safely be migrated."""


class InsufficientSpaceError(MigrationError):
    """The destination volume lacks copy space plus the configured reserve."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    before = path.stat()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    after = path.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise MigrationError(f"file changed during hashing: {path}")
    return digest.hexdigest()


def _plain(path: Path, label: str) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise MigrationError(f"{label} is missing or unreadable: {path}") from exc
    attributes = getattr(info, "st_file_attributes", 0)
    if path.is_symlink() or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
        raise MigrationError(f"{label} crosses a symlink or reparse point: {path}")


def _resolve_unlinked(value: str | Path, label: str, *, must_exist: bool) -> Path:
    path = Path(value).expanduser().absolute()
    if ".." in path.parts:
        raise MigrationError(f"{label} may not contain parent traversal")
    for part in reversed((path, *path.parents)):
        if part.exists() or part.is_symlink():
            _plain(part, label)
    try:
        return path.resolve(strict=must_exist)
    except OSError as exc:
        raise MigrationError(f"{label} is missing or unreadable: {path}") from exc


def _relative(raw: str) -> str:
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        raise MigrationError("manifest path must be a nonempty string")
    normalized = raw.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (path.is_absolute() or PureWindowsPath(raw).drive or
            any(part in ("", ".", "..") for part in normalized.split("/"))):
        raise MigrationError(f"manifest path escapes source tree: {raw!r}")
    return path.as_posix()


def _source_file(root: Path, relative: str) -> Path:
    path = root
    for part in PurePosixPath(relative).parts:
        path = path / part
        _plain(path, "source file path")
    if not path.is_file() or not path.resolve(strict=True).is_relative_to(root):
        raise MigrationError(f"manifest source is not a regular file: {relative}")
    return path


def _destination_path(root: Path, relative: str) -> Path:
    path = root
    for part in PurePosixPath(relative).parts:
        path = path / part
        if path.exists() or path.is_symlink():
            _plain(path, "destination path")
    if not path.resolve().is_relative_to(root):
        raise MigrationError(f"destination path escapes checkout: {relative}")
    return path


def _validate_manifest(manifest_path: Path, expected_sha256: str,
                       source_root: Path) -> tuple[list[dict[str, Any]], str]:
    if not isinstance(expected_sha256, str) or not _SHA.fullmatch(expected_sha256.lower()):
        raise MigrationError("manifest SHA-256 pin is invalid")
    _plain(manifest_path, "source manifest")
    if _sha(manifest_path) != expected_sha256.lower():
        raise MigrationError("source manifest differs from its pin")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MigrationError("source manifest is unreadable or malformed") from exc
    if (not isinstance(manifest, dict) or manifest.get("schemaVersion") != 1 or
            not isinstance(manifest.get("files"), list) or not manifest["files"]):
        raise MigrationError("source manifest requires schemaVersion 1 and nonempty files")
    if Path(manifest.get("sourceRoot", "")).resolve() != source_root:
        raise MigrationError("source root does not match the pinned manifest")
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in manifest["files"]:
        if not isinstance(row, dict):
            raise MigrationError("source manifest file row is not an object")
        relative = _relative(row.get("path", row.get("relativePath")))
        expected = row.get("sha256")
        size = row.get("bytes")
        if (relative.casefold() in seen or not isinstance(expected, str) or
                not _SHA.fullmatch(expected.lower()) or
                not isinstance(size, int) or size < 0):
            raise MigrationError(f"duplicate or invalid source manifest row: {relative}")
        seen.add(relative.casefold())
        entries.append({"path": relative, "bytes": size,
                        "sha256": expected.lower()})
    return entries, expected_sha256.lower()


def _check_existing_destination(destination: Path, entries: list[dict[str, Any]],
                                receipt_path: Path, manifest_sha256: str,
                                source: Path) -> tuple[dict[str, Any] | None, set[str]]:
    receipt = None
    if receipt_path.exists():
        _plain(receipt_path, "migration receipt")
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise MigrationError("migration receipt is unreadable or malformed") from exc
        if (not isinstance(receipt, dict) or receipt.get("schemaVersion") != 1 or
                receipt.get("manifestSha256") != manifest_sha256 or
                receipt.get("sourceRoot") != str(source) or
                receipt.get("destination") != str(destination) or
                receipt.get("expectedFiles") != len(entries) or
                receipt.get("expectedBytes") != sum(row["bytes"] for row in entries)):
            raise MigrationError("existing migration receipt describes another source or manifest")
    expected = {row["path"]: row for row in entries}
    allowed_directories = {
        PurePosixPath(row["path"]).parent.as_posix()
        for row in entries
    }
    allowed_directories |= {
        parent.as_posix()
        for row in entries
        for parent in PurePosixPath(row["path"]).parents
    }
    existing: set[str] = set()
    if destination.exists():
        _plain(destination, "destination")
        if not destination.is_dir():
            raise MigrationError("destination is not a directory")
        stack = [destination]
        any_item = False
        while stack:
            folder = stack.pop()
            with os.scandir(folder) as scan:
                children = list(scan)
            for item in children:
                any_item = True
                path = Path(item.path)
                _plain(path, "destination item")
                relative = path.relative_to(destination).as_posix()
                if item.is_dir(follow_symlinks=False):
                    if relative not in allowed_directories:
                        raise MigrationError(f"destination contains unmanifested directory: {relative}")
                    stack.append(path)
                    continue
                if not item.is_file(follow_symlinks=False):
                    raise MigrationError(f"destination contains nonregular item: {relative}")
                if relative not in expected:
                    raise MigrationError(f"destination contains unmanifested file: {relative}")
                row = expected[relative]
                if path.stat().st_size != row["bytes"] or _sha(path) != row["sha256"]:
                    raise MigrationError(f"destination file differs from manifest: {relative}")
                existing.add(relative)
        if any_item and receipt is None:
            raise MigrationError("nonempty destination needs a matching migration receipt")
    if receipt and receipt.get("status") == "COMPLETE" and len(existing) != len(entries):
        raise MigrationError("completed migration destination is now missing files")
    return receipt, existing


def _free_bytes(path: Path) -> int:
    existing = path
    while not existing.exists():
        existing = existing.parent
    return shutil.disk_usage(existing).free


def _write_receipt(path: Path, data: Mapping[str, Any]) -> None:
    pending = path.with_name(path.name + ".tmp-" + uuid4().hex)
    try:
        with pending.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, path)
    finally:
        if pending.exists():
            pending.unlink()


@contextmanager
def _migration_lock(receipt_path: Path) -> Iterator[None]:
    """Hold an OS lock that is released automatically if the worker exits."""
    lock_path = receipt_path.with_name(receipt_path.name + ".lock")
    _plain(receipt_path.parent, "receipt directory")
    with lock_path.open("a+b", buffering=0) as stream:
        if stream.seek(0, os.SEEK_END) == 0:
            stream.write(b"\x00")
            os.fsync(stream.fileno())
        stream.seek(0)
        if os.name == "nt":
            import msvcrt

            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise MigrationError(f"migration is already active: {lock_path}") from exc
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise MigrationError(f"migration is already active: {lock_path}") from exc
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _copy_one(source: Path, destination: Path, staging: Path,
              expected_sha256: str, expected_bytes: int) -> None:
    if destination.exists() or destination.is_symlink():
        raise MigrationError(f"destination appeared before copy: {destination}")
    stage = staging / (uuid4().hex + ".pending")
    digest = hashlib.sha256()
    source_before = source.stat()
    copied = 0
    try:
        with source.open("rb") as input_stream, stage.open("xb") as output_stream:
            for block in iter(lambda: input_stream.read(4 * 1024 * 1024), b""):
                digest.update(block)
                output_stream.write(block)
                copied += len(block)
            output_stream.flush()
            os.fsync(output_stream.fileno())
        source_after = source.stat()
        if (source_before.st_dev, source_before.st_ino, source_before.st_size,
            source_before.st_mtime_ns) != (source_after.st_dev, source_after.st_ino,
                                         source_after.st_size, source_after.st_mtime_ns):
            raise MigrationError(f"source changed during copy: {source}")
        if copied != expected_bytes or digest.hexdigest() != expected_sha256 or _sha(stage) != expected_sha256:
            raise MigrationError(f"copied bytes failed manifest verification: {source}")
        os.replace(stage, destination)
        if destination.stat().st_size != expected_bytes or _sha(destination) != expected_sha256:
            raise MigrationError(f"destination failed verification: {destination}")
    finally:
        if stage.exists():
            stage.unlink()


def _create_plain_parents(root: Path, target: Path) -> None:
    current = root
    for part in target.parent.relative_to(root).parts:
        current = current / part
        current.mkdir(exist_ok=True)
        _plain(current, "destination directory")
        if not current.is_dir():
            raise MigrationError(f"destination parent is not a directory: {current}")


def migrate_source_tree(
    manifest_path: str | Path,
    manifest_sha256: str,
    source_root: str | Path,
    destination: str | Path,
    receipt_path: str | Path,
    *,
    minimum_free_bytes: int = DEFAULT_MINIMUM_FREE_BYTES,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Verify, preflight, and optionally copy the exact manifest file set."""
    manifest_file = _resolve_unlinked(manifest_path, "source manifest", must_exist=True)
    source = _resolve_unlinked(source_root, "source root", must_exist=True)
    if not source.is_dir():
        raise MigrationError("source root is not a directory")
    target = _resolve_unlinked(destination, "destination", must_exist=False)
    receipt_file = _resolve_unlinked(receipt_path, "receipt", must_exist=False)
    if (target == source or target.is_relative_to(source) or
            source.is_relative_to(target)):
        raise MigrationError("source and destination overlap")
    if (receipt_file.is_relative_to(source) or receipt_file.is_relative_to(target)):
        raise MigrationError("receipt must be outside source and destination")
    if (not isinstance(minimum_free_bytes, int) or minimum_free_bytes < 0):
        raise MigrationError("minimum free-space reserve must be nonnegative")
    entries, manifest_pin = _validate_manifest(manifest_file, manifest_sha256, source)
    receipt, existing = _check_existing_destination(target, entries, receipt_file,
                                                    manifest_pin, source)
    # Verify every source file before any destination mutation.
    for row in entries:
        path = _source_file(source, row["path"])
        if path.stat().st_size != row["bytes"] or _sha(path) != row["sha256"]:
            raise MigrationError(f"source file differs from pinned manifest: {row['path']}")
    missing = [row for row in entries if row["path"] not in existing]
    remaining = sum(row["bytes"] for row in missing)
    free = _free_bytes(target.parent)
    required = remaining + minimum_free_bytes
    result = {"operation": "migrate-source", "dryRun": dry_run,
              "manifestPath": str(manifest_file), "manifestSha256": manifest_pin,
              "sourceRoot": str(source), "destination": str(target),
              "receiptPath": str(receipt_file), "expectedFiles": len(entries),
              "expectedBytes": sum(row["bytes"] for row in entries),
              "verifiedExistingFiles": len(existing),
              "filesRemaining": len(missing), "bytesRemaining": remaining,
              "freeBytes": free, "requiredFreeBytes": required,
              "minimumFreeBytes": minimum_free_bytes,
              "spaceGatePassed": not missing or free >= required,
              "resuming": receipt is not None}
    if dry_run:
        return result
    if missing and free < required:
        raise InsufficientSpaceError(
            f"destination needs {required} free bytes; only {free} available"
        )
    receipt_file.parent.mkdir(parents=True, exist_ok=True)
    with _migration_lock(receipt_file):
        # Another worker may have finished between preflight and lock
        # acquisition.  Recheck both trees and the space budget under lock.
        receipt, existing = _check_existing_destination(target, entries, receipt_file,
                                                        manifest_pin, source)
        for row in entries:
            path = _source_file(source, row["path"])
            if path.stat().st_size != row["bytes"] or _sha(path) != row["sha256"]:
                raise MigrationError(f"source changed after preflight: {row['path']}")
        missing = [row for row in entries if row["path"] not in existing]
        remaining = sum(row["bytes"] for row in missing)
        free = _free_bytes(target.parent)
        required = remaining + minimum_free_bytes
        result.update({"verifiedExistingFiles": len(existing),
                       "filesRemaining": len(missing), "bytesRemaining": remaining,
                       "freeBytes": free, "requiredFreeBytes": required,
                       "spaceGatePassed": not missing or free >= required,
                       "resuming": receipt is not None})
        if missing and free < required:
            raise InsufficientSpaceError(
                f"destination needs {required} free bytes; only {free} available"
            )
        if receipt is None:
            receipt = {"schemaVersion": 1, "manifestPath": str(manifest_file),
                       "manifestSha256": manifest_pin, "sourceRoot": str(source),
                       "destination": str(target), "expectedFiles": len(entries),
                       "expectedBytes": sum(row["bytes"] for row in entries),
                       "createdAt": _now(), "status": "COPYING"}
        receipt["verifiedFiles"] = len(existing)
        receipt["verifiedBytes"] = sum(row["bytes"] for row in entries
                                        if row["path"] in existing)
        _write_receipt(receipt_file, receipt)
        target.mkdir(parents=True, exist_ok=True)
        staging = target.parent / ("." + target.name + ".roadcraft-staging")
        staging.mkdir(exist_ok=True)
        _plain(staging, "migration staging directory")
        for row in missing:
            source_path = _source_file(source, row["path"])
            output = _destination_path(target, row["path"])
            _create_plain_parents(target, output)
            _copy_one(source_path, output, staging, row["sha256"], row["bytes"])
            receipt["verifiedFiles"] += 1
            receipt["verifiedBytes"] += row["bytes"]
            receipt["lastVerifiedPath"] = row["path"]
            _write_receipt(receipt_file, receipt)
        # Final verification is independent of the progress counters in receipt.
        _, verified = _check_existing_destination(target, entries, receipt_file,
                                                  manifest_pin, source)
        if len(verified) != len(entries):
            raise MigrationError("destination is incomplete after copy")
        receipt["status"] = "COMPLETE"
        receipt["verifiedFiles"] = len(entries)
        receipt["verifiedBytes"] = sum(row["bytes"] for row in entries)
        receipt["completedAt"] = _now()
        _write_receipt(receipt_file, receipt)
        if not any(staging.iterdir()):
            staging.rmdir()
    return {**result, "dryRun": False, "status": "COMPLETE",
            "verifiedExistingFiles": len(entries), "filesRemaining": 0,
            "bytesRemaining": 0}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--minimum-free-gib", type=float, default=30.0)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    result = migrate_source_tree(
        args.manifest, args.manifest_sha256, args.source_root, args.destination,
        args.receipt, minimum_free_bytes=int(args.minimum_free_gib * GIB),
        dry_run=not args.run,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
