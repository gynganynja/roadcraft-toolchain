"""Read-only inventory and verification primitives for RoadCraft projects.

No path or hash in this module is tied to a particular D11 build. Callers supply
an explicit project registry and machine configuration. ZIP entries are keyed by
their normalized path *and occurrence* because RoadCraft packages can contain
multiple entries with the same name.
"""

from __future__ import annotations

from collections import defaultdict
import ctypes
from ctypes import wintypes
from hashlib import sha256
import json
import os
from pathlib import Path, PureWindowsPath
import shutil
import stat
import sys
from typing import Any
from zipfile import BadZipFile, ZipFile, ZipInfo, is_zipfile


class RoadcraftError(ValueError):
    """An input is missing, malformed, or failed verification."""


def _is_remote_namespace(value: str | Path) -> bool:
    """Recognize UNC shares and Win32 device paths before filesystem access."""
    return str(value).replace("/", "\\").startswith("\\\\")


def _require_local_path(value: str | Path) -> Path:
    """Reject network/device syntax and reparse ancestors before resolution.

    Inspect each existing component with lstat, stopping before a missing one.
    In particular, resolve() itself can access a UNC target through a local
    junction, so its result cannot be the first locality check.
    """
    if _is_remote_namespace(value):
        raise RoadcraftError("UNC and device paths are not supported")
    path = Path(value).expanduser()
    if _is_remote_namespace(path):
        raise RoadcraftError("UNC and device paths are not supported")
    if os.name == "nt":
        if path.drive and not path.is_absolute():
            raise RoadcraftError("Drive-relative paths are not supported")
        tail = str(path)[len(path.drive):]
        if ":" in tail or any(PureWindowsPath(part).is_reserved() for part in path.parts):
            raise RoadcraftError("Windows device names and alternate data streams are not supported")
    absolute = path if path.is_absolute() else Path.cwd() / path
    if _is_remote_namespace(absolute):
        raise RoadcraftError("UNC and device paths are not supported")
    if os.name == "nt" and absolute.drive:
        drive_type = ctypes.windll.kernel32.GetDriveTypeW(str(Path(absolute.anchor)))
        if drive_type == 4:  # DRIVE_REMOTE, including mapped SMB drives.
            raise RoadcraftError("Remote mapped drives are not supported")
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            info = current.lstat()
        except (FileNotFoundError, NotADirectoryError):
            break
        except OSError as exc:
            raise RoadcraftError(f"Cannot verify local path component {current}: {exc}") from exc
        if stat.S_ISLNK(info.st_mode) or (
                os.name == "nt" and getattr(info, "st_file_attributes", 0) & 0x400):
            raise RoadcraftError(f"Reparse or symbolic-link path component is not supported: {current}")
    return path


def sha256_file(path: str | Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: str | Path) -> dict[str, Any]:
    source = _require_local_path(path).resolve()
    try:
        data = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RoadcraftError(f"Cannot read JSON {source}: {exc}") from exc
    if not isinstance(data, dict):
        raise RoadcraftError(f"Expected a JSON object: {source}")
    return data


def resolve_path(value: str | Path, document: str | Path) -> Path:
    if not isinstance(value, (str, Path)) or not str(value):
        raise RoadcraftError(f"Expected a nonempty path in {document}")
    if _is_remote_namespace(value):
        raise RoadcraftError(f"UNC and device paths are not supported in {document}")
    path = Path(value).expanduser()
    if not path.is_absolute():
        source = _require_local_path(document).resolve()
        path = source.parent / path
    _require_local_path(path)
    resolved = path.resolve()
    if _is_remote_namespace(resolved):
        raise RoadcraftError(f"UNC and device paths are not supported in {document}")
    return resolved


def _pin(value: Any, document: str | Path) -> dict[str, Any] | None:
    """Resolve a path/hash pair while preserving any extra registry fields."""
    if value is None:
        return None
    if isinstance(value, str):
        value = {"path": value}
    if not isinstance(value, dict) or "path" not in value:
        raise RoadcraftError(f"Expected an object containing path in {document}")
    result = dict(value)
    result["path"] = str(resolve_path(value["path"], document))
    expected = value.get("sha256")
    if expected is not None and (not isinstance(expected, str) or len(expected) != 64 or
                                 any(c not in "0123456789abcdefABCDEF" for c in expected)):
        raise RoadcraftError(f"Invalid SHA-256 for {value['path']}")
    if expected is not None:
        result["sha256"] = expected.lower()
    return result


