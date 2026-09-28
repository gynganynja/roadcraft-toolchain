"""Read-only RoadCraft MCP adapter using the official Python SDK's v1 line.

Install the optional ``requirements-mcp.txt`` in a dedicated environment, then
run ``python -m roadcraft.mcp_server --registry /path/project.json --config
/path/machine.json`` with the package installed or its src on PYTHONPATH.
Transport is stdio only. No SDK import, subprocess, or file access occurs on
module import. Logs/errors use stderr; stdout is reserved for MCP messages.

Every registered tool reads existing evidence. Evidence reports are rendered
in memory and optionally returned as HTML; saving them remains a separate CLI
operation. There are no build, export, install, delete, recovery, or app-launch
tools. This is an adapter to local file APIs, not a filesystem sandbox.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, NotRequired, TypedDict

from . import cleanup, core, review, source
from .cli import _verify_project


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
MAX_RETURNED_HTML_BYTES = 2 * 1024 * 1024
INSTRUCTIONS = (
    "Read-only RoadCraft project evidence. Start with project_status and project_doctor. "
    "Accepted, candidate, and installed identities are separate. Hash or numeric checks "
    "do not establish visual or campaign acceptance. Evidence report HTML is returned "
    "in memory; this server never saves files, launches authoring apps, builds, installs, "
    "recovers, or deletes anything. Storage results are review candidates, not deletion instructions."
)


class ReceiptPin(TypedDict):
    path: str
    sha256: NotRequired[str]


class SourceFile(TypedDict):
    path: str
    role: str


class SourceAsset(TypedDict):
    asset: str
    exportMethod: str
    files: list[SourceFile]


class MCPDependencyError(RuntimeError):
    """The optional supported MCP SDK is missing or incompatible."""


def _sdk_components() -> tuple[Any, Any]:
    message = (
        "RoadCraft MCP requires the optional official Python SDK: mcp>=1.28,<2. "
        "Install RoadCraftToolchain/requirements-mcp.txt into the server's Python "
        "environment. The standard-library RoadCraft CLI still works without MCP."
    )
    try:
        version = importlib.metadata.version("mcp")
        match = re.match(r"^(\d+)\.(\d+)", version)
        if not match or not ((1, 28) <= tuple(map(int, match.groups())) < (2, 0)):
            raise MCPDependencyError(f"{message} Found incompatible version {version}.")
        sdk = importlib.import_module("mcp.server.fastmcp")
        types = importlib.import_module("mcp.types")
        return sdk.FastMCP, types.ToolAnnotations
    except (ImportError, importlib.metadata.PackageNotFoundError, AttributeError) as exc:
        raise MCPDependencyError(message) from exc


def _absolute(path: str | Path) -> Path:
    raw = str(path)
    # Reject UNC shares and Win32 device namespaces before resolve() can touch
    # a remote server or named pipe. MCP callers may only supply local paths.
    if (not raw or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", raw) or
            core._is_remote_namespace(raw)):
        raise core.RoadcraftError("Use a local absolute filesystem path")
    result = Path(path).expanduser()
    if not result.is_absolute():
        raise core.RoadcraftError("Use an absolute path; relative paths are only allowed inside evidence documents")
    try:
        core._require_local_path(result)
    except core.RoadcraftError as exc:
        raise core.RoadcraftError(f"Use a local absolute filesystem path: {exc}") from exc
    result = result.resolve()
    if core._is_remote_namespace(result):
        raise core.RoadcraftError("Use a local absolute filesystem path")
    return result


@dataclass(frozen=True)
class ServerSettings:
    registry: Path
    config: Path

    @classmethod
    def defaults(cls) -> "ServerSettings":
        return cls(
            Path(os.environ.get("ROADCRAFT_REGISTRY", PACKAGE_ROOT / "project.json")).expanduser().resolve(),
            Path(os.environ.get("ROADCRAFT_CONFIG", PACKAGE_ROOT / "local/machine.json")).expanduser().resolve(),
        )


class RoadcraftTools:
    """Typed, transport-independent callables; no methods write to disk."""

    def __init__(self, settings: ServerSettings):
        self.settings = settings

    def _config(self) -> dict[str, Any]:
        return core.read_config(self.settings.config) if self.settings.config.is_file() else {}

    def project_status(self) -> dict[str, Any]:
        """Hash accepted, candidate, installed and receipt identities from configured registry/config; report active transaction locks without altering them."""
        result = core.status(core.read_registry(self.settings.registry), self._config())
        result.update(registryPath=str(self.settings.registry), configPath=str(self.settings.config),
                      configFound=self.settings.config.is_file())
        return result

    def project_doctor(self) -> dict[str, Any]:
        """Read Python/tool availability, disk space and active authoring process names. Never start or stop applications."""
        result = core.doctor(self._config())
        result.update(configPath=str(self.settings.config), configFound=self.settings.config.is_file())
        return result

    def verify_project(self) -> dict[str, Any]:
        """Verify every configured accepted/candidate pin and the pinned source-manifest contents; missing pins fail verification and never imply acceptance."""
        return _verify_project(self.settings.registry, self.settings.config)

    def inspect_file(self, path: str, member: str | None = None,
                     occurrence: int | None = None, hash_members: bool = False,
                     offset: int = 0, limit: int = 200) -> dict[str, Any]:
        """Inspect an absolute file path, or ZIP/PAK member occurrences. Occurrence is one-based. Hashing all members can be expensive; offset/limit paginate returned rows only."""
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise core.RoadcraftError("offset must be a nonnegative integer")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise core.RoadcraftError("limit must be an integer between 1 and 1000")
        result = core.inspect_path(_absolute(path), member=member, occurrence=occurrence,
                                   hash_members=hash_members)
        if "members" in result:
            rows = result["members"]
            result["members"] = rows[offset:offset + limit]
            result["pagination"] = {"offset": offset, "limit": limit, "total": len(rows),
                                    "nextOffset": offset + limit if offset + limit < len(rows) else None}
        return result

    def verify_file(self, path: str, sha256: str) -> dict[str, Any]:
        """Verify a local file against an explicit expected SHA-256, including stability during hashing. Reads only; does not update the expected pin."""
        result = core.file_identity(_absolute(path), sha256)
        result["passed"] = result.get("matchesExpected") is True and result.get("unchangedDuringRead") is True
        return result

    def verify_manifest(self, path: str, base: str | None = None) -> dict[str, Any]:
        """Verify a files-array JSON manifest's hashes and optional sizes. Relative entries resolve beside the manifest or beneath explicit base."""
        return core.verify_manifest(_absolute(path), _absolute(base) if base is not None else None)

    def compare_archives(self, baseline: str, candidate: str,
                         allowed_paths: list[str] | None = None) -> dict[str, Any]:
        """Hash and compare ZIP/PAK entries by normalized path AND occurrence. Optional allowed-path globs constrain additions/removals/changes; this is not gameplay acceptance."""
        return core.compare_archives(_absolute(baseline), _absolute(candidate), allowed_paths)

    def source_inventory(self, source_root: str, assets: list[SourceAsset]) -> dict[str, Any]:
        """Hash only declared ordered source files. Each asset declares asset/exportMethod/files; each file declares a root-relative path and role. Return inventory without saving it."""
        return source.capture_source_inventory(_absolute(source_root), assets)

    def source_compare(self, expected_manifest: str, actual_manifest: str) -> dict[str, Any]:
        """Compare two inventory JSON files from source_inventory; verify internal digests, file/asset order, export methods and hashes, allowing source-root relocation."""
        return source.compare_source_baselines(core.load_json(_absolute(expected_manifest)),
                                               core.load_json(_absolute(actual_manifest)))

    def storage_review(self, run_roots: list[str], sdk_templates: str,
                       git_repo: str | None = None, temp_pack: str | None = None) -> dict[str, Any]:
        """Read declared old run folders for exact SDK-template copies and return allocation/hash evidence. Optional Git repo/temp-pack must be paired. No files are removed and no GC/repack runs."""
        if not run_roots:
            raise core.RoadcraftError("Declare at least one run root")
        if (git_repo is None) != (temp_pack is None):
            raise core.RoadcraftError("git_repo and temp_pack must be provided together")
        return cleanup.build_review([_absolute(path) for path in run_roots], _absolute(sdk_templates),
                                    _absolute(git_repo) if git_repo else None,
                                    _absolute(temp_pack) if temp_pack else None)

    def evidence_report(self, receipts: list[ReceiptPin], title: str = "RoadCraft evidence review",
                        include_html: bool = False) -> dict[str, Any]:
        """Verify receipt/image hashes and generate an in-memory JSON/contact-sheet report. Optional HTML is returned only up to 2 MiB. No file is saved. Unpinned roots or incomplete contexts cannot yield comparisons; visual/campaign acceptance remain separate claims."""
        if not receipts:
            raise review.ReviewError("At least one receipt is required")
        collector = review._Collector()
        for receipt in receipts:
            collector.collect(_absolute(receipt["path"]), receipt.get("sha256"))
        capture_pairs, capture_blocked = review._compare(collector.captures)
        metric_pairs, metric_blocked = review._compare(collector.metrics, metrics=True)
        manifest = {
            "schemaVersion": 1, "kind": "roadcraft.review", "title": title,
            "receipts": collector.sources, "captures": collector.captures, "metrics": collector.metrics,
            "captureComparisons": capture_pairs, "metricComparisons": metric_pairs,
            "comparisonExclusions": capture_blocked + metric_blocked,
            "evidence": {
                "captured": {"state": "hash_verified" if collector.captures else "not_provided",
                             "count": len(collector.captures)},
                "numerical": {"state": "compared" if metric_pairs else
                              "recorded_only" if collector.metrics else "not_provided",
                              "records": len(collector.metrics), "matchedPairs": len(metric_pairs),
                              "acceptance": "not_assessed_by_report"},
                "visual": {"state": "not_assessed_by_report", "claims": collector.claims["visual"]},
                "campaign": {"state": "not_assessed_by_report", "claims": collector.claims["campaign"]},
            },
        }
        rendered = review._render(manifest, collector.images, title)
        encoded = rendered.encode("utf-8")
        result = {"manifest": manifest, "writesPerformed": False,
                  "htmlSha256": hashlib.sha256(encoded).hexdigest(), "htmlBytes": len(encoded)}
        if include_html and len(encoded) <= MAX_RETURNED_HTML_BYTES:
            result["html"] = rendered
        elif include_html:
            result["htmlOmittedReason"] = "HTML exceeds 2 MiB response limit; use the local review CLI to save the full report"
        return result


TOOL_NAMES = (
    "project_status", "project_doctor", "verify_project", "inspect_file", "verify_file",
    "verify_manifest", "compare_archives", "source_inventory", "source_compare",
    "storage_review", "evidence_report",
)


def create_server(settings: ServerSettings | None = None) -> Any:
    """Register only typed read-only methods; SDK handles the MCP wire protocol."""
    fast_mcp, annotations = _sdk_components()
    server = fast_mcp("RoadCraft Toolchain", instructions=INSTRUCTIONS, log_level="WARNING")
    operations = RoadcraftTools(settings or ServerSettings.defaults())
    for name in TOOL_NAMES:
        server.add_tool(getattr(operations, name), name=name,
                        annotations=annotations(readOnlyHint=True, destructiveHint=False,
                                                idempotentHint=True, openWorldHint=False))
    return server


def main(argv: list[str] | None = None) -> int:
    defaults = ServerSettings.defaults()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=defaults.registry)
    parser.add_argument("--config", type=Path, default=defaults.config)
    args = parser.parse_args(argv)
    try:
        server = create_server(ServerSettings(args.registry.expanduser().resolve(), args.config.expanduser().resolve()))
    except MCPDependencyError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    server.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
