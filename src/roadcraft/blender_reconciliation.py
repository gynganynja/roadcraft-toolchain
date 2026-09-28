"""Build a pinned, read-only worklist from Blender/USF parity evidence.

The worklist describes differences, not fixes or export approval. A shared
leaf name at two hierarchy paths is only a relocation candidate; the archive
does not contain the missing/extra nodes' full geometry for equivalence checks.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping

from .blender_authoring import _pinned_asset
from .source import (capture_source_inventory, compare_source_baselines,
                     file_sha256)


_MATERIAL_NAME = re.compile(r'material\s*=\s*\{\s*name\s*=\s*"([^"\r\n]+)"')
_MAX_ARCHIVE_BYTES = 8 * 1024 * 1024
_MAX_RAW_BYTES = 32 * 1024 * 1024


class ReconciliationError(ValueError):
    """A parity archive or current source pin cannot support a worklist."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _material_label(serialized: str) -> str:
    match = _MATERIAL_NAME.search(serialized)
    return match.group(1) if match else "sha256:" + _sha(serialized.encode("utf-8"))


def _counts(values: list[str]) -> list[dict[str, Any]]:
    return [{"label": label, "count": count}
            for label, count in sorted(Counter(values).items())]


def _path_findings(diff: Mapping[str, Any]) -> dict[str, Any]:
    missing = diff["missingNodePaths"]
    extra = diff["extraNodePaths"]
    by_old: dict[str, list[str]] = defaultdict(list)
    by_new: dict[str, list[str]] = defaultdict(list)
    for path in missing:
        by_old[path.rsplit("|", 1)[-1]].append(path)
    for path in extra:
        by_new[path.rsplit("|", 1)[-1]].append(path)
    candidates = [
        {"leafName": name, "repairedPath": by_old[name][0],
         "nativeExportPath": by_new[name][0],
         "equivalenceVerified": False}
        for name in sorted(by_old.keys() & by_new.keys())
        if len(by_old[name]) == len(by_new[name]) == 1
    ]
    paired_old = {row["repairedPath"] for row in candidates}
    paired_new = {row["nativeExportPath"] for row in candidates}
    return {
        "pathRelocationCandidates": candidates,
        "repairedOnlyPaths": sorted(set(missing) - paired_old),
        "nativeExportOnlyPaths": sorted(set(extra) - paired_new),
        "ambiguousSharedLeafNames": sorted(name for name in by_old.keys() & by_new.keys()
                                           if len(by_old[name]) != 1 or len(by_new[name]) != 1),
    }


def _mesh_findings(path: str, pair: Mapping[str, Any]) -> dict[str, Any]:
    old = pair.get("baseline") or {}
    new = pair.get("candidate") or {}
    old_materials = old.get("materialNames", [])
    new_materials = new.get("materialNames", [])
    old_labels = [_material_label(value) for value in old_materials]
    new_labels = [_material_label(value) for value in new_materials]
    old_count = Counter(old_labels)
    new_count = Counter(new_labels)
    numeric = ("vertices", "faces", "normals", "uvSets", "colorSets", "skinEntries")
    measurements = {
        key: {"repaired": old.get(key), "nativeExport": new.get(key)}
        for key in numeric if old.get(key) != new.get(key)
    }
    old_bones = old.get("skinBoneNodeUids", [])
    new_bones = new.get("skinBoneNodeUids", [])
    return {
        "path": path,
        "measurements": measurements,
        "repairedMaterialSlots": len(old_materials),
        "nativeExportMaterialSlots": len(new_materials),
        "missingMaterialLabels": _counts(list((old_count - new_count).elements())),
        "extraMaterialLabels": _counts(list((new_count - old_count).elements())),
        "materialLabelOrderDifferent": old_labels != new_labels,
        "materialPayloadDifferent": old_materials != new_materials,
        "repairedMaterialPayloadSha256": _sha(_canonical(old_materials)),
        "nativeExportMaterialPayloadSha256": _sha(_canonical(new_materials)),
        "repairedSkinBoneUidCount": len(old_bones),
        "nativeExportSkinBoneUidCount": len(new_bones),
        "skinBoneUidOrderDifferent": old_bones != new_bones,
        "inverseBindMatricesDifferent": (
            old.get("inverseBindMatricesSha256") !=
            new.get("inverseBindMatricesSha256")),
    }