def read_registry(path: str | Path) -> dict[str, Any]:
    data = load_json(path)
    if data.get("schemaVersion") != 1:
        raise RoadcraftError(f"Unsupported registry schemaVersion in {path}; expected 1")
    accepted = data.get("accepted", {})
    candidates = data.get("candidates", {})
    if not isinstance(accepted, dict) or not isinstance(candidates, dict):
        raise RoadcraftError("accepted and candidates must be JSON objects")
    resolved = dict(data)
    resolved["accepted"] = dict(accepted)
    for key in ("package", "sourceManifest", "authoringInventory"):
        if key in accepted:
            resolved["accepted"][key] = _pin(accepted[key], path)
    if accepted.get("sourceRoot"):
        resolved["accepted"]["sourceRoot"] = str(resolve_path(accepted["sourceRoot"], path))
    resolved["candidates"] = {}
    for name, candidate in candidates.items():
        if not isinstance(candidate, dict):
            raise RoadcraftError(f"Candidate {name} must be an object")
        row = dict(candidate)
        for key in ("package", "receipt"):
            if key in row:
                row[key] = _pin(row[key], path)
        resolved["candidates"][name] = row
    return resolved


def read_config(path: str | Path) -> dict[str, Any]:
    data = load_json(path)
    if data.get("schemaVersion") != 1:
        raise RoadcraftError(f"Unsupported config schemaVersion in {path}; expected 1")
    resolved = dict(data)
    for key in ("sdkRoot", "installedPackage"):
        if key in data and data[key] is not None:
            resolved[key] = str(resolve_path(data[key], path))
    tools = data.get("tools", {})
    if not isinstance(tools, dict):
        raise RoadcraftError("tools must be a JSON object")
    resolved["tools"] = {name: str(resolve_path(location, path))
                         for name, location in tools.items()}
    for key in ("transactionReceipts", "transactionLocks"):
        values = data.get(key, [])
        if not isinstance(values, list):
            raise RoadcraftError(f"{key} must be a JSON array")
        resolved[key] = [str(resolve_path(value, path)) for value in values]
    return resolved


def file_identity(path: str | Path, expected_sha256: str | None = None) -> dict[str, Any]:
    if expected_sha256 is not None and (len(expected_sha256) != 64 or
                                         any(c not in "0123456789abcdefABCDEF"
                                             for c in expected_sha256)):
        raise RoadcraftError(f"Invalid SHA-256 for {path}")
    if _is_remote_namespace(path):
        raise RoadcraftError("UNC and device paths are not supported")
    item = _require_local_path(path).resolve()
    if _is_remote_namespace(item):
        raise RoadcraftError("UNC and device paths are not supported")
    result: dict[str, Any] = {"path": str(item), "exists": item.is_file()}
    if not result["exists"]:
        if expected_sha256:
            result.update(expectedSha256=expected_sha256, matchesExpected=False)
        return result
    before = item.stat()
    digest = sha256_file(item)
    after = item.stat()
    result.update(bytes=after.st_size, sha256=digest,
                  unchangedDuringRead=(before.st_size == after.st_size and
                                       before.st_mtime_ns == after.st_mtime_ns and
                                       before.st_ino == after.st_ino))
    if expected_sha256:
        result.update(expectedSha256=expected_sha256.lower(),
                      matchesExpected=digest == expected_sha256.lower())
    return result


