"""Hash-pinned, recoverable package installation for one RoadCraft mod slot.

No operation targets a built-in game path.  Callers provide the package pins,
installed path, transaction directory, and a process checker.  Mutation is
opt-in with ``dry_run=False``.  Each successful install retains the exact
previous installed bytes for rollback, even when they are another candidate.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
from typing import Any, Callable, Iterator, Mapping, Sequence
from uuid import uuid4


class PackageTransactionError(RuntimeError):
    """The operation could not safely proceed."""


class TransactionBusyError(PackageTransactionError):
    """A process or another package transaction currently owns the slot."""


class RecoveryRequiredError(PackageTransactionError):
    """A durable receipt needs explicit inspection or recovery."""


ProcessChecker = Callable[[], Sequence[str] | bool]
LockOwnerActive = Callable[[Mapping[str, Any]], bool]
_SHA = re.compile(r"^[0-9a-f]{64}$")
_INCOMPLETE = {
    "PREPARING", "BACKUP_VERIFIED", "STAGED_VERIFIED", "SWAP_READY",
    "ROLLBACK_READY", "RECOVERY_REQUIRED",
}


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
        raise PackageTransactionError(f"file changed during hashing: {path}")
    return digest.hexdigest()


def _valid_hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value.lower()):
        raise PackageTransactionError(f"invalid SHA-256 for {label}")
    return value.lower()


def _existing_file(value: str | Path, label: str) -> Path:
    path = Path(value).expanduser()
    try:
        before = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise PackageTransactionError(f"{label} is missing or unreadable: {path}") from exc
    attributes = getattr(before, "st_file_attributes", 0)
    if (path.is_symlink() or
            attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0) or
            not resolved.is_file()):
        raise PackageTransactionError(f"{label} must be a regular file: {path}")
    return resolved


def _pin(value: Mapping[str, Any], label: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or "path" not in value:
        raise PackageTransactionError(f"{label} must contain a path and SHA-256")
    path = _existing_file(value["path"], label)
    expected = _valid_hash(value.get("sha256"), label)
    if _sha(path) != expected:
        raise PackageTransactionError(f"{label} package hash differs from its pin")
    return {"path": str(path), "sha256": expected}


def _target(value: str | Path, *, allow_missing: bool = False) -> Path:
    if allow_missing:
        from .core import _require_local_path
        proposed = _require_local_path(value).expanduser().absolute()
        if not proposed.exists() and not proposed.is_symlink():
            if not proposed.parent.is_dir() or proposed.suffix.lower() != ".pak":
                raise PackageTransactionError("new installed package needs an existing directory and a .pak filename")
            return proposed.parent.resolve() / proposed.name
    path = _existing_file(value, "installed package")
    if not path.parent.is_dir():
        raise PackageTransactionError("installed package directory is missing")
    return path


def _current_sha(target: Path) -> str | None:
    if not target.exists() and not target.is_symlink():
        return None
    return _sha(_existing_file(target, "installed package"))


def _verify_backup(data: dict[str, Any]) -> None:
    if data.get("previousAbsent") is True:
        return
    backup = _existing_file(data["backupPath"], "rollback backup")
    if _sha(backup) != data["previousSha256"]:
        raise RecoveryRequiredError("rollback would overwrite unknown or corrupted package bytes: backup is missing or corrupt")


def _processes_clear(checker: ProcessChecker) -> None:
    if not callable(checker):
        raise PackageTransactionError("a process checker is required")
    try:
        active = checker()
    except Exception as exc:
        raise TransactionBusyError("process state could not be verified") from exc
    if isinstance(active, bool):
        blockers = ["editor/game process"] if active else []
    elif isinstance(active, (list, tuple, set)):
        blockers = [str(item) for item in active]
    else:
        raise PackageTransactionError("process checker must return bool or a sequence")
    if blockers:
        raise TransactionBusyError("editor/game process is active: " + ", ".join(blockers))


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RecoveryRequiredError(f"cannot read transaction record: {path}") from exc
    if not isinstance(data, dict):
        raise RecoveryRequiredError(f"transaction record is not an object: {path}")
    return data


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp-" + uuid4().hex)
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _advance(receipt_path: Path, receipt: dict[str, Any], state: str,
             detail: str) -> None:
    receipt["state"] = state
    receipt.setdefault("events", []).append({"at": _now(), "state": state,
                                              "detail": detail})
    _write_json(receipt_path, receipt)


def _state_root(path: str | Path, *, create: bool) -> Path:
    root = Path(path).expanduser().absolute()
    if create:
        root.mkdir(parents=True, exist_ok=True)
    if root.exists():
        attributes = getattr(root.lstat(), "st_file_attributes", 0)
        if (not root.is_dir() or root.is_symlink() or
                attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)):
            raise PackageTransactionError(f"transaction root is not a plain directory: {root}")
    return root.resolve()


def _ensure_no_incomplete(root: Path, target: Path) -> None:
    if not root.is_dir():
        return
    for path in root.glob("*/receipt.json"):
        receipt = _read_json(path)
        if receipt.get("installedPath") == str(target) and receipt.get("state") in _INCOMPLETE:
            raise RecoveryRequiredError(f"unfinished package transaction: {path}")


@contextmanager
def _lock(root: Path, txid: str, target: Path, *,
          lock_owner_active: LockOwnerActive | None = None) -> Iterator[None]:
    lock_path = root / "package.lock"
    if lock_path.exists() and lock_owner_active is not None:
        old = _read_json(lock_path)
        if old.get("installedPath") != str(target) or old.get("transactionId") != txid:
            raise TransactionBusyError(f"another transaction owns lock: {lock_path}")
        try:
            active = lock_owner_active(old)
        except Exception as exc:
            raise TransactionBusyError("lock owner state could not be verified") from exc
        if active:
            raise TransactionBusyError(f"transaction owner is still active: {lock_path}")
        archive = root / txid / ("orphaned-lock-" + uuid4().hex + ".json")
        os.replace(lock_path, archive)
    payload = {"schemaVersion": 1, "transactionId": txid,
               "installedPath": str(target), "pid": os.getpid(), "createdAt": _now()}
    try:
        with lock_path.open("x", encoding="utf-8") as stream:
            json.dump(payload, stream)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise TransactionBusyError(f"package transaction lock exists: {lock_path}") from exc
    try:
        yield
    finally:
        # Never clear a lock that was replaced by another owner.
        if lock_path.exists():
            current = _read_json(lock_path)
            if current == payload:
                lock_path.unlink()


def _copy_verified(source: Path, destination: Path, expected: str) -> None:
    if destination.exists():
        raise RecoveryRequiredError(f"destination already exists: {destination}")
    with source.open("rb") as input_stream, destination.open("xb") as output_stream:
        shutil.copyfileobj(input_stream, output_stream, length=4 * 1024 * 1024)
        output_stream.flush()
        os.fsync(output_stream.fileno())
    if _sha(destination) != expected:
        raise RecoveryRequiredError(f"copied package failed hash verification: {destination}")


def _receipt(path: str | Path) -> tuple[Path, dict[str, Any], Path, Path]:
    receipt_path = _existing_file(path, "transaction receipt")
    data = _read_json(receipt_path)
    if data.get("schemaVersion") not in (1, 2):
        raise RecoveryRequiredError("unsupported transaction receipt schema")
    txid = data.get("transactionId")
    if (not isinstance(txid, str) or not re.fullmatch(r"[0-9a-f]{32}", txid) or
            receipt_path.name != "receipt.json" or receipt_path.parent.name != txid):
        raise RecoveryRequiredError("transaction receipt location does not match its identity")
    root = receipt_path.parent.parent
    absent = data.get("schemaVersion") == 2 and data.get("previousAbsent") is True
    if data.get("previousAbsent") and not absent:
        raise RecoveryRequiredError("absence requires a version 2 transaction receipt")
    target = _target(data.get("installedPath", ""), allow_missing=absent)
    expected_backup = receipt_path.parent / "before.pak"
    if (data.get("transactionRoot") != str(root) or
            data.get("backupPath") != str(expected_backup) or
            data.get("pendingPath") != str(target.parent / f".{target.name}.roadcraft-{txid}.pending")):
        raise RecoveryRequiredError("transaction receipt paths are inconsistent")
    for key in ("previousSha256", "candidateSha256", "acceptedSha256"):
        if key == "previousSha256" and absent:
            if data.get(key) is not None:
                raise RecoveryRequiredError("absent previous state cannot contain a package hash")
            continue
        if key == "acceptedSha256" and data.get("schemaVersion") == 2 and data.get(key) is None:
            continue
        _valid_hash(data.get(key), key)
    return receipt_path, data, root, target


def install_package(
    accepted_pin: Mapping[str, Any] | None,
    candidate_pin: Mapping[str, Any],
    installed_path: str | Path,
    transaction_root: str | Path,
    expected_installed_sha256: str | None,
    process_checker: ProcessChecker,
    *,
    dry_run: bool = True,
    expect_absent: bool = False,
) -> dict[str, Any]:
    """Install a candidate only when the live package has the expected hash."""
    accepted = _pin(accepted_pin, "accepted") if accepted_pin is not None else {"path": None, "sha256": None}
    candidate = _pin(candidate_pin, "candidate")
    if expect_absent and expected_installed_sha256 is not None:
        raise PackageTransactionError("choose expected absence or an installed hash, not both")
    target = _target(installed_path, allow_missing=expect_absent)
    root = _state_root(transaction_root, create=False)
    expected = None if expect_absent else _valid_hash(expected_installed_sha256, "expected installed package")
    if target in [Path(row["path"]) for row in (accepted, candidate) if row["path"]]:
        raise PackageTransactionError("installed path must be separate from pinned archives")
    if _current_sha(target) != expected:
        raise RecoveryRequiredError("installed package has an unexpected hash")
    if candidate["sha256"] == expected:
        raise PackageTransactionError("candidate is already installed")
    _processes_clear(process_checker)
    _ensure_no_incomplete(root, target)
    plan = {"operation": "install", "dryRun": dry_run,
            "installedPath": str(target), "previousSha256": expected,
            "candidateSha256": candidate["sha256"],
            "acceptedSha256": accepted["sha256"],
            "previousAbsent": expect_absent,
            "transactionRoot": str(root), "backupBytes": 0 if expect_absent else target.stat().st_size,
            "stagingBytes": Path(candidate["path"]).stat().st_size}
    if dry_run:
        return plan

    root = _state_root(root, create=True)
    txid = uuid4().hex
    with _lock(root, txid, target):
        _processes_clear(process_checker)
        _ensure_no_incomplete(root, target)
        if _current_sha(target) != expected or _sha(Path(candidate["path"])) != candidate["sha256"]:
            raise RecoveryRequiredError("package identity changed after preflight")
        txdir = root / txid
        txdir.mkdir()
        receipt_path = txdir / "receipt.json"
        backup = txdir / "before.pak"
        backup_pending = txdir / "before.pak.pending"
        pending = target.parent / f".{target.name}.roadcraft-{txid}.pending"
        data: dict[str, Any] = {
            "schemaVersion": 2 if expect_absent or accepted_pin is None else 1, "transactionId": txid,
            "transactionRoot": str(root), "installedPath": str(target),
            "acceptedPath": accepted["path"], "acceptedSha256": accepted["sha256"],
            "candidatePath": candidate["path"], "candidateSha256": candidate["sha256"],
            "previousSha256": expected, "backupPath": str(backup),
            "previousAbsent": expect_absent,
            "pendingPath": str(pending), "state": "PREPARING", "events": [],
        }
        _advance(receipt_path, data, "PREPARING", "transaction created")
        try:
            if not expect_absent:
                _copy_verified(target, backup_pending, expected)
                os.replace(backup_pending, backup)
                if _sha(backup) != expected:
                    raise RecoveryRequiredError("rollback backup failed verification")
            _advance(receipt_path, data, "BACKUP_VERIFIED",
                     "previous absence recorded" if expect_absent else "previous installed bytes retained")
            _copy_verified(Path(candidate["path"]), pending, candidate["sha256"])
            _advance(receipt_path, data, "STAGED_VERIFIED", "candidate copied beside installed package")
            _processes_clear(process_checker)
            _verify_backup(data)
            if _current_sha(target) != expected or _sha(pending) != candidate["sha256"]:
                raise RecoveryRequiredError("identity changed before atomic swap")
            _advance(receipt_path, data, "SWAP_READY", "safe to inspect live hash after interruption")
            if expect_absent:
                # Atomically create without replacing a file that appeared after preflight.
                os.link(pending, target)
                pending.unlink()
            else:
                os.replace(pending, target)
            if _sha(target) != candidate["sha256"]:
                raise RecoveryRequiredError("installed package failed post-swap verification")
            _advance(receipt_path, data, "INSTALLED", "candidate installed and verified")
        except Exception:
            # A pre-swap failure leaves the original installed bytes.  An
            # interrupted or unverified swap remains described by SWAP_READY.
            if data["state"] in ("PREPARING", "BACKUP_VERIFIED", "STAGED_VERIFIED"):
                try:
                    if _current_sha(target) == expected:
                        _advance(receipt_path, data, "NOT_INSTALLED", "failed before live swap")
                except Exception:
                    pass
            raise
    return {**plan, "dryRun": False, "transactionId": txid,
            "receiptPath": str(receipt_path), "backupPath": str(backup),
            "state": "INSTALLED"}


def _restore(receipt_path: Path, data: dict[str, Any], target: Path,
             process_checker: ProcessChecker) -> None:
    if data.get("previousAbsent") is True:
        _processes_clear(process_checker)
        if _current_sha(target) != data["candidateSha256"]:
            raise RecoveryRequiredError("rollback would remove unknown package bytes")
        _advance(receipt_path, data, "ROLLBACK_READY", "verified candidate may be removed to restore absence")
        _processes_clear(process_checker)
        if _current_sha(target) != data["candidateSha256"]:
            raise RecoveryRequiredError("installed package changed before rollback")
        target.unlink()
        if target.exists():
            raise RecoveryRequiredError("rollback did not restore the empty mod slot")
        _advance(receipt_path, data, "ROLLED_BACK", "previous package absence restored")
        return
    backup = _existing_file(data["backupPath"], "rollback backup")
    previous = data["previousSha256"]
    candidate = data["candidateSha256"]
    if _sha(backup) != previous or _sha(target) != candidate:
        raise RecoveryRequiredError("backup or installed package differs from receipt")
    _processes_clear(process_checker)
    # A fresh name lets recovery proceed even if a previous rollback attempt
    # left a partial staging file after a crash.
    pending = target.parent / (f".{target.name}.roadcraft-{data['transactionId']}."
                               f"rollback-{uuid4().hex}.pending")
    _copy_verified(backup, pending, previous)
    _advance(receipt_path, data, "ROLLBACK_READY", "verified prior bytes staged beside target")
    _processes_clear(process_checker)
    if _sha(target) != candidate or _sha(pending) != previous:
        raise RecoveryRequiredError("installed or staged bytes changed before rollback")
    os.replace(pending, target)
    if _sha(target) != previous:
        raise RecoveryRequiredError("rollback did not restore exact previous bytes")
    _advance(receipt_path, data, "ROLLED_BACK", "exact previous installed bytes restored")


def rollback_package(
    receipt_path: str | Path,
    process_checker: ProcessChecker,
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Restore precisely the bytes that preceded this transaction."""
    path, data, root, target = _receipt(receipt_path)
    _processes_clear(process_checker)
    if data["state"] == "ROLLED_BACK" and _current_sha(target) == data["previousSha256"]:
        return {"operation": "rollback", "dryRun": dry_run, "state": "ROLLED_BACK",
                "receiptPath": str(path), "installedSha256": data["previousSha256"]}
    if data["state"] != "INSTALLED":
        raise RecoveryRequiredError(f"transaction is not ready for normal rollback: {data['state']}")
    _verify_backup(data)
    if _current_sha(target) != data["candidateSha256"]:
        raise RecoveryRequiredError("rollback would overwrite unknown or corrupted package bytes")
    result = {"operation": "rollback", "dryRun": dry_run,
              "receiptPath": str(path), "installedPath": str(target),
              "fromSha256": data["candidateSha256"],
              "toSha256": data["previousSha256"]}
    if dry_run:
        return result
    with _lock(root, data["transactionId"], target):
        _restore(path, data, target, process_checker)
    return {**result, "dryRun": False, "state": "ROLLED_BACK"}


