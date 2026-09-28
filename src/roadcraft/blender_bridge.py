"""Run a pinned USF read/write diagnostic through installed Blender.

This is a source-recovery probe, not an export route.  It never opens an
interactive .blend, alters a repaired USF, or authorizes native Blender export.
The full serialized output lives in disposable ``RoadCraftToolchain/local``
scratch; a small durable receipt records what Blender actually verified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
from typing import Any

from .source import compare_source_baselines, file_sha256


TOOLCHAIN_ROOT = Path(__file__).resolve().parents[2]
HELPER = Path(__file__).with_name("blender_usf_helper.py")
_SHA = re.compile(r"^[0-9a-f]{64}$")


class BlenderBridgeError(RuntimeError):
    """The Blender diagnostic cannot safely run or produce a valid receipt."""


def _under(path: Path, root: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise BlenderBridgeError(f"{label} must be inside {root}")
    return resolved


def _sdk_files(script_root: Path) -> dict[str, str]:
    library = script_root / "saber/blender/lib"
    files = [library / "binary_io.py", *sorted((library / "usf").glob("*.py"))]
    if not (library / "usf/scene.py").is_file() or not all(path.is_file() for path in files):
        raise BlenderBridgeError(f"SDK USF parser is incomplete: {script_root}")
    return {path.relative_to(script_root).as_posix(): file_sha256(path)
            for path in files}


def _pinned_usf(inventory_path: Path, inventory_sha256: str,
                asset_name: str) -> tuple[Path, str, str]:
    if not _SHA.fullmatch(inventory_sha256.lower()):
        raise BlenderBridgeError("invalid authoring inventory SHA-256")
    if file_sha256(inventory_path) != inventory_sha256.lower():
        raise BlenderBridgeError("authoring inventory file differs from its pin")
    try:
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        compare_source_baselines(inventory, inventory)  # validates nested digests
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise BlenderBridgeError("authoring inventory is malformed") from exc
    matching = [asset for asset in inventory["assets"] if asset["asset"] == asset_name]
    if len(matching) != 1:
        raise BlenderBridgeError(f"authoring inventory has no unique asset {asset_name!r}")
    asset = matching[0]
    rows = [row for row in asset["files"] if row["role"] == "build-usf"]
    if len(rows) != 1 or not rows[0]["path"].endswith("/export.usf"):
        raise BlenderBridgeError("asset must have one pinned build USF")
    source_root = Path(inventory["sourceRoot"]).resolve(strict=True)
    declared_path = source_root
    for part in Path(rows[0]["path"]).parts:
        declared_path = declared_path / part
        attributes = getattr(declared_path.lstat(), "st_file_attributes", 0)
        if (declared_path.is_symlink() or
                attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)):
            raise BlenderBridgeError("build USF path crosses a link or reparse point")
    source = declared_path.resolve(strict=True)
    if not source.is_relative_to(source_root) or not source.is_file() or source.is_symlink():
        raise BlenderBridgeError("build USF is outside source root or is linked")
    if source.stat().st_size != rows[0]["bytes"] or file_sha256(source) != rows[0]["sha256"]:
        raise BlenderBridgeError("repaired USF differs from its source inventory")
    return source, rows[0]["sha256"], asset["assetDigest"]


def run_usf_roundtrip(
    *,
    asset_name: str,
    inventory_path: str | Path,
    inventory_sha256: str,
    blender_executable: str | Path,
    sdk_script_root: str | Path,
    scratch_root: str | Path,
    receipt_path: str | Path,
    timeout_seconds: int = 900,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Probe one repaired USF; return a plan or a durable evidence receipt."""
    inventory_file = Path(inventory_path).resolve(strict=True)
    source, source_sha, asset_digest = _pinned_usf(inventory_file,
                                                  inventory_sha256, asset_name)
    blender = Path(blender_executable).resolve(strict=True)
    if not blender.is_file() or blender.suffix.lower() != ".exe":
        raise BlenderBridgeError("Blender executable is missing")
    sdk = Path(sdk_script_root).resolve(strict=True)
    sdk_hashes = _sdk_files(sdk)
    helper_sha = file_sha256(HELPER)
    scratch = _under(Path(scratch_root), TOOLCHAIN_ROOT / "local", "scratch root")
    receipt = _under(Path(receipt_path), TOOLCHAIN_ROOT, "receipt")
    if receipt.exists():
        raise BlenderBridgeError(f"receipt already exists: {receipt}")
    if not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
        raise BlenderBridgeError("timeout must be a positive number of seconds")
    version = subprocess.run([str(blender), "--version"], capture_output=True,
                             text=True, timeout=30, check=True).stdout.splitlines()[0]
    base = {
        "schemaVersion": 1, "asset": asset_name,
        "inventoryPath": str(inventory_file),
        "inventorySha256": inventory_sha256.lower(),
        "sourceAssetDigest": asset_digest,
        "sourcePath": str(source), "sourceSha256": source_sha,
        "blenderPath": str(blender), "blenderVersion": version,
        "sdkScriptRoot": str(sdk), "sdkParserHashes": sdk_hashes,
        "helperSha256": helper_sha,
        "scratchRoot": str(scratch), "receiptPath": str(receipt),
        "nativeBlendExportApproved": False,
    }
    if dry_run:
        return {**base, "status": "DRY_RUN", "dryRun": True}

    scratch.mkdir(parents=True, exist_ok=True)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    if receipt.exists():
        raise BlenderBridgeError(f"receipt appeared during preflight: {receipt}")
    result: dict[str, Any] = {**base, "dryRun": False}
    with tempfile.TemporaryDirectory(prefix="usf-roundtrip-", dir=scratch) as temp:
        job = Path(temp)
        output = job / "roundtrip.usf"
        helper_receipt = job / "blender_result.json"
        log = job / "blender.log"
        command = [
            str(blender), "--background", "--factory-startup", "--disable-autoexec",
            "--python-exit-code", "1", "--python", str(HELPER), "--",
            "--source", str(source), "--source-sha256", source_sha,
            "--output", str(output), "--receipt", str(helper_receipt),
            "--scratch-root", str(job), "--sdk-script-root", str(sdk),
        ]
        environment = dict(os.environ)
        environment.update({
            "BLENDER_USER_CONFIG": str(job / "blender-config"),
            "BLENDER_USER_SCRIPTS": str(job / "blender-scripts"),
            "BLENDER_USER_DATAFILES": str(job / "blender-datafiles"),
            "TEMP": str(job), "TMP": str(job), "TMPDIR": str(job),
        })
        try:
            with log.open("wb") as stream:
                completed = subprocess.run(command, cwd=job, env=environment,
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
        if helper_receipt.is_file():
            try:
                helper_result = json.loads(helper_receipt.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise BlenderBridgeError("Blender helper wrote invalid JSON") from exc
            result["roundtrip"] = helper_result
        if output.is_file() and not output.is_symlink():
            result["outputSha256Observed"] = file_sha256(output)
            result["outputBytesObserved"] = output.stat().st_size
        result["sourceSha256After"] = file_sha256(source)
        result["sourceUnchanged"] = result["sourceSha256After"] == source_sha
        result["sdkUnchanged"] = _sdk_files(sdk) == sdk_hashes
        if result.get("status") != "TIMEOUT":
            if result.get("blenderExitCode") != 0 or "roundtrip" not in result:
                result["status"] = "PARSER_FAILED"
            elif not result["sourceUnchanged"] or not result["sdkUnchanged"]:
                result["status"] = "INPUT_CHANGED"
            elif (result["roundtrip"].get("sourceSha256") != source_sha or
                  result["roundtrip"].get("outputSha256") != result.get("outputSha256Observed") or
                  result["roundtrip"].get("outputBytes") != result.get("outputBytesObserved") or
                  result["roundtrip"].get("byteIdentical") is not
                  (result.get("outputSha256Observed") == source_sha and
                   result.get("outputBytesObserved") == source.stat().st_size)):
                result["status"] = "HELPER_MISMATCH"
            elif (result["roundtrip"].get("byteIdentical") is True and
                  result["roundtrip"].get("semanticSummaryEqual") is True and
                  result["outputSha256Observed"] == source_sha and
                  result["outputBytesObserved"] == source.stat().st_size):
                result["status"] = "BYTE_IDENTICAL"
            elif result["roundtrip"].get("semanticSummaryEqual") is True:
                result["status"] = "BYTE_DIFFERENT_SUMMARY_EQUAL"
            else:
                result["status"] = "SEMANTIC_SUMMARY_DIFFERENT"
        result["scratchOutputDisposed"] = True

    with receipt.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--inventory-sha256", required=True)
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--scratch-root", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--run", action="store_true", help="Execute after pinned dry run")
    args = parser.parse_args()
    result = run_usf_roundtrip(
        asset_name=args.asset, inventory_path=args.inventory,
        inventory_sha256=args.inventory_sha256,
        blender_executable=args.blender, sdk_script_root=args.sdk_script_root,
        scratch_root=args.scratch_root, receipt_path=args.receipt,
        timeout_seconds=args.timeout_seconds, dry_run=not args.run,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.run and result["status"] != "BYTE_IDENTICAL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
