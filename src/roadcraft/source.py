"""Source identity and export gates for RoadCraft authoring assets.

The D11 build currently consumes repaired ``export.usf`` files.  A historical
``.blend`` file is a useful reference, but it is not an approved replacement
for those files until a complete parity review has passed.  This module keeps
that distinction explicit without embedding a dated project or package hash.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import stat
import tempfile
from typing import Any, Callable, Mapping, Sequence


class SourceError(ValueError):
    """A source declaration, inventory, or export request is unsafe."""


class ExportBlockedError(SourceError):
    """The requested authoring route has not passed its required gates."""


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PARITY_CHECKS = (
    "hierarchy",
    "transforms",
    "geometry",
    "normalsTangents",
    "uvColors",
    "materials",
    "skinning",
    "bindMatrices",
    "lods",
    "metadata",
    "animation",
    "compilation",
    "nativeViews",
)


def _canonical_hash(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _relative_path(raw: str) -> str:
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        raise SourceError("source path must be a nonempty relative string")
    normalized = raw.replace("\\", "/")
    relative = PurePosixPath(normalized)
    if (relative.is_absolute() or PureWindowsPath(raw).drive or
            any(part in ("", ".", "..") for part in normalized.split("/"))):
        raise SourceError(f"source path must stay within its tree: {raw!r}")
    return relative.as_posix()


def _declared_file(root: Path, relative: str) -> Path:
    candidate = root
    for part in PurePosixPath(relative).parts:
        candidate = candidate / part
        try:
            attributes = getattr(candidate.lstat(), "st_file_attributes", 0)
        except OSError as exc:
            raise SourceError(f"source path is missing or unreadable: {relative}") from exc
        if candidate.is_symlink() or (attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)):
            raise SourceError(f"source path crosses a link or reparse point: {relative}")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise SourceError(f"source is not a regular file within the tree: {relative}")
    return resolved


def _asset_content(asset: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "asset": asset["asset"],
        "exportMethod": asset["exportMethod"],
        "files": [{key: row[key] for key in ("path", "role", "bytes", "sha256")}
                  for row in asset["files"]],
    }


def _manifest_content(assets: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {"schemaVersion": 1,
            "assets": [_asset_content(asset) for asset in assets]}


def _validate_manifest(manifest: Mapping[str, Any]) -> None:
    try:
        if manifest["schemaVersion"] != 1 or not isinstance(manifest["assets"], list):
            raise SourceError("unsupported source inventory schema")
        names: set[str] = set()
        for asset in manifest["assets"]:
            name = asset["asset"]
            if not isinstance(name, str) or not name or name.casefold() in names:
                raise SourceError("duplicate or empty asset name in inventory")
            names.add(name.casefold())
            if not isinstance(asset["exportMethod"], str) or not asset["exportMethod"]:
                raise SourceError(f"{name}: missing export method")
            if not isinstance(asset["files"], list) or not asset["files"]:
                raise SourceError(f"{name}: source file list is empty")
            seen: set[str] = set()
            for row in asset["files"]:
                path = _relative_path(row["path"])
                if path.casefold() in seen or path != row["path"]:
                    raise SourceError(f"{name}: duplicate or noncanonical file path")
                seen.add(path.casefold())
                if (not isinstance(row["role"], str) or not row["role"] or
                        not isinstance(row["bytes"], int) or row["bytes"] < 0 or
                        not isinstance(row["sha256"], str) or
                        not _SHA256.fullmatch(row["sha256"])):
                    raise SourceError(f"{name}: invalid file metadata for {path}")
            if asset["assetDigest"] != _canonical_hash(_asset_content(asset)):
                raise SourceError(f"{name}: source asset digest is invalid")
        if manifest["manifestDigest"] != _canonical_hash(_manifest_content(manifest["assets"])):
            raise SourceError("source inventory digest is invalid")
    except (KeyError, TypeError) as exc:
        raise SourceError("malformed source inventory") from exc


def capture_source_inventory(
    source_root: Path,
    declarations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Hash declared files in caller order; never infer the accepted source.

    A declaration has ``asset``, ``exportMethod``, and ordered ``files``.  Each
    file has a relative ``path`` and a ``role`` such as ``build-usf``,
    ``blend-reference``, or ``export-options``.  The digest excludes the
    absolute root and timestamps so a verified copy retains its identity.
    """
    try:
        root = Path(source_root).resolve(strict=True)
    except OSError as exc:
        raise SourceError(f"source root is missing or unreadable: {source_root}") from exc
    if not root.is_dir():
        raise SourceError(f"source root is not a directory: {root}")
    if not declarations:
        raise SourceError("at least one asset must be declared")
    assets: list[dict[str, Any]] = []
    seen_assets: set[str] = set()
    for declaration in declarations:
        try:
            name = declaration["asset"]
            method = declaration["exportMethod"]
            declared_files = declaration["files"]
        except (KeyError, TypeError) as exc:
            raise SourceError("asset declaration requires asset, exportMethod, and files") from exc
        if (not isinstance(name, str) or not name or name.casefold() in seen_assets or
                not isinstance(method, str) or not method or
                not isinstance(declared_files, (list, tuple)) or not declared_files):
            raise SourceError("invalid or duplicate asset declaration")
        seen_assets.add(name.casefold())
        files: list[dict[str, Any]] = []
        seen_files: set[str] = set()
        for entry in declared_files:
            try:
                relative = _relative_path(entry["path"])
                role = entry["role"]
            except (KeyError, TypeError) as exc:
                raise SourceError(f"{name}: each file requires path and role") from exc
            if not isinstance(role, str) or not role or relative.casefold() in seen_files:
                raise SourceError(f"{name}: invalid role or duplicate source path")
            seen_files.add(relative.casefold())
            path = _declared_file(root, relative)
            before = path.stat()
            digest = file_sha256(path)
            after = path.stat()
            identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            if identity_before != identity_after:
                raise SourceError(f"{name}: source changed while hashing {relative}")
            files.append({"path": relative, "role": role,
                          "bytes": after.st_size, "sha256": digest})
        asset = {"asset": name, "exportMethod": method, "files": files}
        asset["assetDigest"] = _canonical_hash(_asset_content(asset))
        assets.append(asset)
    manifest = {"schemaVersion": 1, "sourceRoot": str(root), "assets": assets}
    manifest["manifestDigest"] = _canonical_hash(_manifest_content(assets))
    return manifest


