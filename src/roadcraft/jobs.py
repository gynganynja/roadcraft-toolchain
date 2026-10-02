"""Durable, declarative subprocess runner for RoadCraft workflow phases.

Recipes specify argv arrays and pinned inputs. This module never uses a shell,
never infers an executable from PATH, and never modifies the game installation
itself. Native steps are refused while a relevant authoring process is active.
"""

from __future__ import annotations

from datetime import datetime, timezone
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid
from typing import Any

from . import core, incremental


PHASES = frozenset({"build", "inspect", "test", "capture"})
LOCK_NAME = ".roadcraft-jobs.lock"
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


class JobError(core.RoadcraftError):
    """Recipe or execution could not be completed safely."""


class JobBusy(JobError):
    """A run or an interrupted native run holds the shared jobs lock."""


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def summarize_jobs(jobs_root: str | Path) -> dict[str, Any]:
    """Read recorded elapsed times; this is neither acceptance nor a speedup claim."""
    root = core._require_local_path(jobs_root).resolve()
    rows, errors = [], []
    for path in sorted(root.glob("*/receipt.json")):
        try:
            data = core.load_json(path)
            elapsed = None
            if data.get("startedUtc") and data.get("finishedUtc"):
                elapsed = (datetime.fromisoformat(data["finishedUtc"]) -
                           datetime.fromisoformat(data["startedUtc"])).total_seconds()
            rows.append({"runId": data["runId"], "phase": data.get("phase"), "status": data["status"],
                         "startedUtc": data.get("startedUtc"), "finishedUtc": data.get("finishedUtc"),
                         "elapsedSeconds": round(elapsed, 3) if elapsed is not None else None,
                         "executedSteps": sum(s["status"] == "passed" for s in data.get("steps", [])),
                         "reusedSteps": sum(s["status"] == "cached" for s in data.get("steps", [])),
                         "receiptPath": str(path), "receiptSha256": core.sha256_file(path)})
        except (core.RoadcraftError, OSError, KeyError, TypeError, ValueError) as exc:
            errors.append({"path": str(path), "error": str(exc)})
    rows.sort(key=lambda row: (row["startedUtc"] or "", row["runId"]))
    return {"jobsRoot": str(root), "runs": rows, "unreadableReceipts": errors,
            "timingObservationOnly": True}


def _int(value: Any, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise JobError(f"{label} must be an integer >= {minimum}")
    return value


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
            c not in "0123456789abcdefABCDEF" for c in value):
        raise JobError(f"{label} must be a SHA-256 digest")
    return value.lower()


def _items(value: Any, label: str, recipe_path: Path, *, output: bool) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise JobError(f"{label} must be an array")
    result = []
    seen = set()
    for index, row in enumerate(value):
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise JobError(f"{label}[{index}] needs path")
        path = core.resolve_path(row["path"], recipe_path)
        if str(path).casefold() in seen:
            raise JobError(f"Duplicate {label} path: {path}")
        seen.add(str(path).casefold())
        pin = row.get("sha256")
        if not output and pin is None:
            raise JobError(f"Input {path} requires sha256")
        expected = _digest(pin, f"{label}[{index}].sha256") if pin is not None else None
        result.append({"path": str(path), "sha256": expected})
    return result


def load_recipe(path: str | Path, phase: str) -> dict[str, Any]:
    """Validate and resolve one phase without executing or writing anything."""
    source = Path(path).expanduser().resolve()
    data = core.load_json(source)
    result = validate_recipe_document(data, source, phase)
    result["recipeSha256"] = core.sha256_file(source)
    return result