def status(registry: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    accepted = registry.get("accepted", {})
    candidates = registry.get("candidates", {})
    accepted_package = accepted.get("package")
    accepted_result = (file_identity(accepted_package["path"], accepted_package.get("sha256"))
                       if accepted_package else None)
    candidate_results = {
        name: file_identity(row["package"]["path"], row["package"].get("sha256"))
        for name, row in candidates.items() if row.get("package")
    }
    installed_path = config.get("installedPackage")
    installed = file_identity(installed_path) if installed_path else None
    installed_relation = "unknown"
    if installed and installed.get("sha256"):
        if not installed.get("unchangedDuringRead"):
            installed_relation = "unstable"
        else:
            current = installed["sha256"]
            expected_accepted = accepted_package.get("sha256") if accepted_package else None
            if expected_accepted and current == expected_accepted:
                installed_relation = "accepted"
            else:
                matching = sorted(name for name, row in candidates.items()
                                  if row.get("package", {}).get("sha256") == current)
                installed_relation = f"candidate:{','.join(matching)}" if matching else "unrecognized"
    transactions = []
    recovery_required = installed_relation == "unstable"
    for location in config.get("transactionReceipts", []):
        path = Path(location)
        row: dict[str, Any] = {"path": str(path), "exists": path.is_file()}
        if row["exists"]:
            try:
                receipt = load_json(path)
                current = installed.get("sha256") if installed else None
                row["installedSha256Now"] = current
                if "transactionId" in receipt and "state" in receipt:
                    # Package transactions from roadcraft.transaction use a
                    # state machine, rather than legacy capture status fields.
                    row["kind"] = "package-transaction"
                    row["transactionId"] = receipt.get("transactionId")
                    row["state"] = receipt.get("state")
                    row["previousSha256"] = receipt.get("previousSha256")
                    row["candidateSha256"] = receipt.get("candidateSha256")
                    row["installedMatchesPrevious"] = (current == row["previousSha256"]
                                                       if current and row["previousSha256"] else None)
                    row["installedMatchesCandidate"] = (current == row["candidateSha256"]
                                                        if current and row["candidateSha256"] else None)
                    terminal_ok = ((row["state"] == "INSTALLED" and
                                    row["installedMatchesCandidate"] is True) or
                                   (row["state"] in ("ROLLED_BACK", "NOT_INSTALLED") and
                                    row["installedMatchesPrevious"] is True))
                    superseded = (installed_relation == "accepted" and current not in
                                  (row["previousSha256"], row["candidateSha256"]))
                    row["supersededByAccepted"] = superseded
                    row["targetMatchesConfig"] = (receipt.get("installedPath") == installed_path
                                                  if installed_path else None)
                    row["needsReview"] = (not (terminal_ok or superseded) or
                                          row["targetMatchesConfig"] is False)
                else:
                    row["kind"] = "legacy-capture"
                    row["status"] = receipt.get("status")
                    row["runId"] = receipt.get("runId")
                    row["candidateSha256"] = receipt.get("candidateSha256")
                    row["baselineSha256"] = receipt.get("baselineSha256")
                    rollback = receipt.get("rollback")
                    row["rollbackStatus"] = rollback.get("status") if isinstance(rollback, dict) else None
                    row["installedMatchesReceiptCandidate"] = (
                        current == row["candidateSha256"]
                        if row["candidateSha256"] and current else None)
                    row["installedMatchesReceiptBaseline"] = (
                        current == row["baselineSha256"]
                        if row["baselineSha256"] and current else None)
                    state = str(row["status"] or "").upper()
                    row["failedRun"] = "FAIL" in state
                    restored = (row["rollbackStatus"] == "BASELINE_RESTORED" and
                                row["installedMatchesReceiptBaseline"] is True)
                    superseded = (row["rollbackStatus"] == "BASELINE_RESTORED" and
                                  installed_relation == "accepted" and not restored)
                    # A failed capture remains failed evidence. A verified
                    # rollback or later accepted install clears recovery work.
                    row["needsReview"] = (any(word in state for word in ("FAIL", "PENDING", "RECOVERY"))
                                          and not (restored or superseded))
                    if row["rollbackStatus"] == "BASELINE_RESTORED" and not (restored or superseded):
                        row["needsReview"] = True
                    row["rollbackVerifiedNow"] = restored
                    row["supersededByAccepted"] = superseded
            except RoadcraftError as exc:
                row["error"] = str(exc)
                row["needsReview"] = True
        transactions.append(row)
        recovery_required |= row.get("needsReview", False)
    locks = []
    for location in config.get("transactionLocks", []):
        row = {"path": str(Path(location)), "present": Path(location).exists()}
        locks.append(row)
        recovery_required |= row["present"]
    candidate_receipts = {
        name: file_identity(row["receipt"]["path"], row["receipt"].get("sha256"))
        for name, row in candidates.items() if row.get("receipt")
    }
    return {"project": registry.get("project"), "accepted": accepted_result,
            "candidates": candidate_results, "installed": installed,
            "installedRelation": installed_relation,
            "candidateReceipts": candidate_receipts,
            "authoringInventory": (file_identity(accepted["authoringInventory"]["path"],
                                                 accepted["authoringInventory"].get("sha256"))
                                   if accepted.get("authoringInventory") else None),
            "transactionReceipts": transactions, "transactionLocks": locks,
            "recoveryRequired": recovery_required,
            "sourceManifest": (file_identity(accepted["sourceManifest"]["path"],
                                             accepted["sourceManifest"].get("sha256"))
                               if accepted.get("sourceManifest") else None)}


def doctor(config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or {}
    sdk = config.get("sdkRoot")
    sdk_path = Path(sdk) if sdk else None
    disk_root = sdk_path if sdk_path and sdk_path.exists() else Path.cwd()
    disk = shutil.disk_usage(disk_root)
    tools = {name: {"path": location, "exists": Path(location).is_file()}
             for name, location in config.get("tools", {}).items()}
    processes, process_error = _editor_processes()
    warnings = []
    if processes:
        warnings.append("RoadCraft/authoring processes are active; inspect their work before native operations")
    if process_error:
        warnings.append(f"Could not inspect active processes: {process_error}")
    return {"python": {"path": sys.executable, "version": sys.version.split()[0],
                       "meetsMinimum": sys.version_info >= (3, 12)},
            "sdkRoot": {"path": sdk, "exists": sdk_path.is_dir() if sdk_path else False},
            "installedPackage": {"path": config.get("installedPackage"),
                                 "exists": Path(config["installedPackage"]).is_file()
                                 if config.get("installedPackage") else False},
            "tools": tools, "disk": {"root": str(disk_root.resolve()),
                                      "freeBytes": disk.free, "totalBytes": disk.total},
            "activeAuthoringProcesses": processes, "processInspectionError": process_error,
            "warnings": warnings}


def _is_console_launcher(pid: int, expected: Path) -> bool:
    """Match a RoadCraft CLI launcher by its executable file, or fail closed."""
    try:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        open_process = kernel.OpenProcess
        open_process.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        open_process.restype = wintypes.HANDLE
        query_image = kernel.QueryFullProcessImageNameW
        query_image.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                ctypes.POINTER(wintypes.DWORD))
        query_image.restype = wintypes.BOOL
        close = kernel.CloseHandle
        close.argtypes = (wintypes.HANDLE,)
        close.restype = wintypes.BOOL
        handle = open_process(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(buffer))
            if not query_image(handle, 0, buffer, ctypes.byref(size)):
                return False
            return expected.samefile(buffer.value)
        finally:
            close(handle)
    except (AttributeError, OSError):
        return False


def _editor_processes(*, tokens: tuple[str, ...] | None = None) -> tuple[list[dict[str, Any]], str | None]:
    """Enumerate selected process names without querying protected process memory."""
    if os.name != "nt":
        return [], "Windows process inspection is unavailable on this host"
    try:
        class ProcessEntry(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260),
            ]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        snapshot_fn = kernel.CreateToolhelp32Snapshot
        snapshot_fn.argtypes = (wintypes.DWORD, wintypes.DWORD)
        snapshot_fn.restype = wintypes.HANDLE
        first = kernel.Process32FirstW
        first.argtypes = (wintypes.HANDLE, ctypes.POINTER(ProcessEntry))
        first.restype = wintypes.BOOL
        next_entry = kernel.Process32NextW
        next_entry.argtypes = (wintypes.HANDLE, ctypes.POINTER(ProcessEntry))
        next_entry.restype = wintypes.BOOL
        close = kernel.CloseHandle
        close.argtypes = (wintypes.HANDLE,)
        close.restype = wintypes.BOOL
        handle = snapshot_fn(0x2, 0)
        if handle == ctypes.c_void_p(-1).value:
            return [], f"CreateToolhelp32Snapshot failed with Windows error {ctypes.get_last_error()}"
        found = []
        own_pid = os.getpid()
        parents: dict[int, int] = {}
        names: dict[int, str] = {}
        try:
            entry = ProcessEntry()
            entry.dwSize = ctypes.sizeof(ProcessEntry)
            if not first(handle, ctypes.byref(entry)):
                return [], f"Process32FirstW failed with Windows error {ctypes.get_last_error()}"
            if tokens is None:
                tokens = ("roadcraft", "modeditor", "integrationstudio", "blender", "painter", "furnace", "mod_pak_builder")
            while True:
                name = entry.szExeFile
                parents[entry.th32ProcessID] = entry.th32ParentProcessID
                names[entry.th32ProcessID] = name
                # A direct Python invocation must not count itself.
                if (entry.th32ProcessID != own_pid and
                        any(token in name.casefold() for token in tokens)):
                    found.append({"pid": entry.th32ProcessID, "name": name})
                entry.dwSize = ctypes.sizeof(ProcessEntry)
                if not next_entry(handle, ctypes.byref(entry)):
                    # ERROR_NO_MORE_FILES is the only successful endpoint.
                    # Any other enumeration failure must not look like an idle host.
                    code = ctypes.get_last_error()
                    if code != 18:
                        return [], f"Process32NextW failed with Windows error {code}"
                    break
        finally:
            close(handle)
        # The Windows console script is an ancestor of its Python process;
        # a venv Python shim can put another python.exe between them.
        # Exempt the closest matching launcher, never a concurrent CLI.
        entrypoint = Path(sys.argv[0])
        if entrypoint.name.casefold() == "roadcraft":
            entrypoint = entrypoint.with_suffix(".exe")
        if entrypoint.name.casefold() == "roadcraft.exe" and entrypoint.is_file():
            cursor = own_pid
            seen = {cursor}
            for _ in range(16):
                cursor = parents.get(cursor, 0)
                if not cursor or cursor in seen:
                    break
                seen.add(cursor)
                if names.get(cursor, "").casefold() == "roadcraft.exe":
                    if _is_console_launcher(cursor, entrypoint):
                        found = [row for row in found if row["pid"] != cursor]
                    break
        return found, None
    except (AttributeError, OSError) as exc:
        return [], str(exc)


