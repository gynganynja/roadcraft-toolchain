"""Pinned, no-save source inventory for D11 Blender mesh parity gaps.

This observes the historical Blend; it never exports a USF, writes an asset,
or approves the native-Blend route. A source-object path is a candidate until
the pinned SDK's direct-parent/flat-LOD naming rule reconstructs it exactly.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from .blender_armature_parity import (
    BLEND_SHA256, BLENDER_VERSION_PINS, USF_SHA256,
)
from .blender_authoring import BlenderAuthoringError, _pinned_asset
from .blender_left_push_probe import (
    INVENTORY_SHA256, LeftPushProbeError, _unlinked_path, require_hash,
    require_sdk_pins,
)
from .source import file_sha256


TOOLCHAIN_ROOT = Path(__file__).resolve().parents[2]
WORKLIST = TOOLCHAIN_ROOT / "operations/d11_blender_reconstruction_worklist_20260928.json"
WORKLIST_SHA256 = "a842c0e7dd355e64ace39a724a806f509328ba3fb1916fc7ab4bbb85062759c3"
WORKER = Path(__file__).with_name("blender_mesh_inventory_worker.py")
WORKER_SHA256 = "e29122c28bbe60a254a7c239fcc84be7d2f05a57c0ce305132069edd5b264113"
RESULT_PREFIX = "ROADCRAFT_MESH_INVENTORY "
EXPECTED_GAP_ROWS = 126
MAX_JSON_BYTES = 512 * 1024
METRIC_FIELDS = {
    "vertices": "sdkExpectedVertices",
    "faces": "sdkExpectedFaces",
    "normals": "sdkExpectedNormals",
    "uvSets": "sdkExpectedUvSets",
    "colorSets": "sdkExpectedColorSets",
    "skinEntries": "sdkExpectedSkinEntries",
}
COUNT_FIELDS = (
    "rawVertices", "rawPolygons", "rawTriangles", "evaluatedVertices",
    "evaluatedPolygons", "evaluatedTriangles", "saberNormalsCount",
    "armatureModifierCount", "firstArmaturePoseBoneCount",
    "weightedRawVertices", "sdkExpectedVertices", "sdkExpectedFaces",
    "sdkExpectedNormals", "sdkExpectedUvSets", "sdkExpectedColorSets",
    "sdkExpectedMaterialSlots", "sdkExpectedSkinEntries",
    "sdkExpectedSkinBones",
)


class MeshInventoryError(RuntimeError):
    """A pinned readback or its source-gap interpretation is invalid."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _worklist_rows(worklist: dict, source_asset_digest: str) -> list[dict]:
    if (worklist.get("schemaVersion") != 1 or
            worklist.get("status") != "RECONSTRUCTION_REQUIRED" or
            worklist.get("nativeBlendExportApproved") is not False or
            worklist.get("inventorySha256") != INVENTORY_SHA256):
        raise MeshInventoryError("worklist identity or blocked gate differs")
    assets = [asset for asset in worklist.get("assets", [])
              if asset.get("asset") == "cat_d11t"]
    if len(assets) != 1:
        raise MeshInventoryError("worklist has no unique base asset")
    asset = assets[0]
    if (asset.get("sourceAssetDigest") != source_asset_digest or
            asset.get("blendSha256") != BLEND_SHA256 or
            asset.get("repairedUsfSha256") != USF_SHA256 or
            asset.get("nativeBlendExportApproved") is not False):
        raise MeshInventoryError("worklist base asset differs from source pins")
    rows = sorted(asset["findings"]["changedMeshNodes"], key=lambda row: row["path"])
    paths = [row["path"] for row in rows]
    if (len(rows) != EXPECTED_GAP_ROWS or len(set(paths)) != len(paths) or
            any(not path.startswith("|@root|") for path in paths)):
        raise MeshInventoryError("worklist mesh gap coverage differs")
    return rows