def validate_recipe_document(data: dict[str, Any], path: str | Path, phase: str) -> dict[str, Any]:
    """Validate an unsaved recipe using its intended location, without executing it."""
    source = core._require_local_path(path).expanduser().resolve()
    if data.get("schemaVersion") != 1:
        raise JobError("Unsupported recipe schemaVersion; expected 1")
    if phase not in PHASES:
        raise JobError(f"Unknown phase: {phase}")
    name = data.get("name")
    if not isinstance(name, str) or not ID_PATTERN.fullmatch(name):
        raise JobError("Recipe name must contain 1-64 safe characters")
    phases = data.get("phases")
    if not isinstance(phases, dict) or not isinstance(phases.get(phase), list):
        raise JobError(f"Recipe lacks phase {phase}")
    raw_steps = phases[phase]
    if not raw_steps:
        raise JobError(f"Phase {phase} has no steps")
    default_inputs = _items(data.get("inputs", []), "inputs", source, output=False)
    defaults = data.get("defaults", {})
    if not isinstance(defaults, dict):
        raise JobError("defaults must be an object")
    result_steps = []
    ids = set()
    for index, row in enumerate(raw_steps):
        if not isinstance(row, dict):
            raise JobError(f"Step {index} must be an object")
        step_id = row.get("id")
        if not isinstance(step_id, str) or not ID_PATTERN.fullmatch(step_id) or step_id in ids:
            raise JobError(f"Step {index} needs a unique safe id")
        ids.add(step_id)
        command = row.get("command")
        if (not isinstance(command, list) or not command or
                any(not isinstance(arg, str) or not arg for arg in command)):
            raise JobError(f"Step {step_id} command must be a nonempty string array")
        executable = Path(command[0]).expanduser()
        if not executable.is_absolute() or not executable.is_file():
            raise JobError(f"Step {step_id} executable must be an existing absolute file: {command[0]}")
        command = [str(executable.resolve()), *command[1:]]
        cwd_value = row.get("cwd", defaults.get("cwd"))
        if not isinstance(cwd_value, str):
            raise JobError(f"Step {step_id} requires cwd")
        cwd = core.resolve_path(cwd_value, source)
        if not cwd.is_dir():
            raise JobError(f"Step {step_id} cwd is not a directory: {cwd}")
        timeout = _int(row.get("timeoutSeconds", defaults.get("timeoutSeconds")),
                       f"Step {step_id} timeoutSeconds", minimum=1)
        minimum = _int(row.get("minFreeBytes", defaults.get("minFreeBytes")),
                       f"Step {step_id} minFreeBytes")
        native = row.get("native", defaults.get("native", True))
        if not isinstance(native, bool):
            raise JobError(f"Step {step_id} native must be boolean")
        cacheable = row.get("cacheable", False)
        if not isinstance(cacheable, bool) or (cacheable and (native or phase == "capture")):
            raise JobError(f"Step {step_id}: only isolated non-capture steps may be cacheable")
        depends_on = row.get("dependsOn", [])
        prior_ids = {item["id"] for item in result_steps}
        if (not isinstance(depends_on, list) or any(not isinstance(x, str) for x in depends_on)
                or len(set(depends_on)) != len(depends_on) or not set(depends_on) <= prior_ids):
            raise JobError(f"Step {step_id} dependsOn must name unique earlier steps")
        step_inputs = _items(row.get("inputs", []), f"Step {step_id} inputs", source, output=False)
        inputs = [*default_inputs, *step_inputs]
        if len({x["path"].casefold() for x in inputs}) != len(inputs):
            raise JobError(f"Step {step_id} repeats an input path")
        outputs = _items(row.get("outputs", []), f"Step {step_id} outputs", source, output=True)
        if not outputs:
            raise JobError(f"Step {step_id} needs at least one expected output")
        trees = row.get("outputTrees", [])
        if not isinstance(trees, list) or any(not isinstance(p, str) for p in trees):
            raise JobError(f"Step {step_id} outputTrees must be an array of directory paths")
        trees = [str(core.resolve_path(p, source)) for p in trees]
        if any(not Path(p).is_relative_to(cwd) or Path(p) == cwd for p in trees):
            raise JobError(f"Step {step_id} outputTrees must be subdirectories of its working directory")
        env = row.get("env", defaults.get("env", {}))
        if (not isinstance(env, dict) or
                any(not isinstance(k, str) or not k or not isinstance(v, str)
                    for k, v in env.items())):
            raise JobError(f"Step {step_id} env must map nonempty names to strings")
        result_steps.append({"id": step_id, "command": command, "cwd": str(cwd),
                             "inputs": inputs, "outputs": outputs,
                             "timeoutSeconds": timeout, "minFreeBytes": minimum,
                             "native": native, "env": env,
                             "cacheable": cacheable, "dependsOn": depends_on, "outputTrees": trees})
    return {"name": name, "phase": phase, "recipePath": str(source),
            "steps": result_steps}


