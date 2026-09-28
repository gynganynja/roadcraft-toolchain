"""No-save v2/v3 D11 source-mesh readback using the pinned base Blend worker.

The accepted variant Blend files have the same reviewed bytes as the base
Blend. The base worker supplies source facts; this wrapper verifies each
variant's own accepted inputs and interprets those facts against that
variant's repaired/native worklist gaps. It does not export or save assets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from . import blender_mesh_inventory as base
from .blender_authoring import BlenderAuthoringError, _pinned_asset
from .blender_left_push_probe import INVENTORY_SHA256, LeftPushProbeError, require_hash, _unlinked_path
from .source import file_sha256


BASE_HOST_SHA256 = "32db82dd01e40d5808d830564f999489c0f80fc373c34b8665b88fd462fd68e2"
ASSET_PINS = {
    "cat_d11t_v2": {
        "sourceAssetDigest": "6f6d47667c5dd24aa18fa1734aa2cbc7c6af48ac28bc57c67e8609f899f22d6f",
        "blendSha256": base.BLEND_SHA256,
        "repairedUsfSha256": "096a3cc042e382becb69e25c722dbaf0e2c2a65608cf6ff01008705eb0bad24a",
    },
    "cat_d11t_v3": {
        "sourceAssetDigest": "7c3588072e21e5aa8944d136491ebc26e9dace14ab47929bd8672a75ffbac0e7",
        "blendSha256": base.BLEND_SHA256,
        "repairedUsfSha256": "1346b73da9cf72b6e866a722d929fd5c18305537f9ef3acd369f84ea808993d1",
    },
}


class VariantMeshInventoryError(RuntimeError):
    """A variant identity, source readback or gap interpretation differs."""


def _pins(asset_name: str) -> dict[str, str]:
    try:
        return ASSET_PINS[asset_name]
    except (KeyError, TypeError) as exc:
        raise VariantMeshInventoryError("asset is outside the reviewed v2/v3 allowlist") from exc


def _variant_rows(worklist: dict, asset_name: str,
                  source_asset_digest: str) -> list[dict]:
    pins = _pins(asset_name)
    if (source_asset_digest != pins["sourceAssetDigest"] or
            worklist.get("schemaVersion") != 1 or
            worklist.get("status") != "RECONSTRUCTION_REQUIRED" or
            worklist.get("nativeBlendExportApproved") is not False or
            worklist.get("inventorySha256") != INVENTORY_SHA256):
        raise VariantMeshInventoryError("variant worklist identity or gate differs")
    assets = worklist.get("assets")
    if not isinstance(assets, list):
        raise VariantMeshInventoryError("worklist asset collection is malformed")
    matching = [row for row in assets if isinstance(row, dict) and
                row.get("asset") == asset_name]
    if len(matching) != 1:
        raise VariantMeshInventoryError("worklist has no unique variant asset")
    asset = matching[0]
    if (asset.get("sourceAssetDigest") != pins["sourceAssetDigest"] or
            asset.get("blendSha256") != pins["blendSha256"] or
            asset.get("repairedUsfSha256") != pins["repairedUsfSha256"] or
            asset.get("nativeBlendExportApproved") is not False):
        raise VariantMeshInventoryError("variant worklist pins differ")
    try:
        rows = sorted(asset["findings"]["changedMeshNodes"],
                      key=lambda row: row["path"])
        base_rows = base._worklist_rows(worklist, _BASE_ASSET_DIGEST)
        paths = [row["path"] for row in rows]
    except (KeyError, TypeError, ValueError) as exc:
        raise VariantMeshInventoryError("worklist mesh rows are malformed") from exc
    if (len(rows) != base.EXPECTED_GAP_ROWS or len(set(paths)) != len(paths) or
            any(not isinstance(path, str) or not path.startswith("|@root|")
                for path in paths) or
            paths != [row["path"] for row in base_rows]):
        raise VariantMeshInventoryError("variant/base mesh path coverage differs")
    return rows


_BASE_ASSET_DIGEST = "ec611b9f0433874d30422c79f5658598d8ed50b89d5f265d42b423a50341bf30"


def _variant_inputs(registry_path: Path, asset_name: str) -> dict:
    pins = _pins(asset_name)
    registry = _unlinked_path(registry_path, "registry")
    registry_sha = file_sha256(registry)
    config = json.loads(registry.read_text(encoding="utf-8"))
    inventory_ref = config["accepted"]["authoringInventory"]
    if inventory_ref["sha256"] != INVENTORY_SHA256:
        raise VariantMeshInventoryError("accepted inventory pin differs")
    inventory_path = _unlinked_path(registry.parent / inventory_ref["path"],
                                    "authoring inventory")
    if not inventory_path.is_relative_to(registry.parent):
        raise VariantMeshInventoryError("inventory is outside registry checkout")
    _, source_root, asset, blend, usf = _pinned_asset(
        inventory_path, INVENTORY_SHA256, asset_name)
    if asset["assetDigest"] != pins["sourceAssetDigest"]:
        raise VariantMeshInventoryError("accepted asset digest differs")
    require_hash(blend, pins["blendSha256"], "variant source Blend")
    require_hash(usf, pins["repairedUsfSha256"], "variant repaired USF")
    worklist = require_hash(base.WORKLIST, base.WORKLIST_SHA256,
                            "reconstruction worklist")
    gap_rows = _variant_rows(json.loads(worklist.read_text(encoding="utf-8")),
                             asset_name, asset["assetDigest"])
    return {
        "registrySha256": registry_sha,
        "sourceRoot": source_root,
        "blend": blend,
        "usf": usf,
        "gapRows": gap_rows,
    }


def interpret_variant(base_result: dict, asset_name: str,
                      gap_rows: list[dict]) -> dict:
    pins = _pins(asset_name)
    expected_base = {
        "schemaVersion": 1, "status": "SOURCE_GAP_INVENTORY",
        "asset": "cat_d11t", "blendSha256": pins["blendSha256"],
        "repairedUsfSha256": base.USF_SHA256,
        "inventorySha256": INVENTORY_SHA256,
        "worklistSha256": base.WORKLIST_SHA256,
        "workerSha256": base.WORKER_SHA256,
        "sceneFrame": 1, "sceneMeshObjects": 210,
        "mappedGapRows": base.EXPECTED_GAP_ROWS,
        "unmappedGapRows": 0, "blendSaved": False,
        "usfExported": False, "nativeBlendExportApproved": False,
        "sourceUnchanged": True, "sdkUnchanged": True,
    }
    if (not isinstance(base_result, dict) or
            any(type(base_result.get(key)) is not type(value) or
                base_result.get(key) != value
                for key, value in expected_base.items())):
        raise VariantMeshInventoryError("base readback identity or no-write proof differs")
    blender_sha = base_result.get("blenderSha256")
    version = base_result.get("blenderVersion")
    if (blender_sha not in base.BLENDER_VERSION_PINS or
            not isinstance(version, str) or
            not version.startswith(base.BLENDER_VERSION_PINS[blender_sha])):
        raise VariantMeshInventoryError("base Blender pin or version differs")
    rows = base_result.get("rows")
    if (not isinstance(rows, list) or len(rows) != base.EXPECTED_GAP_ROWS or
            len(gap_rows) != base.EXPECTED_GAP_ROWS or
            len({row.get("path") for row in rows if isinstance(row, dict)}) !=
            base.EXPECTED_GAP_ROWS):
        raise VariantMeshInventoryError("base readback mesh coverage differs")
    if (hashlib.sha256(base._canonical(rows)).hexdigest() !=
            base_result.get("rowsDigestSha256")):
        raise VariantMeshInventoryError("base readback row digest differs")
    interpreted = []
    for row, gap in zip(rows, gap_rows):
        if (not isinstance(row, dict) or row.get("path") != gap.get("path") or
                row.get("mappingStatus") != "SDK_PATH_RECONSTRUCTED" or
                not row.get("sourceObject") or
                row.get("predictedSdkPath") != gap["path"] or
                row.get("sourceVisible") is not True):
            raise VariantMeshInventoryError("base source mapping differs from variant gap")
        facts = base._validate_facts(row.get("sourceFacts"))
        interpreted.append({
            "path": gap["path"],
            "sourceObject": row["sourceObject"],
            "predictedSdkPath": row["predictedSdkPath"],
            "mappingStatus": row["mappingStatus"],
            "parentObject": row.get("parentObject"),
            "parentBone": row.get("parentBone"),
            "parentType": row.get("parentType"),
            "sourceVisible": row["sourceVisible"],
            "sourceFacts": facts,
            "gapFindings": base._gap_findings(gap, facts),
        })
    result = {key: base_result[key] for key in expected_base}
    result.update({
        "asset": asset_name,
        "sourceAssetDigest": pins["sourceAssetDigest"],
        "repairedUsfSha256": pins["repairedUsfSha256"],
        "blenderSha256": blender_sha,
        "blenderVersion": version,
        "sourceFactsFromAsset": "cat_d11t",
        "sourceFactsFromByteIdenticalBlend": True,
        "baseSourceRowsDigestSha256": base_result["rowsDigestSha256"],
        "rowsDigestSha256": hashlib.sha256(base._canonical(interpreted)).hexdigest(),
        "repairedOnlyMaterialLabelsAbsentFromSourceRows": sum(
            bool(row["gapFindings"]["repairedOnlyLabelsAbsentFromSource"])
            for row in interpreted),
        "rows": interpreted,
    })
    if len(base._canonical(result)) > base.MAX_JSON_BYTES:
        raise VariantMeshInventoryError("bounded variant readback exceeded")
    return result


def run_probe(*, registry_path: Path, blender_executable: Path,
              sdk_script_root: Path, asset_name: str,
              timeout_seconds: int = 300) -> dict:
    _pins(asset_name)
    require_hash(Path(base.__file__), BASE_HOST_SHA256,
                 "pinned base mesh readback host")
    before = _variant_inputs(registry_path, asset_name)
    base_result = base.run_probe(
        registry_path=registry_path, blender_executable=blender_executable,
        sdk_script_root=sdk_script_root, timeout_seconds=timeout_seconds)
    result = interpret_variant(base_result, asset_name, before["gapRows"])
    after = _variant_inputs(registry_path, asset_name)
    if (before["registrySha256"] != after["registrySha256"] or
            before["sourceRoot"] != after["sourceRoot"] or
            before["blend"] != after["blend"] or
            before["usf"] != after["usf"] or
            before["gapRows"] != after["gapRows"]):
        raise VariantMeshInventoryError("variant inputs changed during readback")
    require_hash(Path(base.__file__), BASE_HOST_SHA256,
                 "base mesh readback host after variant probe")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", choices=tuple(ASSET_PINS), required=True)
    parser.add_argument("--registry", type=Path,
                        default=base.TOOLCHAIN_ROOT / "project.json")
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    args = parser.parse_args(argv)
    try:
        result = run_probe(
            registry_path=args.registry, blender_executable=args.blender,
            sdk_script_root=args.sdk_script_root, asset_name=args.asset,
            timeout_seconds=args.timeout_seconds)
    except (VariantMeshInventoryError, base.MeshInventoryError,
            LeftPushProbeError, BlenderAuthoringError, OSError, ValueError,
            KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"schemaVersion": 1, "status": "ERROR",
                          "error": str(exc),
                          "nativeBlendExportApproved": False}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