def _validate_facts(facts: object) -> dict:
    if not isinstance(facts, dict):
        raise MeshInventoryError("mapped source mesh has no facts")
    for field in COUNT_FIELDS:
        value = facts.get(field)
        if field == "saberNormalsCount" and value is None:
            continue
        if type(value) is not int or value < 0:
            raise MeshInventoryError(f"source mesh {field} is invalid")
    for field in ("evaluatedMaterialNames", "evaluatedUvNames",
                  "evaluatedColorNames", "evaluatedCustomColorNames",
                  "vertexGroupNames"):
        value = facts.get(field)
        if (not isinstance(value, list) or len(value) > 512 or
                any(not isinstance(name, str) or not name or len(name) > 256
                    for name in value)):
            raise MeshInventoryError(f"source mesh {field} is invalid")
    if (facts["sdkExpectedFaces"] != facts["evaluatedTriangles"] or
            facts["sdkExpectedVertices"] != facts["evaluatedTriangles"] * 3 or
            facts["sdkExpectedNormals"] != (facts["saberNormalsCount"]
                                            if facts["saberNormalsCount"] is not None
                                            else facts["sdkExpectedVertices"]) or
            facts["sdkExpectedUvSets"] != len(facts["evaluatedUvNames"]) or
            facts["sdkExpectedColorSets"] != (
                len(facts["evaluatedColorNames"]) +
                len(facts["evaluatedCustomColorNames"])) or
            facts["sdkExpectedMaterialSlots"] != (
                len(facts["evaluatedMaterialNames"]) or 1) or
            facts["sdkExpectedSkinBones"] != (
                facts["firstArmaturePoseBoneCount"]
                if facts["firstArmaturePoseBoneCount"] and facts["weightedRawVertices"]
                else 0) or
            facts["sdkExpectedSkinEntries"] != (
                facts["sdkExpectedVertices"] if facts["sdkExpectedSkinBones"] else 0)):
        raise MeshInventoryError("source mesh SDK count derivation is inconsistent")
    target = facts.get("firstArmatureTarget")
    if target is not None and (not isinstance(target, str) or len(target) > 256):
        raise MeshInventoryError("source mesh armature target is invalid")
    return facts


def _compare_count(source: int, repaired: int, native: int) -> str:
    if source == native and source != repaired:
        return "SOURCE_MATCHES_NATIVE"
    if source == repaired and source != native:
        return "SOURCE_MATCHES_REPAIRED"
    if source != native and source != repaired:
        return "SOURCE_MATCHES_NEITHER"
    raise MeshInventoryError("gap evidence has equal repaired/native counts")


def _gap_findings(gap: dict, facts: dict) -> dict:
    materials = Counter(facts["evaluatedMaterialNames"] or ["blender_default"])
    missing_labels = gap["missingMaterialLabels"]
    absent = []
    present = []
    for entry in missing_labels:
        name = entry["label"]
        count = entry["count"]
        if not isinstance(name, str) or type(count) is not int or count < 1:
            raise MeshInventoryError("worklist missing-material entry is malformed")
        have = min(materials[name], count)
        if have:
            present.append({"label": name, "count": have})
        if count > have:
            absent.append({"label": name, "count": count - have})
    measurements = {}
    for name, pair in gap["measurements"].items():
        if name not in METRIC_FIELDS:
            raise MeshInventoryError(f"unexpected worklist metric: {name}")
        repaired = pair["repaired"]
        native = pair["nativeExport"]
        if (type(repaired) is not int or repaired < 0 or
                type(native) is not int or native < 0):
            raise MeshInventoryError("worklist metric value is invalid")
        source = facts[METRIC_FIELDS[name]]
        measurements[name] = {"sourceSdkExpected": source, "repaired": repaired,
                              "nativeExport": native,
                              "classification": _compare_count(source, repaired, native)}
    source_slots = facts["sdkExpectedMaterialSlots"]
    repaired_slots = gap["repairedMaterialSlots"]
    native_slots = gap["nativeExportMaterialSlots"]
    if (type(repaired_slots) is not int or type(native_slots) is not int or
            repaired_slots < 0 or native_slots < 0):
        raise MeshInventoryError("worklist material slot count is invalid")
    slot_classification = (_compare_count(source_slots, repaired_slots, native_slots)
                           if repaired_slots != native_slots else "SLOT_COUNTS_EQUAL")
    repaired_bones = gap["repairedSkinBoneUidCount"]
    native_bones = gap["nativeExportSkinBoneUidCount"]
    if (type(repaired_bones) is not int or type(native_bones) is not int or
            repaired_bones < 0 or native_bones < 0):
        raise MeshInventoryError("worklist skin bone count is invalid")
    source_bones = facts["sdkExpectedSkinBones"]
    bone_classification = (_compare_count(source_bones, repaired_bones, native_bones)
                           if repaired_bones != native_bones else "BONE_COUNTS_EQUAL")
    return {
        "repairedOnlyLabelsAbsentFromSource": absent,
        "repairedOnlyLabelsPresentInSource": present,
        "materialSlots": {"sourceSdkExpected": source_slots,
                          "repaired": repaired_slots, "nativeExport": native_slots,
                          "classification": slot_classification},
        "skinBones": {"sourceSdkExpected": source_bones,
                      "repaired": repaired_bones, "nativeExport": native_bones,
                      "classification": bone_classification},
        "recordedCountGaps": measurements,
        "inverseBindMatricesDifferent": gap["inverseBindMatricesDifferent"],
        "bindParityEvaluated": False,
    }