def editor_processes() -> tuple[list[dict[str, Any]], str | None]:
    """Public injection point for native process inspection and tests."""
    return core._editor_processes()


def _preflight_step(step: dict[str, Any], *, generated: set[str] | None = None,
                    dry_run: bool = False) -> dict[str, Any]:
    generated = generated or set()
    input_results = []
    for pin in step["inputs"]:
        if dry_run and pin["path"] in generated:
            input_results.append({"path": pin["path"], "expectedSha256": pin["sha256"],
                                  "generatedByPreviousStep": True})
            continue
        check = core.file_identity(pin["path"], pin["sha256"])
        input_results.append(check)
        if not check.get("matchesExpected") or not check.get("unchangedDuringRead"):
            raise JobError(f"Stale or missing input: {pin['path']}")
    free_by_path = {}
    for location in [step["cwd"], *(pin["path"] for pin in step["outputs"])]:
        volume = Path(location)
        if not volume.is_dir():
            volume = volume.parent
        while not volume.exists():
            volume = volume.parent
        free_by_path[str(volume)] = shutil.disk_usage(volume).free
    free = min(free_by_path.values())
    if free < step["minFreeBytes"]:
        raise JobError(f"Insufficient disk for {step['id']}: {free} < {step['minFreeBytes']}")
    active = []
    if step["native"]:
        active, error = editor_processes()
        if error:
            raise JobError(f"Cannot verify authoring processes for native step {step['id']}: {error}")
        if active:
            raise JobError(f"Active authoring processes block native step {step['id']}: {active}")
    return {"inputs": input_results, "freeBytes": free,
            "freeBytesByPath": free_by_path,
            "activeAuthoringProcesses": active}