def _normal_name(info: ZipInfo) -> str:
    return info.filename.replace("\\", "/")


def archive_members(path: str | Path, *, hash_content: bool = True,
                    member: str | None = None, occurrence: int | None = None) -> list[dict[str, Any]]:
    if occurrence is not None and (occurrence < 1 or member is None):
        raise RoadcraftError("--occurrence requires --member and a positive number")
    wanted = member.replace("\\", "/") if member else None
    counts: dict[str, int] = defaultdict(int)
    rows: list[dict[str, Any]] = []
    try:
        with ZipFile(path) as archive:
            for info in archive.infolist():
                name = _normal_name(info)
                counts[name] += 1
                index = counts[name]
                if (wanted is not None and name != wanted or
                        occurrence is not None and index != occurrence):
                    continue
                row: dict[str, Any] = {"path": name, "occurrence": index,
                                       "bytes": info.file_size,
                                       "compressedBytes": info.compress_size,
                                       "crc32": f"{info.CRC:08x}",
                                       "headerOffset": info.header_offset}
                if hash_content:
                    digest = sha256()
                    with archive.open(info) as stream:
                        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                            digest.update(block)
                    row["sha256"] = digest.hexdigest()
                rows.append(row)
    except (BadZipFile, OSError, RuntimeError) as exc:
        raise RoadcraftError(f"Cannot inspect archive {path}: {exc}") from exc
    if wanted is not None and not rows:
        raise RoadcraftError(f"Archive member not found: {wanted}, occurrence={occurrence}")
    return rows


