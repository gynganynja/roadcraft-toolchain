"""Pinned scratch-only Blender authoring comparison against repaired USF.

The output is diagnostic evidence and cannot approve the native-blend route.
Unlike the no-edit USF serialization probe, this actually exports the pinned
historical .blend through the bundled SDK and compares the result to the
authoritative repaired USF. The candidate stays under ignored local scratch
for investigation and is never adopted as build input.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
from typing import Any

from .blender_parity_evidence import package_evidence
from .source import (ExportBlockedError, compare_source_baselines, file_sha256,
                     require_export_allowed)


TOOLCHAIN_ROOT = Path(__file__).resolve().parents[2]
HELPER = Path(__file__).with_name("blender_authoring_helper.py")
DIFF = Path(__file__).with_name("blender_parity_diff.py")
SUMMARY = Path(__file__).with_name("blender_usf_helper.py")
_SHA = re.compile(r"^[0-9a-f]{64}$")


class BlenderAuthoringError(RuntimeError):
    """The pinned diagnostic cannot safely run."""


def _inside(path: Path, root: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise BlenderAuthoringError(f"{label} must be inside {root}")
    return resolved


def _declared_file(root: Path, row: dict[str, Any]) -> Path:
    path = root
    for part in row["path"].split("/"):
        path = path / part
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
        if (path.is_symlink() or
                attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)):
            raise BlenderAuthoringError("authoring file path crosses a link")
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise BlenderAuthoringError("authoring file is outside source root")
    if resolved.stat().st_size != row["bytes"] or file_sha256(resolved) != row["sha256"]:
        raise BlenderAuthoringError(f"authoring file differs from pin: {row['path']}")
    return resolved


def _pinned_asset(inventory_path: Path, inventory_sha256: str, asset: str):
    if not _SHA.fullmatch(inventory_sha256.lower()):
        raise BlenderAuthoringError("invalid inventory SHA-256")
    if file_sha256(inventory_path) != inventory_sha256.lower():
        raise BlenderAuthoringError("authoring inventory differs from pin")
    try:
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        compare_source_baselines(inventory, inventory)
        matching = [row for row in inventory["assets"] if row["asset"] == asset]
        if len(matching) != 1:
            raise BlenderAuthoringError(f"authoring inventory has no unique asset {asset!r}")
        rows = matching[0]["files"]
        blends = [row for row in rows if row["role"] == "blend-reference"]
        usfs = [row for row in rows if row["role"] == "build-usf"]
        if len(blends) != 1 or len(usfs) != 1:
            raise BlenderAuthoringError("asset needs one pinned Blend and one build USF")
        root = Path(inventory["sourceRoot"]).resolve(strict=True)
        blend = _declared_file(root, blends[0])
        baseline = _declared_file(root, usfs[0])
        if blend.suffix.lower() != ".blend" or baseline.suffix.lower() != ".usf":
            raise BlenderAuthoringError("authoring inventory has invalid file roles")
        return inventory, root, matching[0], blend, baseline
    except (OSError, ValueError, TypeError, KeyError) as exc:
        if isinstance(exc, BlenderAuthoringError):
            raise
        raise BlenderAuthoringError("authoring inventory is malformed") from exc


def _sdk_files(sdk: Path) -> dict[str, str]:
    lib = sdk / "saber/blender/lib"
    converter = sdk / "saber/blender/blender_to_usf"
    paths = [*sorted(lib.glob("*.py")), *sorted((lib / "usf").glob("*.py")),
             converter / "name_convention_config.json",
             converter / "import_file.py"]
    if not (lib / "usf/export.py").is_file() or not all(path.is_file() for path in paths):
        raise BlenderAuthoringError("bundled SDK exporter is incomplete")
    return {path.relative_to(sdk).as_posix(): file_sha256(path) for path in paths}


def run_authoring_probe(
    *,
    asset_name: str,
    inventory_path: str | Path,
    inventory_sha256: str,
    blender_executable: str | Path,
    blender_sha256: str,
    sdk_script_root: str | Path,
    scratch_root: str | Path,
    receipt_path: str | Path,
    archive_path: str | Path | None = None,
    timeout_seconds: int = 900,
    blender_threads: int | None = 1,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Compare one pinned .blend to its repaired USF without adopting output."""
    inventory_file = Path(inventory_path).resolve(strict=True)
    inventory, source_root, asset, blend, baseline = _pinned_asset(
        inventory_file, inventory_sha256, asset_name)
    blender = Path(blender_executable).resolve(strict=True)
    if not blender.is_file() or blender.suffix.lower() != ".exe":
        raise BlenderAuthoringError("Blender executable is missing")
    if not _SHA.fullmatch(blender_sha256.lower()):
        raise BlenderAuthoringError("invalid Blender executable SHA-256")
    actual_blender_sha = file_sha256(blender)
    if actual_blender_sha != blender_sha256.lower():
        raise BlenderAuthoringError("Blender executable differs from pin")
    sdk = Path(sdk_script_root).resolve(strict=True)
    sdk_hashes = _sdk_files(sdk)
    scratch = _inside(Path(scratch_root), TOOLCHAIN_ROOT / "local", "scratch root")
    receipt = _inside(Path(receipt_path), TOOLCHAIN_ROOT, "receipt")
    archive = _inside(Path(archive_path) if archive_path is not None else
                      receipt.with_suffix(receipt.suffix + ".gz"),
                      TOOLCHAIN_ROOT, "archive")
    if receipt.exists() or archive.exists():
        raise BlenderAuthoringError("receipt or archive already exists")
    if not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
        raise BlenderAuthoringError("timeout must be a positive number of seconds")
    if blender_threads is not None and (
            isinstance(blender_threads, bool) or not isinstance(blender_threads, int) or
            not 1 <= blender_threads <= 1024):
        raise BlenderAuthoringError("Blender threads must be between 1 and 1024")
    version = subprocess.run([str(blender), "--version"], capture_output=True,
                             text=True, timeout=30, check=True).stdout.splitlines()[0]
    base = {
        "schemaVersion": 1, "asset": asset_name,
        "inventoryPath": str(inventory_file),
        "inventorySha256": inventory_sha256.lower(),
        "sourceAssetDigest": asset["assetDigest"],
        "blendPath": str(blend), "blendSha256": file_sha256(blend),
        "baselineUsfPath": str(baseline), "baselineUsfSha256": file_sha256(baseline),
        "blenderPath": str(blender), "blenderSha256": actual_blender_sha,
        "blenderVersion": version,
        "blenderThreads": blender_threads,
        "sdkScriptRoot": str(sdk), "sdkFileHashes": sdk_hashes,
        "helperSha256": file_sha256(HELPER),
        "diffSha256": file_sha256(DIFF),
        "summarySha256": file_sha256(SUMMARY),
        "scratchRoot": str(scratch), "receiptPath": str(receipt),
        "archivePath": str(archive),
        "nativeBlendExportApproved": False,
    }
    if dry_run:
        return {**base, "status": "DRY_RUN", "dryRun": True}

    if scratch.exists() and any(scratch.iterdir()):
        raise BlenderAuthoringError("scratch root must be empty for a new probe")
    if shutil.disk_usage(TOOLCHAIN_ROOT).free < 1024**3:
        raise BlenderAuthoringError("at least 1 GiB free is required for scratch export")
    scratch.mkdir(parents=True, exist_ok=True)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    candidate = scratch / "candidate.usf"
    helper_result = scratch / "helper_result.json"
    log = scratch / "blender.log"
    command = [
        str(blender), "--background", "--factory-startup", "--disable-autoexec",
        *(["--threads", str(blender_threads)] if blender_threads is not None else []),
        "--python-exit-code", "1", "--python", str(HELPER), "--",
        "--blend", str(blend), "--blend-sha256", base["blendSha256"],
        "--baseline-usf", str(baseline), "--baseline-sha256", base["baselineUsfSha256"],
        "--candidate-usf", str(candidate), "--result", str(helper_result),
        "--scratch-root", str(scratch), "--sdk-script-root", str(sdk),
    ]
    environment = dict(os.environ)
    environment.update({
        "BLENDER_USER_CONFIG": str(scratch / "blender-config"),
        "BLENDER_USER_SCRIPTS": str(scratch / "blender-scripts"),
        "BLENDER_USER_DATAFILES": str(scratch / "blender-datafiles"),
        "TEMP": str(scratch), "TMP": str(scratch), "TMPDIR": str(scratch),
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    result: dict[str, Any] = {**base, "dryRun": False,
                              "candidateUsfPath": str(candidate)}
    try:
        with log.open("wb") as stream:
            completed = subprocess.run(command, cwd=scratch, env=environment,
                                       stdout=stream, stderr=subprocess.STDOUT,
                                       timeout=timeout_seconds, check=False,
                                       creationflags=getattr(subprocess,
                                                             "CREATE_NO_WINDOW", 0))
        result["blenderExitCode"] = completed.returncode
    except subprocess.TimeoutExpired:
        result["blenderExitCode"] = None
        result["status"] = "TIMEOUT"
    if log.is_file():
        with log.open("rb") as stream:
            stream.seek(max(0, log.stat().st_size - 12_000))
            result["blenderLogTail"] = stream.read().decode("utf-8", errors="replace")
    if helper_result.is_file():
        try:
            result["diagnostic"] = json.loads(helper_result.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            result["status"] = "INVALID_HELPER_RESULT"
    if candidate.is_file() and not candidate.is_symlink():
        result["candidateUsfSha256Observed"] = file_sha256(candidate)
        result["candidateUsfBytesObserved"] = candidate.stat().st_size
    result["blendSha256After"] = file_sha256(blend)
    result["baselineUsfSha256After"] = file_sha256(baseline)
    result["sourceUnchanged"] = (
        result["blendSha256After"] == base["blendSha256"] and
        result["baselineUsfSha256After"] == base["baselineUsfSha256"])
    result["sdkUnchanged"] = _sdk_files(sdk) == sdk_hashes
    diagnostic = result.get("diagnostic", {})
    if result.get("status") not in ("TIMEOUT", "INVALID_HELPER_RESULT"):
        if result.get("blenderExitCode") != 0 or not diagnostic:
            result["status"] = "EXPORT_FAILED"
        elif not result["sourceUnchanged"] or not result["sdkUnchanged"]:
            result["status"] = "INPUT_CHANGED"
        elif (diagnostic.get("blendSha256") != base["blendSha256"] or
              diagnostic.get("baselineUsfSha256") != base["baselineUsfSha256"] or
              diagnostic.get("candidateUsfSha256") != result.get("candidateUsfSha256Observed") or
              diagnostic.get("candidateUsfBytes") != result.get("candidateUsfBytesObserved") or
              diagnostic.get("nativeBlendExportApproved") is not False):
            result["status"] = "HELPER_MISMATCH"
        elif (diagnostic.get("rootNameMatches") is False or
              diagnostic["nodeDiff"]["matchesIndexedFields"] is False or
              diagnostic["baselineSemantic"] != diagnostic["candidateSemantic"]):
            result["status"] = "PARITY_DIFFERENT"
        else:
            result["status"] = "DIAGNOSTIC_EQUAL_REVIEW_REQUIRED"

    try:
        require_export_allowed(source_root, inventory, asset_name, "native-blend",
                               parity_receipt=result)
    except ExportBlockedError as exc:
        result["exportGate"] = {"status": "BLOCKED", "reason": str(exc)}
    else:
        result["exportGate"] = {"status": "UNEXPECTEDLY_ALLOWED"}
        result["status"] = "GATE_OPEN_UNEXPECTEDLY"

    package_evidence(result, summary_path=receipt, archive_path=archive,
                     local_raw_path=scratch / "full_receipt.json")
    return result


def _parse_blender_threads(value: str) -> int | None:
    if value.lower() == "auto":
        return None
    try:
        threads = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Blender threads must be 1..1024 or auto") from exc
    if not 1 <= threads <= 1024:
        raise argparse.ArgumentTypeError("Blender threads must be 1..1024 or auto")
    return threads


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--inventory-sha256", required=True)
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--blender-sha256", required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--scratch-root", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--blender-threads", type=_parse_blender_threads,
                        default=1, metavar="N|auto",
                        help="Blender worker threads (default: 1; auto uses Blender's default)")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    result = run_authoring_probe(
        asset_name=args.asset, inventory_path=args.inventory,
        inventory_sha256=args.inventory_sha256,
        blender_executable=args.blender, blender_sha256=args.blender_sha256,
        sdk_script_root=args.sdk_script_root, scratch_root=args.scratch_root,
        receipt_path=args.receipt, archive_path=args.archive,
        timeout_seconds=args.timeout_seconds, blender_threads=args.blender_threads,
        dry_run=not args.run,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.run and result["status"] not in ("PARITY_DIFFERENT",
                                               "DIAGNOSTIC_EQUAL_REVIEW_REQUIRED"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