def recover_package(
    receipt_path: str | Path,
    process_checker: ProcessChecker,
    *,
    dry_run: bool = True,
    lock_owner_active: LockOwnerActive | None = None,
) -> dict[str, Any]:
    """Resolve interrupted work only when live bytes match a known state.

    If a crashed worker left ``package.lock``, pass a checker that confirms
    whether its recorded owner is still active.  The old lock is archived only
    when that checker returns ``False``.  Unknown live bytes are never replaced.
    """
    path, data, root, target = _receipt(receipt_path)
    _processes_clear(process_checker)
    current = _current_sha(target)
    previous = data["previousSha256"]
    candidate = data["candidateSha256"]
    state = data["state"]
    if current not in (previous, candidate):
        raise RecoveryRequiredError("installed package has an unknown hash")
    if state == "INSTALLED" and current == candidate:
        action = "none"
    elif state == "ROLLED_BACK" and current == previous:
        action = "none"
    elif state in _INCOMPLETE and current == previous:
        action = "mark-not-installed" if state != "ROLLBACK_READY" else "mark-rolled-back"
    elif state in ("SWAP_READY", "ROLLBACK_READY", "RECOVERY_REQUIRED") and current == candidate:
        _verify_backup(data)
        action = "restore-previous"
    else:
        raise RecoveryRequiredError(f"receipt state and installed hash conflict: {state}")
    result = {"operation": "recover", "dryRun": dry_run,
              "receiptPath": str(path), "receiptState": state,
              "installedSha256": current, "action": action}
    if dry_run:
        return result
    if action == "none":
        if (root / "package.lock").exists():
            with _lock(root, data["transactionId"], target,
                       lock_owner_active=lock_owner_active):
                pass
        return {**result, "dryRun": False}
    with _lock(root, data["transactionId"], target,
               lock_owner_active=lock_owner_active):
        _processes_clear(process_checker)
        if _current_sha(target) != current:
            raise RecoveryRequiredError("installed package changed during recovery")
        if action == "restore-previous":
            _restore(path, data, target, process_checker)
        elif action == "mark-rolled-back":
            _advance(path, data, "ROLLED_BACK", "interrupted rollback already restored prior bytes")
        else:
            _advance(path, data, "NOT_INSTALLED", "interrupted install left prior bytes intact")
    return {**result, "dryRun": False, "state": data["state"]}