def inspect_path(path: str | Path, *, member: str | None = None,
                 occurrence: int | None = None, hash_members: bool = False) -> dict[str, Any]:
    if occurrence is not None and (member is None or occurrence < 1):
        raise RoadcraftError("--occurrence requires --member and a positive number")
    identity = file_identity(path)
    if not identity["exists"]:
        raise RoadcraftError(f"File does not exist: {identity['path']}")
    archive = is_zipfile(identity["path"])
    if member and not archive:
        raise RoadcraftError("--member requires a ZIP archive")
    result = {"file": identity, "kind": "zip" if archive else "file"}
    if archive:
        rows = archive_members(identity["path"], hash_content=hash_members,
                               member=member, occurrence=occurrence)
        result["memberOccurrences"] = len(rows)
        result["members"] = rows
    return result


def compare_archives(baseline: str | Path, candidate: str | Path,
                     allowed_paths: list[str] | None = None) -> dict[str, Any]:
    old_file = file_identity(baseline)
    new_file = file_identity(candidate)
    if not old_file["exists"] or not new_file["exists"]:
        raise RoadcraftError("Both archive paths must exist")
    before = {(row["path"], row["occurrence"]): row
              for row in archive_members(baseline)}
    after = {(row["path"], row["occurrence"]): row
             for row in archive_members(candidate)}
    changes = []
    for key in sorted(before.keys() | after.keys()):
        left, right = before.get(key), after.get(key)
        if left is None:
            state = "added"
        elif right is None:
            state = "removed"
        elif left["sha256"] != right["sha256"]:
            state = "changed"
        else:
            continue
        changes.append({"path": key[0], "occurrence": key[1], "state": state,
                        "beforeSha256": left["sha256"] if left else None,
                        "afterSha256": right["sha256"] if right else None})
    result = {"baseline": old_file, "candidate": new_file,
              "baselineMemberOccurrences": len(before),
              "candidateMemberOccurrences": len(after),
              "changes": changes, "changeCount": len(changes)}
    if allowed_paths is not None:
        from fnmatch import fnmatchcase
        unexpected = [row for row in changes
                      if not any(fnmatchcase(row["path"], pattern)
                                 for pattern in allowed_paths)]
        result["allowedPaths"] = allowed_paths
        result["unexpectedChanges"] = unexpected
        result["passesAllowedChanges"] = not unexpected
    return result