def reconcile_diff(diff: Mapping[str, Any]) -> dict[str, Any]:
    """Extract named tasks while keeping all equivalence claims false."""
    paths = _path_findings(diff)
    mesh_rows = []
    animation_rows = []
    child_rows = []
    transform_rows = []
    for row in diff["matchedNodeDifferences"]:
        fields = row["fields"]
        path = row["path"]
        if "mesh" in fields:
            mesh_rows.append(_mesh_findings(path, fields["mesh"]))
        if "animation" in fields:
            animation_rows.append({"path": path, **fields["animation"]})
        if "childCount" in fields:
            child_rows.append({"path": path, **fields["childCount"]})
        for field in ("localTransformSha256", "worldTransformSha256"):
            if field in fields:
                transform_rows.append({"path": path, "field": field,
                                       **fields[field]})
    return {
        **paths,
        "changedMeshNodes": mesh_rows,
        "changedAnimationNodes": animation_rows,
        "changedChildCounts": child_rows,
        "changedTransforms": transform_rows,
        "counts": {
            "totalRepairedOnlyPaths": len(diff["missingNodePaths"]),
            "totalNativeExportOnlyPaths": len(diff["extraNodePaths"]),
            "pathRelocationCandidates": len(paths["pathRelocationCandidates"]),
            "unpairedRepairedPaths": len(paths["repairedOnlyPaths"]),
            "unpairedNativeExportPaths": len(paths["nativeExportOnlyPaths"]),
            "changedMeshNodes": len(mesh_rows),
            "changedAnimationNodes": len(animation_rows),
            "changedChildCounts": len(child_rows),
            "changedTransforms": len(transform_rows),
        },
    }