def compare_source_baselines(
    expected: Mapping[str, Any], actual: Mapping[str, Any]
) -> dict[str, Any]:
    """Return ordered asset/file differences; source-root relocation is allowed."""
    _validate_manifest(expected)
    _validate_manifest(actual)
    changes: list[dict[str, Any]] = []
    old_assets = {a["asset"]: a for a in expected["assets"]}
    new_assets = {a["asset"]: a for a in actual["assets"]}
    old_order = list(old_assets)
    new_order = list(new_assets)
    if old_order != new_order:
        changes.append({"kind": "asset-order", "expected": old_order,
                        "actual": new_order})
    for name in dict.fromkeys(old_order + new_order):
        if name not in old_assets:
            changes.append({"kind": "asset-added", "asset": name})
            continue
        if name not in new_assets:
            changes.append({"kind": "asset-removed", "asset": name})
            continue
        previous, current = old_assets[name], new_assets[name]
        if previous["exportMethod"] != current["exportMethod"]:
            changes.append({"kind": "export-method", "asset": name,
                            "expected": previous["exportMethod"],
                            "actual": current["exportMethod"]})
        old_files = {f["path"]: f for f in previous["files"]}
        new_files = {f["path"]: f for f in current["files"]}
        if list(old_files) != list(new_files):
            changes.append({"kind": "file-order", "asset": name,
                            "expected": list(old_files), "actual": list(new_files)})
        for path in dict.fromkeys(list(old_files) + list(new_files)):
            if path not in old_files:
                changes.append({"kind": "file-added", "asset": name, "path": path})
            elif path not in new_files:
                changes.append({"kind": "file-removed", "asset": name, "path": path})
            else:
                old_row, new_row = old_files[path], new_files[path]
                for field in ("role", "bytes", "sha256"):
                    if old_row[field] != new_row[field]:
                        changes.append({"kind": "file-" + field, "asset": name,
                                        "path": path, "expected": old_row[field],
                                        "actual": new_row[field]})
    return {"matches": not changes, "changes": changes,
            "expectedDigest": expected["manifestDigest"],
            "actualDigest": actual["manifestDigest"]}


