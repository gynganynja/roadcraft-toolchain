"""Pinned, no-save readback of the 60 relocated D11 blade collision meshes.

The historical Blend and two retained USFs are inspected only. A common leaf
name or matching count/matrix is diagnostic evidence, not node equivalence or
permission to use the native-Blend export route.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys

from .blender_armature_parity import BLENDER_VERSION_PINS
from .blender_authoring import BlenderAuthoringError, _pinned_asset
from .blender_left_push_probe import (
    BLEND_SHA256, INVENTORY_SHA256, LeftPushProbeError, USF_SHA256,
    _unlinked_path, require_hash, require_sdk_pins,
)
from .blender_mesh_inventory import WORKLIST_SHA256
from .source import file_sha256


TOOLCHAIN_ROOT = Path(__file__).resolve().parents[2]
WORKLIST = TOOLCHAIN_ROOT / "operations/d11_blender_reconstruction_worklist_20260928.json"
WORKER = Path(__file__).with_name("blender_blade_relocation_worker.py")
WORKER_SHA256 = "f8edd2fb82f3264386fd262541e3e686b7389206c71acbb0fcfb5a0d1fd1c6a7"
RESULT_PREFIX = "ROADCRAFT_BLADE_RELOCATION "
LEAVES = tuple(f"cdt_blade_{number}" for number in range(60))
NATIVE_PARENT = "|@root|D11T_Rig.005|BoneChassis_cdt|BoneBladeLift_cdt|BoneBlade_cdt"
REPAIRED_PARENT = ("|@root|D11T_Rig.005|BoneChassis_cdt|BoneBladeLift_cdt|"
                   "BoneBladeRoll_cdt|BoneBlade_cdt")
MAX_JSON_BYTES = 256 * 1024
MESH_FIELDS = ("vertices", "faces", "normals", "materialSlots", "uvSets",
               "colorSets", "skinEntries", "skinBones")
SOURCE_FIELDS = ("rawVertices", "rawPolygons", "rawTriangles",
                 "evaluatedVertices", "evaluatedTriangles", "materialSlots",
                 "uvSets", "colorSets", "vertexGroups", "armatureModifiers")


class BladeRelocationError(RuntimeError):
    """Pinned input or complete readback did not satisfy this diagnostic."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _rows_and_native(worklist: dict, source_asset_digest: str,
                     blend: Path, repaired: Path) -> tuple[list[dict], Path, str, Path, str]:
    if (worklist.get("schemaVersion") != 1 or
            worklist.get("status") != "RECONSTRUCTION_REQUIRED" or
            worklist.get("nativeBlendExportApproved") is not False or
            worklist.get("inventorySha256") != INVENTORY_SHA256):
        raise BladeRelocationError("worklist identity or blocked gate differs")
    matches = [a for a in worklist.get("assets", []) if a.get("asset") == "cat_d11t"]
    if len(matches) != 1:
        raise BladeRelocationError("worklist has no unique base asset")
    asset = matches[0]
    if (asset.get("sourceAssetDigest") != source_asset_digest or
            asset.get("blendSha256") != BLEND_SHA256 or
            asset.get("repairedUsfSha256") != USF_SHA256 or
            asset.get("nativeBlendExportApproved") is not False):
        raise BladeRelocationError("worklist base pins differ")
    candidates = asset["findings"]["pathRelocationCandidates"]
    if not isinstance(candidates, list) or len(candidates) != 66:
        raise BladeRelocationError("worklist relocation coverage differs")
    rows = [row for row in candidates if row.get("leafName") in LEAVES]
    by_leaf = {row["leafName"]: row for row in rows}
    if len(rows) != len(by_leaf) or set(by_leaf) != set(LEAVES):
        raise BladeRelocationError("blade relocation coverage differs")
    for leaf, row in by_leaf.items():
        if (row.get("nativeExportPath") != NATIVE_PARENT + "|" + leaf or
                row.get("repairedPath") != REPAIRED_PARENT + "|" + leaf or
                row.get("equivalenceVerified") is not False):
            raise BladeRelocationError(f"unreviewed blade path or equivalence: {leaf}")
    summary_path = require_hash(Path(asset["summaryPath"]),
                                asset["summarySha256"], "base parity summary")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    native_sha = asset["scratchNativeUsfSha256"]
    if (summary.get("asset") != "cat_d11t" or
            summary.get("nativeBlendExportApproved") is not False or
            summary.get("blendSha256") != BLEND_SHA256 or
            summary.get("baselineUsfSha256") != USF_SHA256 or
            summary.get("candidateUsfSha256") != native_sha or
            summary.get("baselineRootName") != "cat_d11t" or
            summary.get("candidateRootName") != "cat_d11t" or
            Path(summary["blendPath"]) != blend or
            Path(summary["baselineUsfPath"]) != repaired):
        raise BladeRelocationError("retained native export summary differs")
    native_path = require_hash(Path(summary["candidateUsfPath"]), native_sha,
                               "retained scratch native USF")
    return ([by_leaf[leaf] for leaf in LEAVES], native_path, native_sha,
            summary_path, asset["summarySha256"])


