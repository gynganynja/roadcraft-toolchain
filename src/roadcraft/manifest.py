"""Capture a reproducible manifest of explicitly selected source trees."""

from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath
import stat
from typing import Any, Sequence

from .core import RoadcraftError, sha256_file


def _relative(value: str) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise RoadcraftError("manifest input must be a nonempty relative path")
    normalized = value.replace("\\", "/")
    if (PurePosixPath(normalized).is_absolute() or PureWindowsPath(value).drive or
            any(part in ("", ".", "..") for part in normalized.split("/"))):
        raise RoadcraftError(f"manifest input escapes its root: {value!r}")
    return Path(*PurePosixPath(normalized).parts)


def _safe_path(root: Path, path: Path) -> None:
    current = root
    for part in path.relative_to(root).parts:
        current = current / part
        info = current.lstat()
        attributes = getattr(info, "st_file_attributes", 0)
        if current.is_symlink() or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
            raise RoadcraftError(f"manifest path contains a link or reparse point: {current}")


def capture_tree_manifest(source_root: str | Path, inputs: Sequence[str]) -> dict[str, Any]:
    """Hash files under named inputs; reject links and unstable reads.

    Inputs may name files or directories.  Only those inputs are captured, so
    an accepted source manifest never silently grows to include logs or builds.
    """
    root = Path(source_root).resolve(strict=True)
    if not root.is_dir() or not inputs:
        raise RoadcraftError("source root must be a directory with explicit inputs")
    selected: dict[str, Path] = {}
    for raw in inputs:
        relative = _relative(raw)
        selected_path = root / relative
        _safe_path(root, selected_path)
        if selected_path.is_file():
            items = [selected_path]
        elif selected_path.is_dir():
            items = []
            for entry in sorted(selected_path.rglob("*"),
                                key=lambda p: p.relative_to(root).as_posix().casefold()):
                _safe_path(root, entry)
                if entry.is_file():
                    items.append(entry)
        else:
            raise RoadcraftError(f"manifest input is not a regular file or directory: {raw}")
        for item in items:
            _safe_path(root, item)
            key = item.relative_to(root).as_posix()
            if key.casefold() in selected:
                raise RoadcraftError(f"overlapping or case-colliding input: {key}")
            selected[key.casefold()] = item
    rows = []
    for item in sorted(selected.values(), key=lambda p: p.relative_to(root).as_posix().casefold()):
        before = item.stat()
        digest = sha256_file(item)
        after = item.stat()
        if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) !=
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
            raise RoadcraftError(f"source changed while hashing: {item}")
        rows.append({"path": item.relative_to(root).as_posix(),
                     "bytes": after.st_size, "sha256": digest})
    return {"schemaVersion": 1, "sourceRoot": str(root),
            "inputs": list(inputs), "files": rows}
