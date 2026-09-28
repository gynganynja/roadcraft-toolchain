"""Separate, bounded MCP adapter for the Blender USF scratch diagnostic.

This server deliberately does not expose a Blender project API. The only
native operation delegates to :mod:`blender_bridge`, which reads a pinned USF
and disposes of its serialized scratch copy without opening or saving .blend.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from threading import Lock
from typing import Any

from . import blender_bridge, core
from .mcp_server import MCPDependencyError, _sdk_components
from .source import file_sha256


TOOLCHAIN_ROOT = Path(__file__).resolve().parents[2]
SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
ASSET_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
TOOL_NAMES = ("blender_status", "usf_roundtrip")
INSTRUCTIONS = (
    "This is a separate Blender scratch diagnostic, not a Blender editing or export API. "
    "blender_status only probes the operator-pinned executable's version. "
    "usf_roundtrip reads one authoring-inventory-pinned export.usf and disposes of "
    "the serialized scratch copy. It never opens or writes a .blend, replaces source, "
    "or approves native export. Execution requires run=true; a durable receipt is "
    "written only to an explicit new JSON path under RoadCraftToolchain/local/jobs."
)


class BlenderMCPError(ValueError):
    """A Blender MCP request crosses the adapter's bounded safety contract."""


def _absolute(value: str | Path, label: str) -> Path:
    if not str(value) or "://" in str(value):
        raise BlenderMCPError(f"{label} must be an absolute local path")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise BlenderMCPError(f"{label} must be an absolute local path")
    return path.resolve()


def _within(path: Path, root: Path, label: str) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise BlenderMCPError(f"{label} must be under {root}")
    return resolved


@dataclass(frozen=True)
class BlenderSettings:
    blender_executable: Path
    blender_sha256: str
    sdk_script_root: Path
    scratch_root: Path = TOOLCHAIN_ROOT / "local" / "blender-mcp-scratch"

    def __post_init__(self) -> None:
        if not SHA256.fullmatch(self.blender_sha256):
            raise BlenderMCPError("Blender executable needs an explicit SHA-256 pin")
        blender = _absolute(self.blender_executable, "Blender executable")
        if blender.name.casefold() != "blender.exe":
            raise BlenderMCPError("Blender executable must be named blender.exe")
        sdk = _absolute(self.sdk_script_root, "SDK script root")
        scratch = _within(_absolute(self.scratch_root, "scratch root"),
                          TOOLCHAIN_ROOT / "local", "scratch root")
        object.__setattr__(self, "blender_executable", blender)
        object.__setattr__(self, "blender_sha256", self.blender_sha256.lower())
        object.__setattr__(self, "sdk_script_root", sdk)
        object.__setattr__(self, "scratch_root", scratch)