def _matrix(value: object, label: str) -> list[float]:
    if (not isinstance(value, list) or len(value) != 16 or
            any(type(element) not in (float, int) or not math.isfinite(element)
                for element in value)):
        raise BladeRelocationError(f"{label} is not a finite 4x4 matrix")
    return [float(element) for element in value]


def _counts(value: object, fields: tuple[str, ...], label: str) -> dict:
    if (not isinstance(value, dict) or set(value) != set(fields) or
            any(type(value[name]) is not int or value[name] < 0 for name in fields)):
        raise BladeRelocationError(f"{label} counts are incomplete")
    return value


def interpret_readback(result: dict, expected_rows: list[dict],
                       blender_sha: str, native_sha: str,
                       summary_sha: str) -> dict:
    expected = {
        "schemaVersion": 1, "asset": "cat_d11t",
        "blendSha256": BLEND_SHA256, "repairedUsfSha256": USF_SHA256,
        "nativeExportUsfSha256": native_sha,
        "worklistSha256": WORKLIST_SHA256, "summarySha256": summary_sha,
        "blenderSha256": blender_sha, "sceneFrame": 1,
        "sourceSceneMeshCount": 210,
        "nativeExportRootName": "cat_d11t", "repairedRootName": "cat_d11t",
        "blendSaved": False, "usfExported": False,
        "nativeBlendExportApproved": False,
    }
    if not isinstance(result, dict) or any(
            type(result.get(key)) is not type(value) or result.get(key) != value
            for key, value in expected.items()):
        raise BladeRelocationError("readback identity, coverage or no-write fields differ")
    if (blender_sha not in BLENDER_VERSION_PINS or
            not isinstance(result.get("blenderVersion"), str) or
            not result["blenderVersion"].startswith(BLENDER_VERSION_PINS[blender_sha])):
        raise BladeRelocationError("Blender version differs")
    rows = result.get("rows")
    if not isinstance(rows, list) or len(rows) != 60:
        raise BladeRelocationError("readback omitted blade relocation rows")
    compared = []
    for row, evidence in zip(rows, expected_rows):
        leaf = evidence["leafName"]
        if (not isinstance(row, dict) or row.get("leafName") != leaf or
                row.get("nativeExportPath") != evidence["nativeExportPath"] or
                row.get("repairedPath") != evidence["repairedPath"] or
                row.get("equivalenceVerified") is not False):
            raise BladeRelocationError(f"readback path or gate differs: {leaf}")
        source = row.get("source")
        native = row.get("nativeExportNode")
        repaired = row.get("repairedNode")
        if (not isinstance(source, dict) or
                source.get("objectName") != leaf or source.get("objectType") != "MESH" or
                source.get("parentObject") != "D11T_Rig.005" or
                source.get("parentType") != "BONE" or
                source.get("parentBone") != "BoneBlade_cdt" or
                source.get("sourcePredictedPath") != evidence["nativeExportPath"] or
                source.get("visible") is not True):
            raise BladeRelocationError(f"source hierarchy differs: {leaf}")
        _counts(source.get("mesh"), SOURCE_FIELDS, f"source {leaf}")
        if (source["mesh"]["evaluatedTriangles"] !=
                source["mesh"]["rawTriangles"]):
            # A changed evaluated mesh would need a more detailed SDK review.
            raise BladeRelocationError(f"source evaluation changed triangles: {leaf}")
        source_matrix = _matrix(source.get("worldMatrixSaber"), f"source {leaf}")
        for label, node, path in (("native", native, evidence["nativeExportPath"]),
                                  ("repaired", repaired, evidence["repairedPath"])):
            if not isinstance(node, dict) or node.get("path") != path:
                raise BladeRelocationError(f"{label} node path differs: {leaf}")
            _counts(node.get("mesh"), MESH_FIELDS, f"{label} {leaf}")
            _matrix(node.get("worldMatrixSaber"), f"{label} {leaf}")
            _matrix(node.get("localMatrixSaber"), f"{label} local {leaf}")
        native_matrix = native["worldMatrixSaber"]
        repaired_matrix = repaired["worldMatrixSaber"]
        native_local = native["localMatrixSaber"]
        repaired_local = repaired["localMatrixSaber"]
        compared.append({
            **row,
            "sourceNativeWorldMaxElementError": max(
                abs(a - b) for a, b in zip(source_matrix, native_matrix)),
            "sourceRepairedWorldMaxElementError": max(
                abs(a - b) for a, b in zip(source_matrix, repaired_matrix)),
            "nativeRepairedWorldMaxElementError": max(
                abs(a - b) for a, b in zip(native_matrix, repaired_matrix)),
            "nativeRepairedLocalMaxElementError": max(
                abs(a - b) for a, b in zip(native_local, repaired_local)),
        })
    compact = {key: result[key] for key in expected}
    compact.update({
        "status": "SOURCE_BLADE_RELOCATION_INVENTORY",
        "blenderVersion": result["blenderVersion"],
        "relocationRows": len(compared),
        "rowsDigestSha256": hashlib.sha256(_canonical(compared)).hexdigest(),
        "rows": compared,
    })
    if len(_canonical(compact)) > MAX_JSON_BYTES:
        raise BladeRelocationError("bounded relocation result exceeded")
    return compact