def archive_orphaned_lock(
    transaction_root: str | Path,
    installed_path: str | Path,
    process_checker: ProcessChecker,
    lock_owner_active: LockOwnerActive,
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Recover a lock left before its transaction receipt was written.

    The caller must supply an independent owner-liveness check.  The old lock
    is retained as evidence under ``orphaned-locks``; package bytes are never
    touched.  For a transaction with a receipt, use ``recover_package``.
    """
    root = _state_root(transaction_root, create=False)
    target = _target(installed_path)
    lock_path = root / "package.lock"
    lock = _read_json(lock_path)
    if lock.get("installedPath") != str(target):
        raise TransactionBusyError("lock belongs to another installed package")
    _processes_clear(process_checker)
    try:
        active = lock_owner_active(lock)
    except Exception as exc:
        raise TransactionBusyError("lock owner state could not be verified") from exc
    if active:
        raise TransactionBusyError("transaction lock owner is still active")
    txid = lock.get("transactionId")
    if isinstance(txid, str) and (root / txid / "receipt.json").exists():
        raise RecoveryRequiredError("transaction has a receipt; recover that transaction")
    result = {"operation": "archive-orphaned-lock", "dryRun": dry_run,
              "lockPath": str(lock_path), "installedPath": str(target),
              "transactionId": txid}
    if dry_run:
        return result
    if _read_json(lock_path) != lock or lock_owner_active(lock):
        raise TransactionBusyError("transaction lock changed or owner resumed")
    archive_dir = root / "orphaned-locks"
    archive_dir.mkdir(exist_ok=True)
    destination = archive_dir / (uuid4().hex + ".json")
    os.replace(lock_path, destination)
    return {**result, "dryRun": False, "archivedPath": str(destination)}
