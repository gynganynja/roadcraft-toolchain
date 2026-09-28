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
import uuid
from typing import Any

from . import core


PHASES = frozenset({"build", "inspect", "test", "capture"})
LOCK_NAME = ".roadcraft-jobs.lock"
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


class JobError(core.RoadcraftError):
    """Recipe or execution could not be completed safely."""


class JobBusy(JobError):
    """A run or an interrupted native run holds the shared jobs lock."""


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        step_inputs = _items(row.get("inputs", []), f"Step {step_id} inputs", source, output=False)
        inputs = [*default_inputs, *step_inputs]
        if len({x["path"].casefold() for x in inputs}) != len(inputs):
            raise JobError(f"Step {step_id} repeats an input path")
        outputs = _items(row.get("outputs", []), f"Step {step_id} outputs", source, output=True)
        if not outputs:
            raise JobError(f"Step {step_id} needs at least one expected output")
        env = row.get("env", defaults.get("env", {}))
        if (not isinstance(env, dict) or
                any(not isinstance(k, str) or not k or not isinstance(v, str)
                    for k, v in env.items())):
            raise JobError(f"Step {step_id} env must map nonempty names to strings")
        result_steps.append({"id": step_id, "command": command, "cwd": str(cwd),
                             "inputs": inputs, "outputs": outputs,
                             "timeoutSeconds": timeout, "minFreeBytes": minimum,
                             "native": native, "env": env})
    return {"name": name, "phase": phase, "recipePath": str(source),
            "recipeSha256": core.sha256_file(source), "steps": result_steps}


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
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


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
    if not isinstance(pid, int) or pid <= 0:
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
               *, dry_run: bool = False) -> dict[str, Any]:
    """Run one phase serially, recording every completed step atomically.

    A timeout or interruption of a native step retains the lock and reports
    recoveryRequired. Callers must verify the external package/editor state
    before clearing such a lock; this module does not perform blind recovery.
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
                            "minFreeBytes": step["minFreeBytes"], "native": step["native"]})
            generated.update(pin["path"] for pin in step["outputs"])
        return {"status": "dry_run", "recipePath": plan["recipePath"],
                "recipeSha256": plan["recipeSha256"], "name": plan["name"],
                "phase": phase, "steps": planned, "writesPerformed": False}

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
    current_step: dict[str, Any] | None = None
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
            _atomic_json(receipt_path, receipt)
            try:
                row["exitCode"] = _run_command(step, log_path)
            except subprocess.TimeoutExpired:
                row["status"] = "timed_out"
                row["error"] = f"Exceeded {step['timeoutSeconds']} seconds"
                row["logSha256"] = core.sha256_file(log_path) if log_path.is_file() else None
                retain_lock = step["native"]
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
            row.update(status="passed", finishedUtc=_utc())
            _atomic_json(receipt_path, receipt)
        receipt.update(status="passed", finishedUtc=_utc())
        _atomic_json(receipt_path, receipt)
    except KeyboardInterrupt:
        retain_lock = bool(current_step and current_step["native"])
        receipt.update(status="interrupted", recoveryRequired=retain_lock,
                       error="Interrupted by operator", finishedUtc=_utc())
        if receipt["steps"] and receipt["steps"][-1]["status"] in ("preflight", "running"):
            receipt["steps"][-1].update(status="interrupted", finishedUtc=_utc())
        if run_dir.exists():
            _atomic_json(receipt_path, receipt)
    except Exception as exc:
        if current_step and receipt["steps"] and receipt["steps"][-1]["status"] == "running":
            # Unknown failures during a native command need external review.
            retain_lock |= current_step["native"] and not isinstance(exc, JobError)
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
