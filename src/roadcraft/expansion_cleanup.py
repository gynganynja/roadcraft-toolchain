"""Execute only the exact files in a pinned retail-export expansion review.

The review is evidence, not a deletion instruction.  This command defaults to
dry-run.  Applying requires both ``--apply`` and the exact manifest SHA-256;
it records a durable write-ahead, per-file journal so interrupted runs can be
resumed without broad directory cleanup.
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any, Callable, Iterator
import zipfile

from . import cleanup, core


SHA256 = re.compile(r"^[0-9a-f]{64}$")
UNSAFE_ATTRIBUTES = 0x400 | 0x800 | 0x200  # reparse, compressed, sparse
PROCESS_TOKENS = ("roadcraft", "modeditor", "integrationstudio", "furnace",
                  "mod_pak_builder", "retail_export")
SCRIPT_HOST_TOKENS = ("python", "pypy", "py.exe", "pyw.exe")


class ExpansionCleanupBlocked(RuntimeError):
    """A candidate, retained copy, or execution gate has drifted."""


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _absolute(raw: str | Path, label: str) -> Path:
    if not isinstance(raw, (str, Path)) or not str(raw):
        raise ExpansionCleanupBlocked(f"{label} is missing")
    path = Path(raw)
    if not path.is_absolute() or ".." in path.parts:
        raise ExpansionCleanupBlocked(f"{label} must be an absolute path without traversal: {path}")
    return path


def _inside(path: Path, root: Path) -> bool:
    try:
        return path != root and path.is_relative_to(root)
    except ValueError:
        return False


def _plain(path: Path, label: str, *, regular: bool = False) -> os.stat_result:
    """Reject reparse ancestors before any hashing or path-based unlink."""
    for component in reversed((path, *path.parents)):
        try:
            info = component.lstat()
        except OSError as exc:
            raise ExpansionCleanupBlocked(f"{label} is missing or unreadable: {component}") from exc
        if component.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ExpansionCleanupBlocked(f"{label} crosses a symlink or reparse point: {component}")
    info = path.lstat()
    if regular and not stat.S_ISREG(info.st_mode):
        raise ExpansionCleanupBlocked(f"{label} is not a regular file: {path}")
    return info


def _snapshot(path: Path, label: str, *, candidate: bool = False) -> dict[str, Any]:
    before = _plain(path, label, regular=True)
    attrs = getattr(before, "st_file_attributes", 0)
    if candidate and attrs & UNSAFE_ATTRIBUTES:
        raise ExpansionCleanupBlocked(f"{label} has unsafe file attributes: {path}")
    digest = _sha(path)
    after = _plain(path, label, regular=True)
    observed = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
                after.st_nlink, getattr(after, "st_file_attributes", 0))
    prior = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
             before.st_nlink, attrs)
    if observed != prior:
        raise ExpansionCleanupBlocked(f"{label} changed during hashing: {path}")
    return {"path": str(path), "sha256": digest, "logicalBytes": after.st_size,
            "allocatedBytes": cleanup.allocated_bytes(path),
            "fileId": f"{after.st_dev}:{after.st_ino}", "hardLinks": after.st_nlink,
            "mtimeNs": after.st_mtime_ns, "attributes": attrs}


def _manifest(path: Path, pin: str | None, *, apply: bool) -> tuple[dict[str, Any], str]:
    if apply and not pin:
        raise ExpansionCleanupBlocked("--apply requires an exact --manifest-sha256 pin")
    if pin and not SHA256.fullmatch(pin.lower()):
        raise ExpansionCleanupBlocked("manifest SHA-256 pin must be 64 hex characters")
    _plain(path, "review manifest", regular=True)
    actual = _sha(path)
    if pin and actual != pin.lower():
        raise ExpansionCleanupBlocked(f"review manifest differs from pinned SHA-256: {actual}")
    try:
        review = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ExpansionCleanupBlocked("review manifest is unreadable or malformed") from exc
    if (not isinstance(review, dict) or review.get("schemaVersion") != 1 or
            not isinstance(review.get("candidates"), list) or not review["candidates"] or
            not isinstance(review.get("stages"), list) or not review["stages"] or
            review.get("candidateCount") != len(review["candidates"]) or
            review.get("candidateAllocatedBytes") != sum(
                row.get("allocatedBytes", -1) for row in review["candidates"]
                if isinstance(row, dict))):
        raise ExpansionCleanupBlocked("review candidate totals or schema are inconsistent")
    return review, actual


def _validate_rows(review: dict[str, Any]) -> tuple[Path, list[dict[str, Any]], dict[str, dict[str, Any]]]:
    scope = _absolute(review.get("scope"), "review scope")
    _plain(scope, "review scope")
    if not scope.is_dir():
        raise ExpansionCleanupBlocked("review scope is not a directory")
    stages: dict[str, dict[str, Any]] = {}
    for stage in review["stages"]:
        if not isinstance(stage, dict):
            raise ExpansionCleanupBlocked("malformed stage row")
        stage_path = _absolute(stage.get("stage"), "stage")
        project = _absolute(stage.get("project"), "stage project")
        if not _inside(stage_path, scope) or project != stage_path / "project":
            raise ExpansionCleanupBlocked(f"stage escapes review scope: {stage_path}")
        key = str(stage_path).casefold()
        if key in stages:
            raise ExpansionCleanupBlocked(f"duplicate stage: {stage_path}")
        stages[key] = stage
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    counts: dict[str, int] = {key: 0 for key in stages}
    allocated: dict[str, int] = {key: 0 for key in stages}
    for row in review["candidates"]:
        if not isinstance(row, dict):
            raise ExpansionCleanupBlocked("malformed candidate row")
        candidate = _absolute(row.get("path"), "candidate")
        key = str(candidate).casefold()
        stage_key = str(_absolute(row.get("stage"), "candidate stage")).casefold()
        stage = stages.get(stage_key)
        if key in seen or stage is None or stage.get("status") != "reviewed":
            raise ExpansionCleanupBlocked(f"duplicate or unreviewed candidate: {candidate}")
        seen.add(key)
        expected_root = _absolute(stage["project"], "project") / "mods_source"
        if not _inside(candidate, expected_root) or not _inside(candidate, scope):
            raise ExpansionCleanupBlocked(f"candidate escapes reviewed mods_source: {candidate}")
        if (row.get("classification") != "generated-retail-export-copy" or
                row.get("executionStatus") != "review-candidate-only-active-ownership-recheck-required" or
                not isinstance(row.get("logicalBytes"), int) or row["logicalBytes"] < 0 or
                not isinstance(row.get("allocatedBytes"), int) or row["allocatedBytes"] < 0 or
                row.get("hardLinks") != 1 or
                not isinstance(row.get("fileId"), str) or
                not isinstance(row.get("mtimeNs"), int) or
                not isinstance(row.get("attributes"), int) or
                not isinstance(row.get("sha256"), str) or
                not SHA256.fullmatch(row["sha256"])):
            raise ExpansionCleanupBlocked(f"candidate has invalid review fields: {candidate}")
        retained = row.get("retainedOriginal")
        if not isinstance(retained, dict) or retained.get("kind") not in (
                "retained-package-member", "retained-source-texture-copy"):
            raise ExpansionCleanupBlocked(f"candidate lacks supported retained counterpart: {candidate}")
        original = _absolute(retained.get("path"), "retained counterpart")
        if not _inside(original, scope) or original == candidate:
            raise ExpansionCleanupBlocked(f"retained counterpart escapes scope: {original}")
        if retained["kind"] == "retained-package-member":
            package = stage.get("retainedPackage")
            if (not isinstance(package, dict) or package.get("path") != str(original) or
                    package.get("sha256") != retained.get("packageSha256") or
                    not isinstance(retained.get("occurrences"), list) or
                    not retained["occurrences"]):
                raise ExpansionCleanupBlocked(f"package evidence differs: {candidate}")
        elif retained.get("sha256") != row["sha256"]:
            raise ExpansionCleanupBlocked(f"retained texture hash differs: {candidate}")
        counts[stage_key] += 1
        allocated[stage_key] += row["allocatedBytes"]
        rows.append(row)
    if any(str(_absolute(row["retainedOriginal"]["path"], "retained counterpart")).casefold()
           in seen for row in rows):
        raise ExpansionCleanupBlocked("a retained counterpart is itself listed for deletion")
    for key, stage in stages.items():
        if (counts[key] != stage.get("candidateFiles") or
                allocated[key] != stage.get("candidateAllocatedBytes") or
                (counts[key] and stage.get("executableOrMarkdownReferences") != [])):
            raise ExpansionCleanupBlocked(f"stage totals or reference review differ: {stage['stage']}")
    return scope, rows, stages


def _verify_candidate(row: dict[str, Any]) -> dict[str, Any]:
    candidate = _absolute(row["path"], "candidate")
    current = _snapshot(candidate, "candidate", candidate=True)
    for field in ("logicalBytes", "allocatedBytes", "fileId", "hardLinks",
                  "mtimeNs", "attributes", "sha256"):
        if current[field] != row[field]:
            raise ExpansionCleanupBlocked(f"candidate drift ({field}): {candidate}")
    return current


def _verify_retained(row: dict[str, Any], archives: dict[str, zipfile.ZipFile],
                     source_cache: dict[str, dict[str, Any]]) -> None:
    retained = row["retainedOriginal"]
    original = _absolute(retained["path"], "retained counterpart")
    if retained["kind"] == "retained-source-texture-copy":
        current = source_cache.get(str(original).casefold())
        if current is None:
            current = _snapshot(original, "retained texture")
            source_cache[str(original).casefold()] = current
        if current["sha256"] != retained["sha256"] or current["sha256"] != row["sha256"]:
            raise ExpansionCleanupBlocked(f"retained texture drift: {original}")
        return
    archive = archives.get(str(original).casefold())
    if archive is None:
        raise ExpansionCleanupBlocked(f"retained package was not verified: {original}")
    infos = archive.infolist()
    for occurrence in retained["occurrences"]:
        if (not isinstance(occurrence, dict) or
                not isinstance(occurrence.get("index"), int) or
                occurrence["index"] < 0 or occurrence["index"] >= len(infos) or
                not isinstance(occurrence.get("member"), str) or
                not isinstance(occurrence.get("bytes"), int) or
                occurrence.get("sha256") != row["sha256"]):
            raise ExpansionCleanupBlocked(f"invalid retained package occurrence: {original}")
        info = infos[occurrence["index"]]
        if info.filename.replace("\\", "/") != occurrence["member"] or info.file_size != occurrence["bytes"]:
            raise ExpansionCleanupBlocked(f"retained package member drift: {original}")
        digest = hashlib.sha256()
        with archive.open(info) as stream:
            for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != occurrence["sha256"]:
            raise ExpansionCleanupBlocked(f"retained package member hash drift: {original}")


def _git_state(scope: Path, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    prefix = ["git", "--no-optional-locks", "-c", f"safe.directory={scope.as_posix()}",
              "-C", str(scope)]
    def run(*args: str) -> bytes:
        result = subprocess.run([*prefix, *args], capture_output=True, check=False)
        if result.returncode:
            raise ExpansionCleanupBlocked(f"Git inspection failed: {result.stderr.decode(errors='replace').strip()}")
        return result.stdout
    root = Path(os.fsdecode(run("rev-parse", "--show-toplevel")).strip()).resolve()
    if root != scope.resolve():
        raise ExpansionCleanupBlocked(f"Git root differs from review scope: {root}")
    tracked = {name.replace(b"\\", b"/").lower() for name in run("ls-files", "-z", "--cached").split(b"\0") if name}
    candidate_rel = {os.fsencode(str(Path(row["path"]).relative_to(scope)).replace("\\", "/")).lower()
                     for row in candidates}
    tracked_candidates = tracked.intersection(candidate_rel)
    status = run("status", "--porcelain=v1", "-z", "--untracked-files=no")
    return {"head": os.fsdecode(run("rev-parse", "HEAD")).strip(),
            "trackedCandidateCount": len(tracked_candidates),
            "trackedCandidates": [os.fsdecode(x) for x in sorted(tracked_candidates)[:10]],
            "trackedStatusSha256": hashlib.sha256(status).hexdigest(),
            "trackedStatusEntries": status.count(b"\0")}


def _command_line_processes() -> tuple[dict[int, dict[str, Any]], str | None]:
    """Read all command lines so missing interpreter rows cannot look idle."""
    script = ("$ErrorActionPreference='Stop'; "
              "Get-CimInstance Win32_Process | "
              "Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress")
    try:
        result = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                                capture_output=True, text=True, check=False)
    except OSError as exc:
        return {}, f"command-line query failed: {exc}"
    if result.returncode:
        return {}, f"command-line query failed: {result.stderr.strip() or 'unknown error'}"
    try:
        raw = json.loads(result.stdout)
        rows = raw if isinstance(raw, list) else [raw]
        if not rows or not all(isinstance(row, dict) and
                               isinstance(row.get("ProcessId"), int) and
                               isinstance(row.get("Name"), str) for row in rows):
            raise ValueError("missing process rows or identity fields")
        return {row["ProcessId"]: row for row in rows}, None
    except (ValueError, TypeError) as exc:
        return {}, f"command-line process response is invalid: {exc}"


def _script_host(name: str) -> bool:
    name = name.casefold()
    return "python" in name or "pypy" in name or name in ("py.exe", "pyw.exe")


def _classify_processes(snapshot: list[dict[str, Any]],
                        command_lines: dict[int, dict[str, Any]],
                        command_line_error: str | None,
                        *, own_pid: int) -> list[dict[str, Any]]:
    """Fail closed for script hosts whose command line was not inspected."""
    active: list[dict[str, Any]] = []
    seen: set[int] = set()
    for row in snapshot:
        pid = row["pid"]
        name = str(row["name"])
        lowered = name.casefold()
        named = any(token in lowered for token in PROCESS_TOKENS)
        host = _script_host(name)
        if pid == own_pid and host and not named:
            continue
        if not (named or host):
            continue
        seen.add(pid)
        cim_row = command_lines.get(pid, {})
        # A PID reused between snapshots is not evidence about the earlier
        # script host.  Require its process name to agree as well.
        command = (cim_row.get("CommandLine") if
                   str(cim_row.get("Name", "")).casefold() == lowered else None)
        if named:
            reason = "known-game-or-export-process"
        elif command_line_error or not isinstance(command, str) or not command:
            reason = "uninspectable-script-host"
        elif "retail_export.py" in command.casefold():
            reason = "retail-export-script"
        else:
            continue
        finding = {"pid": pid, "name": name, "reason": reason}
        if reason == "retail-export-script":
            finding["commandLine"] = command
        active.append(finding)
    # A process can start between the Toolhelp and CIM snapshots.  A newly
    # observed export command is still active even if Toolhelp missed it.
    for pid, row in command_lines.items():
        command = row.get("CommandLine")
        if pid not in seen and pid != own_pid and isinstance(command, str) and \
                "retail_export.py" in command.casefold():
            active.append({"pid": pid, "name": row["Name"],
                           "reason": "retail-export-script", "commandLine": command})
    return active


def _process_state() -> tuple[list[dict[str, Any]], str | None, dict[str, Any]]:
    snapshot, error = core._editor_processes(tokens=PROCESS_TOKENS + SCRIPT_HOST_TOKENS)
    if error:
        return [], error, {"method": "toolhelp-process-names", "complete": False}
    if os.name != "nt":
        return [], "Windows export-job inspection is unavailable", \
            {"method": "toolhelp-process-names", "complete": False}
    command_lines, command_line_error = _command_line_processes()
    active = _classify_processes(snapshot, command_lines, command_line_error,
                                 own_pid=os.getpid())
    return active, command_line_error, {
        "method": "toolhelp-plus-cim" if command_line_error is None else
                  "toolhelp-conservative-script-host-block",
        "complete": command_line_error is None,
        "commandLinesAvailable": command_line_error is None,
        "commandLineQueryError": command_line_error,
        "snapshotMatchingProcessCount": len(snapshot),
        "commandLineProcessCount": len(command_lines),
        "ownPidExcluded": os.getpid(),
    }


def _checked_processes(checker: Callable[..., Any]) -> tuple[list[dict[str, Any]], str | None, dict[str, Any]]:
    checked = checker()
    if len(checked) == 2:
        processes, error = checked
        return processes, error, {"method": "external-checker", "complete": not bool(error)}
    return checked


@contextmanager
def _lock(receipt: Path) -> Iterator[None]:
    lock = receipt.with_name(receipt.name + ".lock")
    _plain(receipt.parent, "receipt parent")
    with lock.open("a+b", buffering=0) as stream:
        if stream.seek(0, os.SEEK_END) == 0:
            stream.write(b"\0")
            os.fsync(stream.fileno())
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise ExpansionCleanupBlocked(f"cleanup receipt is locked: {receipt}") from exc
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
                raise ExpansionCleanupBlocked(f"cleanup receipt is locked: {receipt}") from exc
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _append(receipt: Path, event: dict[str, Any]) -> None:
    with receipt.open("ab") as stream:
        stream.write((json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n").encode())
        stream.flush()
        os.fsync(stream.fileno())


def _receipt_state(receipt: Path, manifest_sha: str, rows: list[dict[str, Any]],
                   scope: Path) -> tuple[int, bool, bool]:
    if not receipt.exists():
        _append(receipt, {"type": "start", "schemaVersion": 1,
                          "manifestSha256": manifest_sha, "scope": str(scope),
                          "candidateCount": len(rows), "utc": _utc()})
        return 0, False, False
    _plain(receipt, "cleanup receipt", regular=True)
    try:
        events = [json.loads(line) for line in receipt.read_text(encoding="utf-8").splitlines()]
    except (OSError, UnicodeError, ValueError) as exc:
        raise ExpansionCleanupBlocked("cleanup receipt is unreadable or malformed") from exc
    if not events or events[0].get("type") != "start" or events[0].get("schemaVersion") != 1 or \
            events[0].get("manifestSha256") != manifest_sha or events[0].get("scope") != str(scope) or \
            events[0].get("candidateCount") != len(rows):
        raise ExpansionCleanupBlocked("cleanup receipt does not match pinned review")
    index = 0
    pending = False
    complete = False
    for event in events[1:]:
        kind = event.get("type")
        if complete or kind not in ("intent", "deleted", "complete"):
            raise ExpansionCleanupBlocked("cleanup receipt has invalid event sequence")
        if kind == "complete":
            if index != len(rows) or pending:
                raise ExpansionCleanupBlocked("cleanup completed before all files were recorded")
            complete = True
            continue
        if index >= len(rows) or event.get("index") != index or \
                event.get("path") != rows[index]["path"] or \
                event.get("sha256") != rows[index]["sha256"] or \
                event.get("fileId") != rows[index]["fileId"]:
            raise ExpansionCleanupBlocked("cleanup receipt file event differs from manifest")
        if kind == "intent":
            if pending:
                raise ExpansionCleanupBlocked("cleanup receipt has two uncommitted intents")
            pending = True
        elif not pending:
            raise ExpansionCleanupBlocked("cleanup receipt records deletion without intent")
        else:
            index += 1
            pending = False
    return index, pending, complete


def _event(kind: str, index: int, row: dict[str, Any]) -> dict[str, Any]:
    return {"type": kind, "index": index, "path": row["path"],
            "sha256": row["sha256"], "fileId": row["fileId"], "utc": _utc()}


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def execute_expansion_cleanup(
    manifest_path: str | Path, *, manifest_sha256: str | None = None,
    apply: bool = False, receipt_path: str | Path | None = None,
    dry_run_output: str | Path | None = None,
    sample_candidates: int | None = None,
    process_checker: Callable[..., Any] = _process_state,
    git_checker: Callable[[Path, list[dict[str, Any]]], dict[str, Any]] = _git_state,
) -> dict[str, Any]:
    """Verify all listed files; optionally unlink exact files with resume journal.

    No directory, archive, or unlisted file is ever removed.  An existing
    receipt resumes only the same manifest and only after all remaining files
    and retained counterparts pass the full preflight again.
    """
    manifest = _absolute(manifest_path, "manifest")
    review, manifest_hash = _manifest(manifest, manifest_sha256, apply=apply)
    scope, rows, stages = _validate_rows(review)
    if sample_candidates is not None and (apply or sample_candidates < 1):
        raise ExpansionCleanupBlocked("sample-candidates is positive and dry-run only")
    receipt = _absolute(receipt_path, "receipt") if receipt_path is not None else None
    if apply and receipt is None:
        raise ExpansionCleanupBlocked("--apply requires an external --receipt path")
    if receipt is not None and (_inside(receipt, scope) or receipt == manifest):
        raise ExpansionCleanupBlocked("receipt must be outside review scope and manifest")

    if sample_candidates is not None:
        selected = rows[:sample_candidates]
        with ExitStack() as stack:
            archives: dict[str, zipfile.ZipFile] = {}
            source_cache: dict[str, dict[str, Any]] = {}
            for row in selected:
                _verify_candidate(row)
                original = row["retainedOriginal"]
                if original["kind"] == "retained-package-member":
                    path = _absolute(original["path"], "retained package")
                    key = str(path).casefold()
                    if key not in archives:
                        stage = stages[str(Path(row["stage"])).casefold()]
                        if _snapshot(path, "retained package")["sha256"] != stage["retainedPackage"]["sha256"]:
                            raise ExpansionCleanupBlocked(f"retained package drift: {path}")
                        archives[key] = stack.enter_context(zipfile.ZipFile(path))
                _verify_retained(row, archives, source_cache)
            git = git_checker(scope, rows)
            processes, process_error, process_inspection = _checked_processes(process_checker)
        result = {"operation": "remove-reviewed-retail-export-files", "dryRun": True,
                  "partialSample": True, "applyReady": False,
                  "manifest": str(manifest), "manifestSha256": manifest_hash,
                  "scope": str(scope), "candidateCount": len(rows),
                  "sampleCandidateCount": len(selected), "sampleSelection": "first manifest rows",
                  "sampledRetainedSourceFiles": len(source_cache),
                  "sampledRetainedPackages": len(archives),
                  "git": git, "activeProcesses": processes,
                  "processInspectionError": process_error,
                  "processInspection": process_inspection, "checkedUtc": _utc(),
                  "deletedCount": 0}
        if dry_run_output is not None:
            output = _absolute(dry_run_output, "dry-run output")
            if _inside(output, scope) or output == manifest:
                raise ExpansionCleanupBlocked("dry-run output must be outside review scope and manifest")
            _write_json(output, result)
            result["output"] = str(output)
        return result

    def inspect(next_index: int, pending: bool) -> tuple[dict[str, Any], dict[str, zipfile.ZipFile], ExitStack]:
        stack = ExitStack()
        archives: dict[str, zipfile.ZipFile] = {}
        try:
            for stage in stages.values():
                if stage.get("candidateFiles", 0) == 0:
                    continue
                for field in ("retainedAudit", "retainedPackage", "retainedSourceSnapshot"):
                    item = stage.get(field)
                    if not isinstance(item, dict) or not isinstance(item.get("sha256"), str):
                        raise ExpansionCleanupBlocked(f"stage lacks sealed {field}: {stage['stage']}")
                    path = _absolute(item.get("path"), field)
                    if not _inside(path, scope) or _snapshot(path, field)["sha256"] != item["sha256"]:
                        raise ExpansionCleanupBlocked(f"stage {field} differs: {path}")
                    if field == "retainedPackage":
                        archives[str(path).casefold()] = stack.enter_context(zipfile.ZipFile(path))
            source_cache: dict[str, dict[str, Any]] = {}
            for index, row in enumerate(rows):
                candidate = Path(row["path"])
                if index < next_index:
                    if candidate.exists() or candidate.is_symlink():
                        raise ExpansionCleanupBlocked(f"receipt says deleted but file exists: {candidate}")
                elif not (index == next_index and pending and not candidate.exists() and not candidate.is_symlink()):
                    _verify_candidate(row)
                elif not stat.S_ISDIR(_plain(candidate.parent, "pending candidate parent").st_mode):
                    raise ExpansionCleanupBlocked(f"pending candidate parent is invalid: {candidate.parent}")
                _verify_retained(row, archives, source_cache)
            git = git_checker(scope, rows)
            processes, process_error, process_inspection = _checked_processes(process_checker)
            ready = not git.get("trackedCandidateCount") and not processes and not process_error
            result = {"operation": "remove-reviewed-retail-export-files", "dryRun": not apply,
                      "manifest": str(manifest), "manifestSha256": manifest_hash,
                      "scope": str(scope), "candidateCount": len(rows),
                      "candidateAllocatedBytes": sum(row["allocatedBytes"] for row in rows),
                      "verifiedRetainedSourceFiles": len(source_cache),
                      "verifiedRetainedPackages": len(archives),
                      "alreadyDeletedCount": next_index,
                      "git": git, "activeProcesses": processes,
                      "processInspectionError": process_error,
                      "processInspection": process_inspection, "applyReady": ready,
                      "checkedUtc": _utc(), "deletedCount": 0}
            return result, archives, stack
        except BaseException:
            stack.close()
            raise

    if not apply:
        result, _, stack = inspect(0, False)
        stack.close()
        if dry_run_output is not None:
            output = _absolute(dry_run_output, "dry-run output")
            if _inside(output, scope) or output == manifest:
                raise ExpansionCleanupBlocked("dry-run output must be outside review scope and manifest")
            _write_json(output, result)
            result["output"] = str(output)
        return result

    assert receipt is not None
    receipt.parent.mkdir(parents=True, exist_ok=True)
    with _lock(receipt):
        next_index, pending, complete = _receipt_state(receipt, manifest_hash, rows, scope)
        result, archives, stack = inspect(next_index, pending)
        try:
            if not result["applyReady"]:
                raise ExpansionCleanupBlocked("active process, incomplete process inspection, or tracked candidate blocks cleanup")
            baseline_git = result["git"]
            if complete:
                result.update({"dryRun": False, "state": "COMPLETE", "receipt": str(receipt),
                               "deletedCount": len(rows)})
                return result
            source_cache: dict[str, dict[str, Any]] = {}
            current_stage = None
            for index in range(next_index, len(rows)):
                row = rows[index]
                candidate = Path(row["path"])
                if row["stage"] != current_stage:
                    processes, process_error, _ = _checked_processes(process_checker)
                    if processes or process_error or git_checker(scope, rows) != baseline_git:
                        raise ExpansionCleanupBlocked("process or Git state changed before stage deletion")
                    current_stage = row["stage"]
                if pending and index == next_index and not candidate.exists() and not candidate.is_symlink():
                    # The previous process unlinked after its durable intent
                    # but stopped before recording the completed deletion.
                    _append(receipt, _event("deleted", index, row))
                    pending = False
                    continue
                _verify_candidate(row)
                source_cache.clear()  # each counterpart is rehashed immediately before unlink
                _verify_retained(row, archives, source_cache)
                if not pending:
                    _append(receipt, _event("intent", index, row))
                _verify_candidate(row)  # reject replacement between intent and unlink
                candidate.unlink()  # exact manifest path only; never remove directories
                _append(receipt, _event("deleted", index, row))
                pending = False
            _append(receipt, {"type": "complete", "utc": _utc()})
            result.update({"dryRun": False, "state": "COMPLETE", "receipt": str(receipt),
                           "deletedCount": len(rows) - next_index})
            return result
        finally:
            stack.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--dry-run-output", type=Path)
    parser.add_argument("--sample-candidates", type=int)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        result = execute_expansion_cleanup(
            args.manifest, manifest_sha256=args.manifest_sha256,
            apply=args.apply, receipt_path=args.receipt,
            dry_run_output=args.dry_run_output,
            sample_candidates=args.sample_candidates)
    except (ExpansionCleanupBlocked, OSError, zipfile.BadZipFile, KeyError, TypeError,
            ValueError) as exc:
        parser.exit(2, f"{exc}\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