def parse_result(stdout: str, rows: list[dict], blender_sha: str,
                 native_sha: str, summary_sha: str) -> dict:
    matches = [line[len(RESULT_PREFIX):] for line in stdout.splitlines()
               if line.startswith(RESULT_PREFIX)]
    if len(matches) != 1 or len(matches[0]) > MAX_JSON_BYTES:
        raise BladeRelocationError("Blender did not emit one bounded readback")
    try:
        raw = json.loads(matches[0])
    except json.JSONDecodeError as exc:
        raise BladeRelocationError("Blender readback is malformed") from exc
    return interpret_readback(raw, rows, blender_sha, native_sha, summary_sha)


def run_probe(*, registry_path: Path, blender_executable: Path,
              sdk_script_root: Path, timeout_seconds: int = 600) -> dict:
    if type(timeout_seconds) is not int or timeout_seconds < 1:
        raise BladeRelocationError("timeout must be a positive integer")
    registry = _unlinked_path(registry_path, "registry")
    registry_sha = file_sha256(registry)
    config = json.loads(registry.read_text(encoding="utf-8"))
    inventory_ref = config["accepted"]["authoringInventory"]
    if inventory_ref["sha256"] != INVENTORY_SHA256:
        raise BladeRelocationError("accepted authoring inventory pin differs")
    inventory_path = _unlinked_path(registry.parent / inventory_ref["path"],
                                    "authoring inventory")
    if not inventory_path.is_relative_to(registry.parent):
        raise BladeRelocationError("authoring inventory is outside checkout")
    inventory, source_root, asset, blend, repaired = _pinned_asset(
        inventory_path, INVENTORY_SHA256, "cat_d11t")
    require_hash(blend, BLEND_SHA256, "source Blend")
    require_hash(repaired, USF_SHA256, "repaired USF")
    worklist = require_hash(WORKLIST, WORKLIST_SHA256, "reconstruction worklist")
    rows, native, native_sha, summary_path, summary_sha = _rows_and_native(
        json.loads(worklist.read_text(encoding="utf-8")), asset["assetDigest"],
        blend, repaired)
    blender = _unlinked_path(blender_executable, "Blender executable")
    blender_sha = file_sha256(blender)
    if blender_sha not in BLENDER_VERSION_PINS:
        raise BladeRelocationError("Blender executable differs from reviewed pins")
    require_hash(blender, blender_sha, "Blender executable")
    sdk = require_sdk_pins(sdk_script_root)
    worker = require_hash(WORKER, WORKER_SHA256, "blade relocation worker")
    command = [str(blender), "--background", "--factory-startup",
               "--disable-autoexec", "--threads", "1", "--python-exit-code", "1",
               "--python", str(worker), "--", "--blend", str(blend),
               "--repaired-usf", str(repaired), "--native-usf", str(native),
               "--worklist", str(worklist), "--sdk-script-root", str(sdk),
               "--worker-sha256", WORKER_SHA256, "--blender-sha256", blender_sha,
               "--native-usf-sha256", native_sha, "--summary-sha256", summary_sha]
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(command, capture_output=True, text=True,
                               errors="replace", timeout=timeout_seconds,
                               env=environment, check=False,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if completed.returncode != 0:
        tail = "\n".join((completed.stdout + completed.stderr).splitlines()[-12:])
        raise BladeRelocationError(f"Blender exited {completed.returncode}: {tail}")
    result = parse_result(completed.stdout, rows, blender_sha, native_sha, summary_sha)
    require_hash(registry, registry_sha, "registry after readback")
    require_hash(inventory_path, INVENTORY_SHA256, "authoring inventory after readback")
    if _unlinked_path(Path(inventory["sourceRoot"]),
                      "source root after readback") != source_root:
        raise BladeRelocationError("source root changed during readback")
    require_hash(blend, BLEND_SHA256, "source Blend after readback")
    require_hash(repaired, USF_SHA256, "repaired USF after readback")
    require_hash(native, native_sha, "retained native USF after readback")
    require_hash(worklist, WORKLIST_SHA256, "worklist after readback")
    require_hash(summary_path, summary_sha, "parity summary after readback")
    require_sdk_pins(sdk)
    require_hash(blender, blender_sha, "Blender executable after readback")
    require_hash(worker, WORKER_SHA256, "worker after readback")
    result.update({"sourceUnchanged": True, "sdkUnchanged": True,
                   "nativeExportUnchanged": True,
                   "workerSha256": WORKER_SHA256,
                   "inventorySha256": INVENTORY_SHA256})
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=TOOLCHAIN_ROOT / "project.json")
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args(argv)
    try:
        result = run_probe(registry_path=args.registry,
                           blender_executable=args.blender,
                           sdk_script_root=args.sdk_script_root,
                           timeout_seconds=args.timeout_seconds)
    except (BladeRelocationError, LeftPushProbeError, BlenderAuthoringError,
            OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"schemaVersion": 1, "status": "ERROR", "error": str(exc),
                          "nativeBlendExportApproved": False}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
