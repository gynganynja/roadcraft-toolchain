"""Pinned, no-save D11 v2/v3 source/native/repaired material readback.

Each variant opens its own accepted Blend path and parses its own repaired and
retained native USFs. No base-asset result is reused as variant evidence.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from . import blender_material_payload as base
from . import blender_mesh_variant_inventory as variant
from .blender_authoring import BlenderAuthoringError
from .blender_left_push_probe import (
    INVENTORY_SHA256, LeftPushProbeError, _unlinked_path, require_hash,
    require_sdk_pins,
)
from .blender_mesh_inventory import BLENDER_VERSION_PINS, WORKLIST, WORKLIST_SHA256
from .source import file_sha256


BASE_MATERIAL_HOST_SHA256 = "681f70389f424e342d66d9f3bd392d59ca1d9c33368a0c3106decda692f39ad7"
VARIANT_INVENTORY_HOST_SHA256 = "4f0bc0b0dc8312d147b654f95b63b361e3c84c180f807565b6a2bbb06ab073c0"
WORKER = Path(__file__).with_name("blender_material_variant_payload_worker.py")
WORKER_SHA256 = "74fe12860d15bf7d6237b40945aec79decff23a865031121707863f68545d2a0"
RESULT_PREFIX = "ROADCRAFT_VARIANT_MATERIAL_PAYLOAD "
ASSET_PINS = {
    "cat_d11t_v2": {
        **variant.ASSET_PINS["cat_d11t_v2"],
        "nativeUsfSha256": "0e533bbc80a95798824e69e5c6545cc50b9d98f0ba81e7f0e96d9e3a93c2dc3f",
        "summarySha256": "ffcc6bb774911f0f1e7a1d865cb2b113f88305a07a2e4aef2f4e5aff07814dc0",
    },
    "cat_d11t_v3": {
        **variant.ASSET_PINS["cat_d11t_v3"],
        "nativeUsfSha256": "bdd562bafeef47644e998cad413e246f10ff0d13bf172cf18d75cdf032e6cc13",
        "summarySha256": "c7d28c2f630eadd51cb042150c3162c4f5da811d02e59897e9c0314d6ae058a0",
    },
}


class VariantMaterialPayloadError(RuntimeError):
    """A variant source or material readback fails a reviewed pin or gate."""


def _pins(asset_name: str) -> dict[str, str]:
    try:
        return ASSET_PINS[asset_name]
    except (KeyError, TypeError) as exc:
        raise VariantMaterialPayloadError("asset is outside the v2/v3 allowlist") from exc


def _inputs(registry_path: Path, asset_name: str) -> dict:
    pins = _pins(asset_name)
    require_hash(Path(base.__file__), BASE_MATERIAL_HOST_SHA256,
                 "base material comparison host")
    require_hash(Path(variant.__file__), VARIANT_INVENTORY_HOST_SHA256,
                 "variant inventory host")
    accepted = variant._variant_inputs(registry_path, asset_name)
    worklist = require_hash(WORKLIST, WORKLIST_SHA256, "reconstruction worklist")
    data = json.loads(worklist.read_text(encoding="utf-8"))
    candidates = [row for row in data["assets"] if row.get("asset") == asset_name]
    if len(candidates) != 1:
        raise VariantMaterialPayloadError("worklist variant is not unique")
    row = candidates[0]
    if (row.get("sourceAssetDigest") != pins["sourceAssetDigest"] or
            row.get("blendSha256") != pins["blendSha256"] or
            row.get("repairedUsfSha256") != pins["repairedUsfSha256"] or
            row.get("scratchNativeUsfSha256") != pins["nativeUsfSha256"] or
            row.get("summarySha256") != pins["summarySha256"] or
            row.get("nativeExportRootName") != asset_name or
            row.get("repairedRootName") != "cat_d11t" or
            row.get("nativeBlendExportApproved") is not False):
        raise VariantMaterialPayloadError("variant worklist material inputs differ")
    summary = _unlinked_path(Path(row["summaryPath"]), "variant parity summary")
    require_hash(summary, pins["summarySha256"], "variant parity summary")
    summary_data = json.loads(summary.read_text(encoding="utf-8"))
    if (summary_data.get("asset") != asset_name or
            summary_data.get("sourceAssetDigest") != pins["sourceAssetDigest"] or
            summary_data.get("candidateUsfSha256") != pins["nativeUsfSha256"] or
            summary_data.get("nativeBlendExportApproved") is not False):
        raise VariantMaterialPayloadError("variant parity summary identity differs")
    native = _unlinked_path(Path(summary_data["candidateUsfPath"]),
                            "variant retained native USF")
    require_hash(native, pins["nativeUsfSha256"], "variant retained native USF")
    return {**accepted, "worklist": worklist, "summary": summary,
            "native": native, "summarySha256": pins["summarySha256"],
            "nativeUsfSha256": pins["nativeUsfSha256"]}


def interpret_readback(result: dict, gap_rows: list[dict], asset_name: str,
                       blender_sha: str, host_sha: str) -> dict:
    pins = _pins(asset_name)
    expected = {
        "schemaVersion": 1, "asset": asset_name,
        "sourceAssetDigest": pins["sourceAssetDigest"],
        "blendSha256": pins["blendSha256"],
        "repairedUsfSha256": pins["repairedUsfSha256"],
        "nativeExportUsfSha256": pins["nativeUsfSha256"],
        "summarySha256": pins["summarySha256"],
        "worklistSha256": WORKLIST_SHA256,
        "blenderSha256": blender_sha, "hostSha256": host_sha,
        "baseMaterialHostSha256": BASE_MATERIAL_HOST_SHA256,
        "mapperWorkerSha256": base.MAPPER_WORKER_SHA256,
        "sceneFrame": 1, "sourceSceneMeshCount": 210,
        "nativeExportRootName": asset_name,
        "repairedUsfRootName": "cat_d11t",
        "blendSaved": False, "usfExported": False,
        "nativeBlendExportApproved": False,
    }
    if not isinstance(result, dict) or any(
            type(result.get(key)) is not type(value) or result.get(key) != value
            for key, value in expected.items()):
        raise VariantMaterialPayloadError("variant identity or no-write fields differ")
    if (blender_sha not in BLENDER_VERSION_PINS or
            not isinstance(result.get("blenderVersion"), str) or
            not result["blenderVersion"].startswith(BLENDER_VERSION_PINS[blender_sha])):
        raise VariantMaterialPayloadError("variant Blender version differs")
    rows = result.get("rows")
    if not isinstance(rows, list) or len(rows) != len(gap_rows) or len(rows) != 126:
        raise VariantMaterialPayloadError("variant material row coverage differs")
    seen = set()
    summary = {
        "sourceNativeExactMaterialRows": 0,
        "sourceNativeOrderedNameRows": 0,
        "sourceNativeTextureReferenceRows": 0,
        "sourceNativeFaceMappingRows": 0,
        "sourceRepairedExactMaterialRows": 0,
        "sourceRepairedFaceMappingRows": 0,
        "repairedOnlyMaterialLabelOccurrences": 0,
        "sourceSlots": 0, "nativeSlots": 0, "repairedSlots": 0,
    }
    for row, gap in zip(rows, gap_rows):
        if (not isinstance(row, dict) or set(row) != {
                "path", "sourceObject", "source", "native", "repaired"} or
                row["path"] != gap["path"] or
                not isinstance(row["sourceObject"], str) or
                row["sourceObject"] in seen):
            raise VariantMaterialPayloadError("variant path or object mapping differs")
        seen.add(row["sourceObject"])
        source, native, repaired = (base._validate_summary(row[key]) for key in
                                    ("source", "native", "repaired"))
        summary["sourceNativeExactMaterialRows"] += source["slots"] == native["slots"]
        summary["sourceNativeOrderedNameRows"] += (
            [slot["name"] for slot in source["slots"]] ==
            [slot["name"] for slot in native["slots"]])
        summary["sourceNativeTextureReferenceRows"] += (
            [slot["textureReferences"] for slot in source["slots"]] ==
            [slot["textureReferences"] for slot in native["slots"]])
        summary["sourceNativeFaceMappingRows"] += (
            source["faceMaterialIndices"] == native["faceMaterialIndices"])
        summary["sourceRepairedExactMaterialRows"] += source["slots"] == repaired["slots"]
        summary["sourceRepairedFaceMappingRows"] += (
            source["faceMaterialIndices"] == repaired["faceMaterialIndices"])
        summary["repairedOnlyMaterialLabelOccurrences"] += len(
            base._missing_names(source, repaired))
        for key, value in (("sourceSlots", source), ("nativeSlots", native),
                           ("repairedSlots", repaired)):
            summary[key] += value["slotCount"]
    compact = {key: result[key] for key in expected}
    compact.update({
        "status": "SOURCE_NATIVE_VARIANT_MATERIAL_PAYLOAD_READBACK",
        "blenderVersion": result["blenderVersion"], "mappedRows": len(rows),
        **summary, "rowsDigestSha256": base._sha(rows),
        "textureBytesCompared": False,
        "shaderGraphSemanticsCompared": False,
        "rows": rows,
    })
    if len(base._canonical(compact)) > base.MAX_JSON_BYTES:
        raise VariantMaterialPayloadError("bounded variant material result exceeded")
    return compact


def parse_result(stdout: str, gap_rows: list[dict], asset_name: str,
                 blender_sha: str, host_sha: str) -> dict:
    matches = [line[len(RESULT_PREFIX):] for line in stdout.splitlines()
               if line.startswith(RESULT_PREFIX)]
    if len(matches) != 1 or len(matches[0].encode("utf-8")) > base.MAX_JSON_BYTES:
        raise VariantMaterialPayloadError("Blender emitted no unique bounded readback")
    try:
        raw = json.loads(matches[0])
    except json.JSONDecodeError as exc:
        raise VariantMaterialPayloadError("variant material JSON is malformed") from exc
    return interpret_readback(raw, gap_rows, asset_name, blender_sha, host_sha)


def run_probe(*, registry_path: Path, blender_executable: Path,
              sdk_script_root: Path, asset_name: str,
              timeout_seconds: int = 900) -> dict:
    if type(timeout_seconds) is not int or timeout_seconds < 1:
        raise VariantMaterialPayloadError("timeout must be a positive integer")
    before = _inputs(registry_path, asset_name)
    pins = _pins(asset_name)
    blender = _unlinked_path(blender_executable, "Blender executable")
    blender_sha = file_sha256(blender)
    if blender_sha not in BLENDER_VERSION_PINS:
        raise VariantMaterialPayloadError("Blender executable differs from reviewed pins")
    require_hash(blender, blender_sha, "Blender executable")
    sdk = require_sdk_pins(sdk_script_root)
    mapper_worker = require_hash(base.MAPPER_WORKER, base.MAPPER_WORKER_SHA256,
                                 "mapped path worker")
    worker = require_hash(WORKER, WORKER_SHA256, "variant material worker")
    host_sha = file_sha256(Path(__file__))
    command = [str(blender), "--background", "--factory-startup",
               "--disable-autoexec", "--threads", "1", "--python-exit-code", "1",
               "--python", str(worker), "--", "--asset", asset_name,
               "--blend", str(before["blend"]),
               "--repaired-usf", str(before["usf"]),
               "--native-usf", str(before["native"]),
               "--worklist", str(before["worklist"]),
               "--summary", str(before["summary"]),
               "--sdk-script-root", str(sdk),
               "--worker-sha256", WORKER_SHA256,
               "--mapper-sha256", base.MAPPER_WORKER_SHA256,
               "--host-sha256", host_sha,
               "--blender-sha256", blender_sha]
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(command, capture_output=True, text=True,
                               errors="replace", timeout=timeout_seconds,
                               env=environment, check=False,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if completed.returncode != 0:
        tail = "\n".join((completed.stdout + completed.stderr).splitlines()[-12:])
        raise VariantMaterialPayloadError(f"Blender exited {completed.returncode}: {tail}")
    result = parse_result(completed.stdout, before["gapRows"],
                          asset_name, blender_sha, host_sha)
    after = _inputs(registry_path, asset_name)
    if any(before[key] != after[key] for key in (
            "registrySha256", "sourceRoot", "blend", "usf", "gapRows",
            "worklist", "summary", "native", "summarySha256", "nativeUsfSha256")):
        raise VariantMaterialPayloadError("variant inputs changed during readback")
    for path, digest, label in (
            (before["blend"], pins["blendSha256"], "variant Blend"),
            (before["usf"], pins["repairedUsfSha256"], "variant repaired USF"),
            (before["native"], pins["nativeUsfSha256"], "variant native USF"),
            (before["summary"], pins["summarySha256"], "variant summary"),
            (blender, blender_sha, "Blender executable"),
            (mapper_worker, base.MAPPER_WORKER_SHA256, "mapper worker"),
            (worker, WORKER_SHA256, "variant material worker"),
            (Path(__file__), host_sha, "variant material host")):
        require_hash(path, digest, label + " after readback")
    require_sdk_pins(sdk)
    result.update({
        "sourceUnchanged": True, "sdkUnchanged": True,
        "nativeExportUnchanged": True, "repairedUsfUnchanged": True,
        "inventorySha256": INVENTORY_SHA256,
        "workerSha256": WORKER_SHA256,
    })
    if len(base._canonical(result)) > base.MAX_JSON_BYTES:
        raise VariantMaterialPayloadError("bounded final variant result exceeded")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", choices=tuple(ASSET_PINS), required=True)
    parser.add_argument("--registry", type=Path,
                        default=base.TOOLCHAIN_ROOT / "project.json")
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args(argv)
    try:
        result = run_probe(registry_path=args.registry,
                           blender_executable=args.blender,
                           sdk_script_root=args.sdk_script_root,
                           asset_name=args.asset,
                           timeout_seconds=args.timeout_seconds)
    except (VariantMaterialPayloadError, variant.VariantMeshInventoryError,
            base.MaterialPayloadError, LeftPushProbeError, BlenderAuthoringError,
            OSError, ValueError, KeyError, TypeError,
            subprocess.TimeoutExpired) as exc:
        print(json.dumps({"schemaVersion": 1, "status": "ERROR",
                          "error": str(exc),
                          "nativeBlendExportApproved": False}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