def require_export_allowed(
    source_root: Path,
    inventory: Mapping[str, Any],
    asset_name: str,
    requested_method: str,
    parity_receipt: Mapping[str, Any] | None = None,
) -> None:
    """Reject stale inputs and unapproved native Blender exports.

    The parity receipt is an external review record, not proof generated here.
    Every listed check must be passed and the receipt must identify the exact
    current asset content and repaired USF baseline.
    """
    _validate_manifest(inventory)
    declarations = [
        {"asset": asset["asset"], "exportMethod": asset["exportMethod"],
         "files": [{"path": row["path"], "role": row["role"]}
                   for row in asset["files"]]}
        for asset in inventory["assets"]
    ]
    current = capture_source_inventory(source_root, declarations)
    if not compare_source_baselines(inventory, current)["matches"]:
        raise ExportBlockedError("source files changed since the declared inventory")
    asset = next((row for row in current["assets"] if row["asset"] == asset_name), None)
    if asset is None:
        raise ExportBlockedError(f"asset is absent from the inventory: {asset_name}")
    if requested_method != "native-blend":
        if requested_method != asset["exportMethod"]:
            raise ExportBlockedError(f"{asset_name}: export method is not declared")
        return
    usf_files = [row for row in asset["files"] if row["role"] == "build-usf"]
    if len(usf_files) != 1:
        raise ExportBlockedError(f"{asset_name}: exactly one repaired build USF is required")
    receipt = parity_receipt or {}
    if (receipt.get("schemaVersion") != 1 or receipt.get("status") != "APPROVED" or
            receipt.get("asset") != asset_name or
            receipt.get("sourceAssetDigest") != asset["assetDigest"] or
            receipt.get("baselineUsfSha256") != usf_files[0]["sha256"] or
            not isinstance(receipt.get("reviewer"), str) or not receipt["reviewer"].strip() or
            not isinstance(receipt.get("checks"), dict) or
            any(receipt["checks"].get(check) is not True for check in _PARITY_CHECKS)):
        raise ExportBlockedError(f"{asset_name}: complete approved Blender parity receipt is missing or stale")


def validate_usf_no_edit_roundtrip(
    source: Path,
    writer: Callable[[Path, Path], None],
    scratch_root: Path,
) -> dict[str, Any]:
    """Use a trusted parser/writer to test byte parity in disposable scratch.

    The SDK's USF parser needs Blender's Python runtime.  Callers load it there
    and inject a function that reads ``source`` and writes ``destination``.
    This function never rewrites the source.  The temporary output is created
    beneath a caller-selected writable root and removed after inspection.
    """
    path = Path(source).resolve(strict=True)
    scratch = Path(scratch_root).resolve(strict=True)
    if not path.is_file() or not scratch.is_dir() or not callable(writer):
        raise SourceError("USF roundtrip needs a file, writable scratch directory, and writer")
    if path.suffix.casefold() != ".usf":
        raise SourceError("roundtrip source must be a USF file")
    if not os.access(scratch, os.W_OK):
        raise SourceError(f"scratch directory is not writable: {scratch}")
    before = file_sha256(path)
    source_bytes = path.stat().st_size
    try:
        with tempfile.TemporaryDirectory(prefix="roadcraft-usf-roundtrip-", dir=scratch) as temp:
            destination = Path(temp) / "roundtrip.usf"
            writer(path, destination)
            if not destination.is_file() or destination.is_symlink():
                raise SourceError("USF writer did not produce a regular scratch output")
            output_sha = file_sha256(destination)
            output_bytes = destination.stat().st_size
    finally:
        if file_sha256(path) != before:
            raise SourceError("USF source changed during roundtrip validation")
    return {"sourceSha256": before, "sourceBytes": source_bytes,
            "outputSha256": output_sha, "outputBytes": output_bytes,
            "byteIdentical": output_sha == before and output_bytes == source_bytes}