def interpret_readback(result: dict, gap_rows: list[dict],
                       expected_blender_sha256: str) -> dict:
    expected = {
        "schemaVersion": 1, "asset": "cat_d11t",
        "blendSha256": BLEND_SHA256, "repairedUsfSha256": USF_SHA256,
        "worklistSha256": WORKLIST_SHA256,
        "blenderSha256": expected_blender_sha256, "sceneFrame": 1,
        "sceneMeshObjects": 210, "blendSaved": False, "usfExported": False,
        "nativeBlendExportApproved": False,
    }
    if any(type(result.get(key)) is not type(value) or result.get(key) != value
           for key, value in expected.items()):
        raise MeshInventoryError("Blender readback identity or no-write fields differ")
    if (expected_blender_sha256 not in BLENDER_VERSION_PINS or
            not isinstance(result.get("blenderVersion"), str) or
            not result["blenderVersion"].startswith(
                BLENDER_VERSION_PINS[expected_blender_sha256])):
        raise MeshInventoryError("Blender version differs")
    rows = result.get("rows")
    if not isinstance(rows, list) or len(rows) != len(gap_rows):
        raise MeshInventoryError("Blender omitted mesh gap rows")
    interpreted = []
    mapped_objects = set()
    for row, gap in zip(rows, gap_rows):
        if not isinstance(row, dict) or row.get("path") != gap["path"]:
            raise MeshInventoryError("Blender mesh paths differ from pinned worklist")
        status = row.get("mappingStatus")
        name = row.get("sourceObject")
        predicted = row.get("predictedSdkPath")
        if (status not in ("SDK_PATH_RECONSTRUCTED", "UNMAPPED") or
                name is not None and (not isinstance(name, str) or len(name) > 256) or
                predicted is not None and not isinstance(predicted, str)):
            raise MeshInventoryError("Blender source mapping is malformed")
        mapped = status == "SDK_PATH_RECONSTRUCTED"
        if mapped != bool(name and predicted == gap["path"]):
            raise MeshInventoryError("Blender source mapping contradicts path")
        if mapped:
            if name in mapped_objects:
                raise MeshInventoryError("one source mesh maps to multiple gaps")
            mapped_objects.add(name)
            facts = _validate_facts(row.get("facts"))
            findings = _gap_findings(gap, facts)
        else:
            if row.get("facts") is not None:
                raise MeshInventoryError("unmapped path has source facts")
            facts = None
            findings = None
        interpreted.append({
            "path": gap["path"], "sourceObject": name,
            "predictedSdkPath": predicted, "mappingStatus": status,
            "parentObject": row.get("parentObject"),
            "parentBone": row.get("parentBone"),
            "parentType": row.get("parentType"),
            "sourceVisible": row.get("sourceVisible"),
            "sourceFacts": facts, "gapFindings": findings,
        })
    digest = hashlib.sha256(_canonical(interpreted)).hexdigest()
    compact = {key: result[key] for key in expected}
    compact.update({
        "status": "SOURCE_GAP_INVENTORY",
        "blenderVersion": result["blenderVersion"],
        "mappedGapRows": len(mapped_objects),
        "unmappedGapRows": len(gap_rows) - len(mapped_objects),
        "rawVsEvaluatedTriangleCountChangedRows": sum(
            row["sourceFacts"] is not None and
            row["sourceFacts"]["rawTriangles"] !=
            row["sourceFacts"]["evaluatedTriangles"] for row in interpreted),
        "rawVsEvaluatedVertexCountChangedRows": sum(
            row["sourceFacts"] is not None and
            row["sourceFacts"]["rawVertices"] !=
            row["sourceFacts"]["evaluatedVertices"] for row in interpreted),
        "weightedRawVerticesBelowRawRows": sum(
            row["sourceFacts"] is not None and
            row["sourceFacts"]["weightedRawVertices"] <
            row["sourceFacts"]["rawVertices"] for row in interpreted),
        "firstArmatureTargetMatchesSourceRows": sum(
            row["sourceFacts"] is not None and
            row["sourceFacts"]["firstArmatureTarget"] == "D11T_Rig.005"
            for row in interpreted),
        "repairedOnlyMaterialLabelsAbsentFromSourceRows": sum(
            bool(row["gapFindings"] and row["gapFindings"]
                 ["repairedOnlyLabelsAbsentFromSource"]) for row in interpreted),
        "rowsDigestSha256": digest,
        "rows": interpreted,
    })
    if len(_canonical(compact)) > MAX_JSON_BYTES:
        raise MeshInventoryError("bounded source inventory output exceeded")
    return compact