class BlenderTools:
    """Transport-independent, fixed-path Blender diagnostics."""

    def __init__(self, settings: BlenderSettings):
        self.settings = settings
        self._roundtrip_lock = Lock()

    def _blender_identity(self) -> dict[str, Any]:
        return core.file_identity(self.settings.blender_executable,
                                  self.settings.blender_sha256)

    def _require_blender(self) -> dict[str, Any]:
        identity = self._blender_identity()
        if not identity.get("matchesExpected") or not identity.get("unchangedDuringRead"):
            raise BlenderMCPError("Blender executable is missing, changed, or unstable")
        return identity

    def blender_status(self) -> dict[str, Any]:
        """Check the fixed Blender executable pin, SDK parser, helper, and `--version`; do not open a project."""
        identity = self._blender_identity()
        result: dict[str, Any] = {
            "ready": False,
            "blender": identity,
            "sdkScriptRoot": str(self.settings.sdk_script_root),
            "scratchRoot": str(self.settings.scratch_root),
            "nativeBlendExportApproved": False,
        }
        if not identity.get("matchesExpected") or not identity.get("unchangedDuringRead"):
            result["reason"] = "Blender executable is missing, changed, or unstable"
            return result
        try:
            sdk_hashes = blender_bridge._sdk_files(self.settings.sdk_script_root)
        except (blender_bridge.BlenderBridgeError, OSError) as exc:
            result["reason"] = str(exc)
            return result
        result["sdkParserHashes"] = sdk_hashes
        result["helperSha256"] = file_sha256(blender_bridge.HELPER)
        try:
            completed = subprocess.run(
                [str(self.settings.blender_executable), "--version"],
                capture_output=True, text=True, timeout=30, check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            result["reason"] = f"Blender version probe failed: {exc}"
            return result
        lines = completed.stdout.splitlines()
        if completed.returncode != 0 or not lines or not lines[0].startswith("Blender "):
            result["reason"] = "Blender version probe returned no valid version"
            result["versionExitCode"] = completed.returncode
            return result
        result["version"] = lines[0]
        result["versionExitCode"] = completed.returncode
        after = self._blender_identity()
        if not after.get("matchesExpected") or not after.get("unchangedDuringRead"):
            result["reason"] = "Blender executable changed during version probe"
            return result
        result["ready"] = True
        return result

    def usf_roundtrip(self, asset_name: str, inventory_path: str,
                      inventory_sha256: str, *, run: bool = False,
                      receipt_path: str | None = None,
                      timeout_seconds: int = 900) -> dict[str, Any]:
        """Dry-run or scratch-roundtrip one pinned export.usf; optional durable receipt must be new under local/jobs."""
        if not isinstance(asset_name, str) or not ASSET_NAME.fullmatch(asset_name):
            raise BlenderMCPError("asset_name must be a simple asset identifier")
        inventory = _absolute(inventory_path, "authoring inventory")
        if inventory.suffix.lower() != ".json":
            raise BlenderMCPError("authoring inventory must be JSON")
        if not isinstance(inventory_sha256, str) or not SHA256.fullmatch(inventory_sha256):
            raise BlenderMCPError("authoring inventory needs an explicit SHA-256 pin")
        if not isinstance(run, bool):
            raise BlenderMCPError("run must be a boolean")
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or not 1 <= timeout_seconds <= 900:
            raise BlenderMCPError("timeout_seconds must be between 1 and 900")
        jobs_root = TOOLCHAIN_ROOT / "local" / "jobs"
        requested_receipt = None
        if receipt_path is not None:
            requested_receipt = _within(_absolute(receipt_path, "receipt path"), jobs_root,
                                        "receipt path")
            if requested_receipt == jobs_root.resolve() or requested_receipt.suffix.lower() != ".json":
                raise BlenderMCPError("receipt path must name a JSON file under local/jobs")
            if requested_receipt.exists():
                raise BlenderMCPError("receipt already exists; choose a new path")
        self._require_blender()
        if not self._roundtrip_lock.acquire(blocking=False):
            raise BlenderMCPError("Another Blender scratch roundtrip is already running")
        try:
            if run and requested_receipt is None:
                # An ephemeral bridge receipt is needed to verify Blender's
                # output, then TemporaryDirectory disposes of it.
                self.settings.scratch_root.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryDirectory(prefix="mcp-usf-", dir=self.settings.scratch_root) as temporary:
                    result = blender_bridge.run_usf_roundtrip(
                        asset_name=asset_name, inventory_path=inventory,
                        inventory_sha256=inventory_sha256,
                        blender_executable=self.settings.blender_executable,
                        sdk_script_root=self.settings.sdk_script_root,
                        scratch_root=Path(temporary) / "scratch",
                        receipt_path=Path(temporary) / "receipt.json",
                        timeout_seconds=timeout_seconds, dry_run=False,
                    )
                result["scratchRoot"] = str(self.settings.scratch_root)
                result["receiptPath"] = None
                result["durableReceiptWritten"] = False
            else:
                result = blender_bridge.run_usf_roundtrip(
                    asset_name=asset_name, inventory_path=inventory,
                    inventory_sha256=inventory_sha256,
                    blender_executable=self.settings.blender_executable,
                    sdk_script_root=self.settings.sdk_script_root,
                    scratch_root=self.settings.scratch_root,
                    receipt_path=requested_receipt or self.settings.scratch_root / "dry-run-receipt.json",
                    timeout_seconds=timeout_seconds, dry_run=not run,
                )
                result["durableReceiptWritten"] = bool(run and requested_receipt)
                if requested_receipt is None:
                    result["receiptPath"] = None
            result["blenderExecutableSha256"] = self.settings.blender_sha256
            after = self._blender_identity()
            if not after.get("matchesExpected") or not after.get("unchangedDuringRead"):
                result["status"] = "BLENDER_BINARY_CHANGED"
                result["nativeBlendExportApproved"] = False
            return result
        finally:
            self._roundtrip_lock.release()


def create_server(settings: BlenderSettings) -> Any:
    """Register only status and bounded scratch-roundtrip with the official SDK."""
    fast_mcp, annotations = _sdk_components()
    server = fast_mcp("RoadCraft Blender Scratch", instructions=INSTRUCTIONS,
                      log_level="WARNING")
    tools = BlenderTools(settings)
    server.add_tool(tools.blender_status, name="blender_status",
                    annotations=annotations(readOnlyHint=True, destructiveHint=False,
                                            idempotentHint=True, openWorldHint=False))
    server.add_tool(tools.usf_roundtrip, name="usf_roundtrip",
                    annotations=annotations(readOnlyHint=False, destructiveHint=False,
                                            idempotentHint=False, openWorldHint=False))
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender-executable", type=Path, required=True)
    parser.add_argument("--blender-sha256", required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--scratch-root", type=Path,
                        default=TOOLCHAIN_ROOT / "local" / "blender-mcp-scratch")
    args = parser.parse_args(argv)
    try:
        settings = BlenderSettings(args.blender_executable, args.blender_sha256,
                                   args.sdk_script_root, args.scratch_root)
        server = create_server(settings)
    except (BlenderMCPError, MCPDependencyError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    server.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