def _verified_full(summary_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    summary_bytes = summary_path.read_bytes()
    summary = json.loads(summary_bytes)
    archive = Path(summary["archivePath"]).resolve(strict=True)
    if archive.stat().st_size > _MAX_ARCHIVE_BYTES:
        raise ReconciliationError("parity archive is too large")
    archive_bytes = archive.read_bytes()
    if (len(archive_bytes) != summary["archiveBytes"] or
            _sha(archive_bytes) != summary["archiveSha256"]):
        raise ReconciliationError("parity archive differs from summary pin")
    with gzip.open(archive, "rb") as stream:
        raw = stream.read(_MAX_RAW_BYTES + 1)
    if (len(raw) > _MAX_RAW_BYTES or len(raw) != summary["fullRawBytes"] or
            _sha(raw) != summary["fullRawSha256"]):
        raise ReconciliationError("parity JSON differs from summary pin")
    full = json.loads(raw)
    for key in ("asset", "inventorySha256", "sourceAssetDigest", "blendPath",
                "blendSha256", "baselineUsfPath", "baselineUsfSha256",
                "candidateUsfPath", "sdkFileHashes", "helperSha256",
                "diffSha256", "summarySha256", "status", "exportGate"):
        if full.get(key) != summary.get(key):
            raise ReconciliationError(f"parity summary/full mismatch: {key}")
    if (full.get("candidateUsfSha256Observed") != summary.get("candidateUsfSha256") or
            full.get("candidateUsfBytesObserved") != summary.get("candidateUsfBytes")):
        raise ReconciliationError("candidate digest differs from summary")
    if (full.get("status") != "PARITY_DIFFERENT" or
            full.get("nativeBlendExportApproved") is not False or
            summary.get("nativeBlendExportApproved") is not False or
            full.get("exportGate", {}).get("status") != "BLOCKED" or
            full.get("sourceUnchanged") is not True or
            full.get("sdkUnchanged") is not True or
            full.get("blenderExitCode") != 0):
        raise ReconciliationError("parity evidence does not have a blocked-difference verdict")
    diagnostic = full.get("diagnostic", {})
    if (diagnostic.get("blendSha256") != full["blendSha256"] or
            diagnostic.get("baselineUsfSha256") != full["baselineUsfSha256"] or
            diagnostic.get("candidateUsfSha256") != summary["candidateUsfSha256"] or
            diagnostic.get("candidateUsfBytes") != summary["candidateUsfBytes"] or
            diagnostic.get("nativeBlendExportApproved") is not False):
        raise ReconciliationError("Blender helper disagrees with outer receipt")
    if file_sha256(Path(full["candidateUsfPath"])) != summary["candidateUsfSha256"]:
        raise ReconciliationError("scratch native export differs from pin")
    return summary, full


def build_reconciliation_report(
    registry_path: str | Path, summary_paths: list[str | Path],
) -> dict[str, Any]:
    """Verify current authoring sources and sealed archives before deriving work."""
    registry_file = Path(registry_path).resolve(strict=True)
    registry = json.loads(registry_file.read_text(encoding="utf-8"))
    accepted = registry["accepted"]
    inventory_decl = accepted["authoringInventory"]
    inventory_path = (registry_file.parent / inventory_decl["path"]).resolve(strict=True)
    inventory_sha = inventory_decl["sha256"]
    if file_sha256(inventory_path) != inventory_sha:
        raise ReconciliationError("current authoring inventory differs from registry pin")
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    declarations = [{
        "asset": asset["asset"], "exportMethod": asset["exportMethod"],
        "files": [{"path": row["path"], "role": row["role"]}
                  for row in asset["files"]],
    } for asset in inventory["assets"]]
    current = capture_source_inventory(Path(inventory["sourceRoot"]), declarations)
    if not compare_source_baselines(inventory, current)["matches"]:
        raise ReconciliationError("declared authoring source differs from inventory")
    assets = []
    seen = set()
    for provided_path in summary_paths:
        summary_path = Path(provided_path).resolve(strict=True)
        summary, full = _verified_full(summary_path)
        asset_name = summary["asset"]
        if asset_name in seen:
            raise ReconciliationError(f"duplicate asset summary: {asset_name}")
        seen.add(asset_name)
        _, _, asset_row, blend, baseline = _pinned_asset(
            inventory_path, inventory_sha, asset_name)
        if (summary["inventorySha256"] != inventory_sha or
                summary["sourceAssetDigest"] != asset_row["assetDigest"] or
                Path(summary["blendPath"]).resolve() != blend or
                Path(summary["baselineUsfPath"]).resolve() != baseline or
                summary["blendSha256"] != file_sha256(blend) or
                summary["baselineUsfSha256"] != file_sha256(baseline)):
            raise ReconciliationError(f"{asset_name}: current authoring source differs")
        diagnostic = full["diagnostic"]
        if diagnostic["nodeDiff"]["matchesIndexedFields"] is not False:
            raise ReconciliationError(f"{asset_name}: node diff has no differences")
        assets.append({
            "asset": asset_name,
            "sourceAssetDigest": asset_row["assetDigest"],
            "repairedUsfSha256": summary["baselineUsfSha256"],
            "blendSha256": summary["blendSha256"],
            "scratchNativeUsfSha256": summary["candidateUsfSha256"],
            "summaryPath": str(summary_path),
            "summarySha256": _sha(summary_path.read_bytes()),
            "archiveSha256": summary["archiveSha256"],
            "fullRawSha256": summary["fullRawSha256"],
            "repairedTotals": diagnostic["baselineSemantic"],
            "nativeExportTotals": diagnostic["candidateSemantic"],
            "repairedRootName": diagnostic["baselineRootName"],
            "nativeExportRootName": diagnostic["candidateRootName"],
            "findings": reconcile_diff(diagnostic["nodeDiff"]),
            "nativeBlendExportApproved": False,
        })
    if not assets:
        raise ReconciliationError("at least one parity summary is required")
    assets.sort(key=lambda row: row["asset"])
    return {
        "schemaVersion": 1,
        "status": "RECONSTRUCTION_REQUIRED",
        "registryPath": str(registry_file),
        "registrySha256": file_sha256(registry_file),
        "inventoryPath": str(inventory_path),
        "inventorySha256": inventory_sha,
        "sourceInventoryVerified": True,
        "sourceFileCount": sum(len(asset["files"]) for asset in inventory["assets"]),
        "assets": assets,
        "nativeBlendExportApproved": False,
        "limits": [
            "Matching leaf names at different hierarchy paths do not prove equivalent nodes.",
            "Export differences do not prove whether the source Blend, SDK exporter, or both need changes.",
            "This worklist does not establish compilation, native-view, visual, or campaign parity.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--summary", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_reconciliation_report(args.registry, args.summary)
    payload = json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps({"status": result["status"], "assets": [row["asset"]
                      for row in result["assets"]], "output": str(args.output)},
                     sort_keys=True))


if __name__ == "__main__":
    main()