def verify_manifest(path: str | Path, base: str | Path | None = None) -> dict[str, Any]:
    manifest = load_json(path)
    rows = manifest.get("files")
    if not isinstance(rows, list):
        raise RoadcraftError("Manifest needs a files array")
    root = (_require_local_path(base).resolve() if base else
            _require_local_path(path).resolve().parent)
    results = []
    for row in rows:
        if not isinstance(row, dict):
            raise RoadcraftError("Manifest file rows must be objects")
        source = row.get("path", row.get("relativePath"))
        expected = row.get("sha256")
        if not isinstance(source, str) or not source or not isinstance(expected, str):
            raise RoadcraftError("Manifest file rows need path/relativePath and sha256")
        item = Path(source)
        if not item.is_absolute():
            item = root / item
        result = file_identity(item, expected)
        expected_bytes = row.get("bytes")
        if expected_bytes is not None:
            result["expectedBytes"] = expected_bytes
            result["matchesBytes"] = result.get("bytes") == expected_bytes
        results.append(result)
    passed = all(row.get("matchesExpected") and row.get("unchangedDuringRead") and
                 row.get("matchesBytes", True) for row in results)
    return {"manifest": str(Path(path).resolve()), "base": str(root),
            "files": results, "passed": passed}


def verify_authoring_inventory(path: str | Path, source_root: str | Path) -> dict[str, Any]:
    """Rehash declared editable sources and compare their ordered inventory."""
    from . import source

    inventory = load_json(path)
    try:
        source._validate_manifest(inventory)
        declarations = [
            {"asset": asset["asset"], "exportMethod": asset["exportMethod"],
             "files": [{"path": row["path"], "role": row["role"]}
                       for row in asset["files"]]}
            for asset in inventory["assets"]
        ]
        actual = source.capture_source_inventory(Path(source_root), declarations)
        comparison = source.compare_source_baselines(inventory, actual)
    except source.SourceError as exc:
        raise RoadcraftError(f"Authoring inventory verification failed: {exc}") from exc
    return {"inventory": str(Path(path).resolve()),
            "sourceRoot": str(Path(source_root).resolve()),
            "expectedDigest": comparison["expectedDigest"],
            "actualDigest": comparison["actualDigest"],
            "changes": comparison["changes"], "passed": comparison["matches"]}