def parse_result(stdout: str, gap_rows: list[dict],
                 expected_blender_sha256: str) -> dict:
    matches = [line[len(RESULT_PREFIX):] for line in stdout.splitlines()
               if line.startswith(RESULT_PREFIX)]
    if len(matches) != 1 or len(matches[0]) > MAX_JSON_BYTES:
        raise MeshInventoryError("Blender did not emit one bounded readback")
    try:
        result = json.loads(matches[0])
    except json.JSONDecodeError as exc:
        raise MeshInventoryError("Blender readback is malformed") from exc
    if not isinstance(result, dict):
        raise MeshInventoryError("Blender readback is not an object")
    return interpret_readback(result, gap_rows, expected_blender_sha256)


def run_probe(*, registry_path: Path, blender_executable: Path,
              sdk_script_root: Path, timeout_seconds: int = 300) -> dict:
    if type(timeout_seconds) is not int or timeout_seconds < 1:
        raise MeshInventoryError("timeout must be a positive integer")
    registry = _unlinked_path(registry_path, "registry")
    registry_sha = file_sha256(registry)
    config = json.loads(registry.read_text(encoding="utf-8"))
    inventory_ref = config["accepted"]["authoringInventory"]
    if inventory_ref["sha256"] != INVENTORY_SHA256:
        raise MeshInventoryError("accepted authoring inventory pin differs")
    inventory_raw = registry.parent / inventory_ref["path"]
    inventory_path = _unlinked_path(inventory_raw, "authoring inventory")
    if not inventory_path.is_relative_to(registry.parent):
        raise MeshInventoryError("authoring inventory is outside registry checkout")
    _, source_root, asset_row, blend, usf = _pinned_asset(
        inventory_path, INVENTORY_SHA256, "cat_d11t")
    require_hash(blend, BLEND_SHA256, "source Blend")
    require_hash(usf, USF_SHA256, "repaired USF")
    worklist = require_hash(WORKLIST, WORKLIST_SHA256,
                            "reconstruction worklist")
    gap_rows = _worklist_rows(json.loads(worklist.read_text(encoding="utf-8")),
                              asset_row["assetDigest"])
    blender = _unlinked_path(blender_executable, "Blender executable")
    blender_sha = file_sha256(blender)
    if blender_sha not in BLENDER_VERSION_PINS:
        raise MeshInventoryError("Blender executable differs from reviewed pins")
    require_hash(blender, blender_sha, "Blender executable")
    sdk = require_sdk_pins(sdk_script_root)
    worker = require_hash(WORKER, WORKER_SHA256, "mesh inventory worker")
    command = [str(blender), "--background", "--factory-startup",
               "--disable-autoexec", "--threads", "1", "--python-exit-code", "1",
               "--python", str(worker), "--", "--blend", str(blend),
               "--repaired-usf", str(usf), "--worklist", str(worklist),
               "--sdk-script-root", str(sdk), "--worker-sha256", WORKER_SHA256,
               "--blender-sha256", blender_sha]
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(command, capture_output=True, text=True,
                               errors="replace", timeout=timeout_seconds,
                               env=environment, check=False,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if completed.returncode != 0:
        tail = "\n".join((completed.stdout + completed.stderr).splitlines()[-12:])
        raise MeshInventoryError(f"Blender exited {completed.returncode}: {tail}")
    result = parse_result(completed.stdout, gap_rows, blender_sha)
    require_hash(registry, registry_sha, "registry after readback")
    require_hash(inventory_path, INVENTORY_SHA256,
                 "authoring inventory after readback")
    require_hash(blend, BLEND_SHA256, "source Blend after readback")
    require_hash(usf, USF_SHA256, "repaired USF after readback")
    require_hash(WORKLIST, WORKLIST_SHA256, "reconstruction worklist after readback")
    require_sdk_pins(sdk)
    require_hash(blender, blender_sha, "Blender executable after readback")
    require_hash(WORKER, WORKER_SHA256, "mesh inventory worker after readback")
    if _unlinked_path(Path(json.loads(inventory_path.read_text(encoding="utf-8"))
                           ["sourceRoot"]), "source root after readback") != source_root:
        raise MeshInventoryError("source root changed during readback")
    result.update({"sourceUnchanged": True, "sdkUnchanged": True,
                   "workerSha256": WORKER_SHA256,
                   "inventorySha256": INVENTORY_SHA256,
                   "worklistSha256": WORKLIST_SHA256})
    if len(_canonical(result)) > MAX_JSON_BYTES:
        raise MeshInventoryError("bounded source inventory output exceeded")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path,
                        default=TOOLCHAIN_ROOT / "project.json")
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    args = parser.parse_args(argv)
    try:
        result = run_probe(registry_path=args.registry,
                           blender_executable=args.blender,
                           sdk_script_root=args.sdk_script_root,
                           timeout_seconds=args.timeout_seconds)
    except (MeshInventoryError, LeftPushProbeError, BlenderAuthoringError,
            OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"schemaVersion": 1, "status": "ERROR",
                          "error": str(exc),
                          "nativeBlendExportApproved": False}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