def _atomic_json(path: Path, data: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        # Windows readers/virus scanners can briefly deny rename/delete sharing.
        # Retry only the observed Windows lock/permission errors, with a finite bound.
        for attempt in range(8):
            try:
                os.replace(temporary, path)
                break
            except OSError as exc:
                if getattr(exc, "winerror", None) not in (5, 32, 33) or attempt == 7:
                    raise
                time.sleep(min(0.05 * 2 ** attempt, 0.5))
    finally:
        for attempt in range(8):
            try:
                temporary.unlink(missing_ok=True)
                break
            except OSError as exc:
                if getattr(exc, "winerror", None) not in (5, 32, 33) or attempt == 7:
                    raise
                time.sleep(min(0.05 * 2 ** attempt, 0.5))


def _lock(jobs_root: Path, run_id: str) -> Path:
    lock = jobs_root / LOCK_NAME
    content = {"runId": run_id, "pid": os.getpid(), "createdUtc": _utc(),
               "python": sys.executable}
    try:
        with lock.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(content, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise JobBusy(f"Job lock exists: {lock}; inspect recovery state before retrying") from exc
    return lock


def _pid_alive(pid: int) -> bool | None:
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return None
    if os.name == "nt":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        open_process = kernel.OpenProcess
        open_process.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        open_process.restype = wintypes.HANDLE
        get_exit_code = kernel.GetExitCodeProcess
        get_exit_code.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        get_exit_code.restype = wintypes.BOOL
        close = kernel.CloseHandle
        close.argtypes = (wintypes.HANDLE,)
        close.restype = wintypes.BOOL
        handle = open_process(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            error = ctypes.get_last_error()
            if error in (87, 1168):  # ERROR_INVALID_PARAMETER / ERROR_NOT_FOUND
                return False
            return True if error == 5 else None  # access denied means it exists
        try:
            code = wintypes.DWORD()
            if not get_exit_code(handle, ctypes.byref(code)):
                return None
            return code.value == 259  # STILL_ACTIVE
        finally:
            close(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return None
    return True


def inspect_jobs(jobs_root: str | Path) -> dict[str, Any]:
    """Read the lock and owner receipt; never clear an interrupted lock."""
    root = Path(jobs_root).expanduser().resolve()
    lock_path = root / LOCK_NAME
    result: dict[str, Any] = {"jobsRoot": str(root), "lockPresent": lock_path.exists(),
                              "recoveryRequired": False}
    if not lock_path.exists():
        return result
    try:
        lock = core.load_json(lock_path)
    except core.RoadcraftError as exc:
        result.update(lockError=str(exc), recoveryRequired=True)
        return result
    result["lock"] = lock
    result["ownerAlive"] = _pid_alive(lock.get("pid"))
    run_id = lock.get("runId")
    if not isinstance(run_id, str) or not ID_PATTERN.fullmatch(run_id):
        result.update(recoveryRequired=True, lockError="Invalid runId in lock")
        return result
    receipt_path = root / run_id / "receipt.json"
    if receipt_path.is_file():
        try:
            receipt = core.load_json(receipt_path)
            result["receipt"] = receipt
            result["recoveryRequired"] = (receipt.get("recoveryRequired") is True or
                                          result["ownerAlive"] is not True)
        except core.RoadcraftError as exc:
            result.update(receiptError=str(exc), recoveryRequired=True)
    else:
        result.update(receiptMissing=True, recoveryRequired=True)
    return result


def _recovery_preflight(jobs_root: Path, run_id: str, expected_lock_sha256: str,
                        expected_receipt_sha256: str, expected_installed_sha256: str,
                        registry_path: Path, expected_registry_sha256: str,
                        config_path: Path, expected_config_sha256: str) -> dict[str, Any]:
    """Prove a retained native lock can be released without touching a package."""
    if not isinstance(run_id, str) or not ID_PATTERN.fullmatch(run_id):
        raise JobError("Recovery requires a safe, exact run ID")
    lock_digest = _digest(expected_lock_sha256, "expected lock SHA-256")
    receipt_digest = _digest(expected_receipt_sha256, "expected receipt SHA-256")
    installed_digest = _digest(expected_installed_sha256, "expected installed SHA-256")
    registry_digest = _digest(expected_registry_sha256, "expected registry SHA-256")
    config_digest = _digest(expected_config_sha256, "expected config SHA-256")
    if not jobs_root.is_dir():
        raise JobError(f"Jobs root is missing: {jobs_root}")
    lock_path = jobs_root / LOCK_NAME
    run_dir = jobs_root / run_id
    receipt_path = run_dir / "receipt.json"
    if lock_path.is_symlink() or run_dir.is_symlink() or receipt_path.is_symlink():
        raise JobError("Recovery refuses a symlinked lock, run directory, or receipt")
    state = inspect_jobs(jobs_root)
    if not state["lockPresent"] or "lockError" in state or "receiptError" in state:
        raise JobError("A readable job lock and owner receipt are required")
    if state.get("ownerAlive") is not False:
        raise JobError("Cannot prove the lock owner has exited")
    lock = state.get("lock", {})
    receipt = state.get("receipt", {})
    if (lock.get("runId") != run_id or receipt.get("runId") != run_id or
            receipt.get("status") not in ("failed", "interrupted") or
            receipt.get("recoveryRequired") is not True):
        raise JobError("Lock and terminal recovery-required receipt must match the run ID")
    lock_identity = core.file_identity(lock_path, lock_digest)
    receipt_identity = core.file_identity(receipt_path, receipt_digest)
    for label, identity in (("lock", lock_identity), ("receipt", receipt_identity)):
        if identity.get("matchesExpected") is not True or identity.get("unchangedDuringRead") is not True:
            raise JobError(f"Reviewed {label} identity is stale or unstable")

    registry_identity = core.file_identity(registry_path, registry_digest)
    config_identity = core.file_identity(config_path, config_digest)
    if any(row.get("matchesExpected") is not True or
           row.get("unchangedDuringRead") is not True
           for row in (registry_identity, config_identity)):
        raise JobError("Reviewed registry or machine config identity is stale or unstable")
    registry = core.read_registry(registry_path)
    config = core.read_config(config_path)
    accepted_pin = registry.get("accepted", {}).get("package") or {}
    if accepted_pin.get("sha256") != installed_digest:
        raise JobError("Expected installed SHA-256 must equal the accepted registry pin")
    if not config.get("installedPackage"):
        raise JobError("Machine config must identify the installed package")
    if not config.get("transactionReceipts") or not config.get("transactionLocks"):
        raise JobError("Machine config must enumerate transaction receipts and locks")
    project = core.status(registry, config)
    accepted = project.get("accepted") or {}
    installed = project.get("installed") or {}
    if (accepted.get("matchesExpected") is not True or
            accepted.get("unchangedDuringRead") is not True or
            installed.get("sha256") != installed_digest or
            installed.get("unchangedDuringRead") is not True or
            project.get("installedRelation") != "accepted" or
            project.get("recoveryRequired") is not False):
        raise JobError("Accepted and installed package or transaction state is not verified")
    if any(not row.get("exists") or row.get("needsReview") is not False
           for row in project["transactionReceipts"]):
        raise JobError("A configured transaction receipt needs review")
    for row in project["transactionReceipts"]:
        if row.get("kind") == "legacy-capture":
            terminal = row.get("status") in (
                "NATIVE_CAPTURES_READY_BASELINE_RESTORED",
                "NATIVE_TRIAGE_CAPTURES_READY_BASELINE_RESTORED",
                "FAIL_ROLLBACK_PENDING",
            )
            if not terminal or row.get("rollbackVerifiedNow") is not True:
                raise JobError("Legacy capture receipt lacks a verified terminal rollback")
        elif row.get("kind") == "package-transaction":
            if row.get("state") not in ("ROLLED_BACK", "NOT_INSTALLED"):
                raise JobError("Package transaction receipt is not terminal at the accepted package")
        else:
            raise JobError("Unknown transaction receipt kind")
    if any(row.get("present") is not False for row in project["transactionLocks"]):
        raise JobError("A configured transaction lock is still present")
    transaction_receipt_identities = [core.file_identity(row["path"])
                                      for row in project["transactionReceipts"]]
    if any(row.get("exists") is not True or row.get("unchangedDuringRead") is not True
           for row in transaction_receipt_identities):
        raise JobError("A configured transaction receipt changed during verification")
    active, error = editor_processes()
    if error:
        raise JobError(f"Cannot inspect authoring processes: {error}")
    if active:
        raise JobError(f"Active authoring processes block recovery: {active}")
    return {"status": "ready", "runId": run_id, "jobsRoot": str(jobs_root),
            "lock": lock_identity, "receipt": receipt_identity,
            "registry": registry_identity, "config": config_identity,
            "installed": installed, "accepted": accepted,
            "installedRelation": project["installedRelation"],
            "transactionReceipts": project["transactionReceipts"],
            "transactionReceiptIdentities": transaction_receipt_identities,
            "transactionLocks": project["transactionLocks"],
            "activeAuthoringProcesses": active}


def recover_jobs(jobs_root: str | Path, run_id: str, expected_lock_sha256: str,
                 expected_receipt_sha256: str, expected_installed_sha256: str,
                 registry_path: str | Path, expected_registry_sha256: str,
                 config_path: str | Path, expected_config_sha256: str,
                 *, dry_run: bool = True) -> dict[str, Any]:
    """Release only an externally verified, reviewed, abandoned job lock.

    The original receipt and installed package are never modified. A separate
    durable recovery receipt records the checks and lock-release outcome.
    """
    root = Path(jobs_root).expanduser().resolve()
    registry = Path(registry_path).expanduser().resolve()
    config = Path(config_path).expanduser().resolve()
    check = _recovery_preflight(root, run_id, expected_lock_sha256,
                                expected_receipt_sha256, expected_installed_sha256,
                                registry, expected_registry_sha256,
                                config, expected_config_sha256)
    if dry_run:
        return {**check, "writesPerformed": False}
    # Recheck immediately before making a durable release record. This catches
    # changes while the first pass hashes the accepted and installed packages.
    check = _recovery_preflight(root, run_id, expected_lock_sha256,
                                expected_receipt_sha256, expected_installed_sha256,
                                registry, expected_registry_sha256,
                                config, expected_config_sha256)
    recovery_path = root / run_id / f"job_recovery_{uuid.uuid4().hex}.json"
    recovery = {"schemaVersion": 1, "runId": run_id,
                "status": "verified_release_pending", "verifiedUtc": _utc(),
                "verification": check}
    with recovery_path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(recovery, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    try:
        lock_path = root / LOCK_NAME
        lock_now = core.file_identity(lock_path, expected_lock_sha256)
        receipt_now = core.file_identity(root / run_id / "receipt.json", expected_receipt_sha256)
        installed_now = core.file_identity(check["installed"]["path"], expected_installed_sha256)
        registry_now = core.file_identity(registry, expected_registry_sha256)
        config_now = core.file_identity(config, expected_config_sha256)
        transaction_receipts_now = [core.file_identity(row["path"], row["sha256"])
                                    for row in check["transactionReceiptIdentities"]]
        owner_now = core.load_json(lock_path).get("pid") if lock_now.get("matchesExpected") else None
        active_now, process_error = editor_processes()
        if (lock_path.is_symlink() or (root / run_id).is_symlink() or
                (root / run_id / "receipt.json").is_symlink() or
                lock_now.get("matchesExpected") is not True or
                lock_now.get("unchangedDuringRead") is not True or
                receipt_now.get("matchesExpected") is not True or
                receipt_now.get("unchangedDuringRead") is not True or
                installed_now.get("matchesExpected") is not True or
                installed_now.get("unchangedDuringRead") is not True or
                registry_now.get("matchesExpected") is not True or
                registry_now.get("unchangedDuringRead") is not True or
                config_now.get("matchesExpected") is not True or
                config_now.get("unchangedDuringRead") is not True or
                any(row.get("matchesExpected") is not True or
                    row.get("unchangedDuringRead") is not True
                    for row in transaction_receipts_now) or
                _pid_alive(owner_now) is not False or
                process_error or active_now or
                any(Path(row["path"]).exists() for row in check["transactionLocks"])):
            raise JobError("External state or reviewed evidence changed before release")
        lock_path.unlink()
        recovery.update(status="released", releasedUtc=_utc())
    except Exception as exc:
        recovery.update(status="release_failed", error=str(exc), finishedUtc=_utc())
        _atomic_json(recovery_path, recovery)
        raise
    _atomic_json(recovery_path, recovery)
    return {**check, "status": "released", "writesPerformed": True,
            "recoveryReceiptPath": str(recovery_path),
            "recoveryReceiptSha256": core.sha256_file(recovery_path)}


def _verify_outputs(step: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    rows = [core.file_identity(pin["path"], pin["sha256"]) for pin in step["outputs"]]
    passed = all(row["exists"] and row.get("unchangedDuringRead") and
                 row.get("matchesExpected", True) for row in rows)
    return rows, passed


def _run_command(step: dict[str, Any], log_path: Path) -> int:
    """Publish a complete log atomically, retaining .partial on hard crashes."""
    partial = log_path.with_name(f".{log_path.name}.partial")
    try:
        with partial.open("xb") as log:
            creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            try:
                completed = subprocess.run(
                    step["command"], cwd=step["cwd"],
                    env={**os.environ, **step["env"]},
                    stdout=log, stderr=subprocess.STDOUT, shell=False,
                    timeout=step["timeoutSeconds"], creationflags=creation_flags,
                    check=False,
                )
            finally:
                log.flush()
                os.fsync(log.fileno())
    finally:
        if partial.exists():
            os.replace(partial, log_path)
    return completed.returncode


def run_recipe(recipe_path: str | Path, phase: str, jobs_root: str | Path,
               *, dry_run: bool = False, incremental_build: bool = False) -> dict[str, Any]:
    """Run one phase serially, recording every completed step atomically.

    Any phase failure after a native command starts retains the lock and reports
    recoveryRequired, including nonzero exit and missing expected outputs.
    `recover_jobs` can release it only after the external package/editor and
    transaction state passes pinned verification; no blind recovery occurs.
    """
    plan = load_recipe(recipe_path, phase)
    generated: set[str] = set()
    if dry_run:
        planned = []
        for step in plan["steps"]:
            check = _preflight_step(step, generated=generated, dry_run=True)
            planned.append({"id": step["id"], "status": "ready",
                            "command": step["command"], "cwd": step["cwd"],
                            "inputs": check["inputs"], "outputs": step["outputs"],
                            "freeBytes": check["freeBytes"],
                            "timeoutSeconds": step["timeoutSeconds"],
                            "minFreeBytes": step["minFreeBytes"], "native": step["native"],
                            "cacheable": step["cacheable"], "dependsOn": step["dependsOn"],
                            "outputTrees": step["outputTrees"]})
            generated.update(pin["path"] for pin in step["outputs"])
        return {"status": "dry_run", "recipePath": plan["recipePath"],
                "recipeSha256": plan["recipeSha256"], "name": plan["name"],
                "phase": phase, "steps": planned, "writesPerformed": False,
                "incrementalRequested": incremental_build}

    root = Path(jobs_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:12]}"
    lock_path = _lock(root, run_id)
    run_dir = root / run_id
    receipt_path = run_dir / "receipt.json"
    receipt: dict[str, Any] = {"schemaVersion": 1, "runId": run_id, "name": plan["name"],
                               "phase": phase, "recipePath": plan["recipePath"],
                               "recipeSha256": plan["recipeSha256"],
                               "startedUtc": _utc(), "status": "running",
                               "recoveryRequired": False, "steps": []}
    retain_lock = False
    native_command_started = False
    current_step: dict[str, Any] | None = None
    cache_entries = incremental.read_index(root) if incremental_build else {}
    try:
        run_dir.mkdir(exist_ok=False)
        _atomic_json(receipt_path, receipt)
        for step in plan["steps"]:
            current_step = step
            if core.sha256_file(plan["recipePath"]) != plan["recipeSha256"]:
                raise JobError("Recipe changed after planning")
            log_path = run_dir / f"{step['id']}.log"
            row: dict[str, Any] = {"id": step["id"], "status": "preflight",
                                   "startedUtc": _utc(), "command": step["command"],
                                   "cwd": step["cwd"], "native": step["native"],
                                   "log": str(log_path)}
            receipt["steps"].append(row)
            _atomic_json(receipt_path, receipt)
            check = _preflight_step(step)
            row.update(status="running", inputChecks=check["inputs"],
                       freeBytesAtStart=check["freeBytes"])
            if incremental_build and step["cacheable"]:
                row["cacheKey"] = incremental.fingerprint(step, receipt["steps"][:-1])
                reuse = incremental.lookup(root, cache_entries, row["cacheKey"], step)
                if reuse:
                    outputs, valid = _verify_outputs(step)
                    if valid and [p.get("sha256") for p in outputs] == [p.get("sha256") for p in reuse["outputChecks"]]:
                        row.pop("log", None)  # A reused step has no new command log.
                        row.update(status="cached", outputChecks=outputs, finishedUtc=_utc(),
                                   reusedFrom={k: reuse[k] for k in ("receiptPath", "receiptSha256", "runId")},
                                   executionSeconds=reuse["executionSeconds"], outputTreeChecks=reuse["outputTreeChecks"])
                        _atomic_json(receipt_path, receipt)
                        continue
            _atomic_json(receipt_path, receipt)
            execution_started = time.monotonic()
            try:
                # Any later phase failure leaves a native command's external
                # package/editor state unproven, including a nonzero exit.
                native_command_started |= step["native"]
                row["exitCode"] = _run_command(step, log_path)
            except subprocess.TimeoutExpired:
                row["status"] = "timed_out"
                row["error"] = f"Exceeded {step['timeoutSeconds']} seconds"
                row["logSha256"] = core.sha256_file(log_path) if log_path.is_file() else None
                retain_lock = native_command_started
                raise JobError(f"Step {step['id']} timed out")
            row["logSha256"] = core.sha256_file(log_path)
            if row["exitCode"] != 0:
                row["status"] = "failed"
                raise JobError(f"Step {step['id']} exited {row['exitCode']}")
            # Inputs must remain pinned after execution, too. This catches
            # commands that silently rewrite an accepted source while building.
            for pin in step["inputs"]:
                identity = core.file_identity(pin["path"], pin["sha256"])
                if not identity.get("matchesExpected") or not identity.get("unchangedDuringRead"):
                    row["status"] = "failed"
                    raise JobError(f"Step {step['id']} changed pinned input {pin['path']}")
            outputs, valid = _verify_outputs(step)
            row["outputChecks"] = outputs
            if not valid:
                row["status"] = "failed"
                raise JobError(f"Step {step['id']} missing or mismatched expected outputs")
            row["outputTreeChecks"] = incremental.capture_trees(step["outputTrees"])
            row.update(status="passed", finishedUtc=_utc(),
                       executionSeconds=round(time.monotonic() - execution_started, 6))
            _atomic_json(receipt_path, receipt)
        receipt.update(status="passed", finishedUtc=_utc())
        receipt["incremental"] = {
            "requested": incremental_build,
            "executedSteps": sum(r["status"] == "passed" for r in receipt["steps"]),
            "reusedSteps": sum(r["status"] == "cached" for r in receipt["steps"]),
            "previousExecutionSecondsReused": round(sum(r.get("executionSeconds", 0)
                                                       for r in receipt["steps"] if r["status"] == "cached"), 6)}
        _atomic_json(receipt_path, receipt)
        if incremental_build:
            _atomic_json(root / incremental.INDEX, incremental.add_receipt(cache_entries, receipt, receipt_path))
    except KeyboardInterrupt:
        retain_lock = native_command_started
        receipt.update(status="interrupted", recoveryRequired=retain_lock,
                       error="Interrupted by operator", finishedUtc=_utc())
        if receipt["steps"] and receipt["steps"][-1]["status"] in ("preflight", "running"):
            receipt["steps"][-1].update(status="interrupted", finishedUtc=_utc())
        if run_dir.exists():
            _atomic_json(receipt_path, receipt)
    except Exception as exc:
        retain_lock |= native_command_started
        receipt.update(status="failed", recoveryRequired=retain_lock,
                       error=str(exc), finishedUtc=_utc())
        if receipt["steps"] and receipt["steps"][-1]["status"] in ("preflight", "running"):
            receipt["steps"][-1].update(status="failed", error=str(exc), finishedUtc=_utc())
        if run_dir.exists():
            _atomic_json(receipt_path, receipt)
    finally:
        if not retain_lock:
            try:
                held = core.load_json(lock_path)
            except core.RoadcraftError:
                held = {}
            if held.get("runId") == run_id and held.get("pid") == os.getpid():
                lock_path.unlink(missing_ok=True)
    return receipt
