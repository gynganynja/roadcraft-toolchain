"""Pinned, no-save D11 v2/v3 mesh payload readback.

Each run opens one accepted variant Blend and compares its in-memory Saber SDK
projection with that variant's own retained native and repaired USFs. It does
not export a USF or approve the native-Blend build route.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

from . import blender_mesh_payload as base
from . import blender_mesh_variant_inventory as variant
from .blender_authoring import BlenderAuthoringError
from .blender_left_push_probe import (
    INVENTORY_SHA256, LeftPushProbeError, _unlinked_path, require_hash,
    require_sdk_pins,
)
from .blender_mesh_inventory import BLENDER_VERSION_PINS, WORKLIST, WORKLIST_SHA256
from .source import file_sha256


BASE_MESH_HOST_SHA256 = "2ec3051322517d68b07c99bd94710402bb32d2157e540996814e66e5925a1a4e"
VARIANT_INVENTORY_HOST_SHA256 = "4f0bc0b0dc8312d147b654f95b63b361e3c84c180f807565b6a2bbb06ab073c0"
WORKER = Path(__file__).with_name("blender_mesh_variant_payload_worker.py")
WORKER_SHA256 = "cfef0c5e5cdc6ed033c704a769b0c53d466bd1f79b77746343472f50f786bda0"
RESULT_PREFIX = "ROADCRAFT_VARIANT_MESH_PAYLOAD "
MAX_JSON_BYTES = 768 * 1024
COLOR_DETAIL_PATH = "|@root|D11T_Rig.005|Ripper_vis|Ripper_vis_LOD2"
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


class VariantMeshPayloadError(RuntimeError):
    """Variant source, native USF, repaired USF, or mesh readback differs."""


def _pins(asset_name: str) -> dict[str, str]:
    try:
        return ASSET_PINS[asset_name]
    except (KeyError, TypeError) as exc:
        raise VariantMeshPayloadError("asset is outside the v2/v3 allowlist") from exc


def _color_summary(values: list[list[int]]) -> dict:
    if not isinstance(values, list) or len(values) > 32:
        raise VariantMeshPayloadError("invalid color-set coverage")
    digest = hashlib.sha256()
    digest.update(struct.pack("<Q", len(values)))
    entries = 0
    for colors in values:
        if not isinstance(colors, list) or len(colors) > 10_000_000:
            raise VariantMeshPayloadError("invalid color-array coverage")
        digest.update(struct.pack("<Q", len(colors)))
        entries += len(colors)
        for value in colors:
            if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
                raise VariantMeshPayloadError("invalid packed color")
            digest.update(struct.pack("<I", value))
    return {"elements": entries, "sets": len(values), "sha256": digest.hexdigest()}


def summarize_color_detail(source_sets: list[list[int]],
                           native_sets: list[list[int]],
                           path: str = COLOR_DETAIL_PATH) -> dict:
    """Bound raw packed-color values for one exact mapped mesh path."""
    if not isinstance(path, str) or not path.startswith("|@root|") or len(path) > 512:
        raise VariantMeshPayloadError("invalid color detail path")
    source = _color_summary(source_sets)
    native = _color_summary(native_sets)
    if (source["sets"] != native["sets"] or
            any(len(a) != len(b) for a, b in zip(source_sets, native_sets))):
        raise VariantMeshPayloadError("target color arrays have different shapes")
    first = []
    different = 0
    for set_index, (left, right) in enumerate(zip(source_sets, native_sets)):
        for color_index, (source_value, native_value) in enumerate(zip(left, right)):
            if source_value != native_value:
                different += 1
                if len(first) < 12:
                    first.append({"set": set_index, "index": color_index,
                                  "source": source_value, "native": native_value})
    return {"path": path, "source": source, "native": native,
            "differentEntries": different, "firstDifferences": first}


def _inputs(registry_path: Path, asset_name: str) -> dict:
    pins = _pins(asset_name)
    require_hash(Path(base.__file__), BASE_MESH_HOST_SHA256,
                 "base mesh payload host")
    require_hash(Path(variant.__file__), VARIANT_INVENTORY_HOST_SHA256,
                 "variant inventory host")
    accepted = variant._variant_inputs(registry_path, asset_name)
    worklist = require_hash(WORKLIST, WORKLIST_SHA256, "reconstruction worklist")
    data = json.loads(worklist.read_text(encoding="utf-8"))
    candidates = [row for row in data["assets"] if row.get("asset") == asset_name]
    if len(candidates) != 1:
        raise VariantMeshPayloadError("worklist variant is not unique")
    row = candidates[0]
    if (row.get("sourceAssetDigest") != pins["sourceAssetDigest"] or
            row.get("blendSha256") != pins["blendSha256"] or
            row.get("repairedUsfSha256") != pins["repairedUsfSha256"] or
            row.get("scratchNativeUsfSha256") != pins["nativeUsfSha256"] or
            row.get("summarySha256") != pins["summarySha256"] or
            row.get("nativeExportRootName") != asset_name or
            row.get("repairedRootName") != "cat_d11t" or
            row.get("nativeBlendExportApproved") is not False):
        raise VariantMeshPayloadError("variant worklist mesh inputs differ")
    summary = _unlinked_path(Path(row["summaryPath"]), "variant parity summary")
    require_hash(summary, pins["summarySha256"], "variant parity summary")
    summary_data = json.loads(summary.read_text(encoding="utf-8"))
    if (summary_data.get("asset") != asset_name or
            summary_data.get("sourceAssetDigest") != pins["sourceAssetDigest"] or
            summary_data.get("candidateUsfSha256") != pins["nativeUsfSha256"] or
            summary_data.get("nativeBlendExportApproved") is not False):
        raise VariantMeshPayloadError("variant parity summary identity differs")
    native = _unlinked_path(Path(summary_data["candidateUsfPath"]),
                            "variant retained native USF")
    require_hash(native, pins["nativeUsfSha256"], "variant retained native USF")
    return {**accepted, "worklist": worklist, "summary": summary,
            "native": native, "summarySha256": pins["summarySha256"],
            "nativeUsfSha256": pins["nativeUsfSha256"]}


def _validated_field(value: object, name: str) -> tuple[dict, dict, dict]:
    if not isinstance(value, dict) or set(value) != {"source", "native", "repaired"}:
        raise VariantMeshPayloadError(f"incomplete {name} variant component")
    source, native, repaired = (value[key] for key in
                                ("source", "native", "repaired"))
    base._validate_component({"source": source, "native": native,
                              "match": source == native}, name)
    base._validate_component({"source": source, "native": repaired,
                              "match": source == repaired}, name)
    return source, native, repaired


def _validate_color_detail(value: object, target_row: dict,
                           *, include_cache: bool) -> dict:
    expected = {"path", "source", "native", "differentEntries",
                "firstDifferences"}
    if include_cache:
        expected |= {"cacheAfterUsfReads", "cacheBeforeTarget",
                     "cacheAfterTarget", "cacheAfterAll"}
    if not isinstance(value, dict) or set(value) != expected or \
            value["path"] != target_row["path"]:
        raise VariantMeshPayloadError("color detail path or fields differ")
    field = target_row["fields"]["packedColors"]
    if value["source"] != field["source"] or value["native"] != field["native"]:
        raise VariantMeshPayloadError("color detail contradicts row summaries")
    if include_cache:
        for key in ("cacheAfterUsfReads", "cacheBeforeTarget",
                    "cacheAfterTarget", "cacheAfterAll"):
            if type(value[key]) is not int or value[key] < 0:
                raise VariantMeshPayloadError("invalid SDK color-cache count")
    count = value["differentEntries"]
    samples = value["firstDifferences"]
    if (type(count) is not int or not 0 <= count <= value["source"]["elements"] or
            not isinstance(samples, list) or len(samples) != min(count, 12) or
            (count == 0) != (value["source"] == value["native"])):
        raise VariantMeshPayloadError("color detail count contradicts digest")
    last = (-1, -1)
    for sample in samples:
        if not isinstance(sample, dict) or set(sample) != {
                "set", "index", "source", "native"}:
            raise VariantMeshPayloadError("invalid color difference sample")
        index = (sample["set"], sample["index"])
        if (type(sample["set"]) is not int or type(sample["index"]) is not int or
                not 0 <= sample["set"] < value["source"]["sets"] or
                not 0 <= sample["index"] < value["source"]["elements"] or
                index <= last or
                type(sample["source"]) is not int or
                type(sample["native"]) is not int or
                not 0 <= sample["source"] <= 0xFFFFFFFF or
                not 0 <= sample["native"] <= 0xFFFFFFFF or
                sample["source"] == sample["native"]):
            raise VariantMeshPayloadError("color difference sample is invalid")
        last = index
    return value


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
        "baseMeshHostSha256": BASE_MESH_HOST_SHA256,
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
        raise VariantMeshPayloadError("variant identity or no-write fields differ")
    if (blender_sha not in BLENDER_VERSION_PINS or
            not isinstance(result.get("blenderVersion"), str) or
            not result["blenderVersion"].startswith(BLENDER_VERSION_PINS[blender_sha])):
        raise VariantMeshPayloadError("variant Blender version differs")
    rows = result.get("rows")
    if not isinstance(rows, list) or len(rows) != len(gap_rows) or len(rows) != 126:
        raise VariantMeshPayloadError("variant mesh row coverage differs")
    seen = set()
    native_matches = {name: 0 for name in base.FIELD_NAMES}
    repaired_ordered_matches = {name: 0 for name in base.FIELD_NAMES}
    repaired_same_count = {name: 0 for name in base.FIELD_NAMES}
    repaired_same_uv_names = 0
    repaired_same_color_sets = 0
    repaired_same_skin_width = 0
    repaired_position_aligned_rows = 0
    repaired_comparable_normals_rows = 0
    repaired_equal_normals_on_aligned_rows = 0
    repaired_comparable_uv_rows = 0
    repaired_equal_uv_on_aligned_rows = 0
    repaired_comparable_colors_rows = 0
    repaired_equal_colors_on_aligned_rows = 0
    all_native_rows = 0
    for row, gap in zip(rows, gap_rows):
        if (not isinstance(row, dict) or set(row) != {
                "path", "sourceObject", "fields"} or
                row["path"] != gap["path"] or
                not isinstance(row["sourceObject"], str) or
                not row["sourceObject"] or
                row["sourceObject"] in seen or
                not isinstance(row["fields"], dict) or
                set(row["fields"]) != set(base.FIELD_NAMES)):
            raise VariantMeshPayloadError("variant path, mapping or field coverage differs")
        seen.add(row["sourceObject"])
        row_native_exact = True
        for name in base.FIELD_NAMES:
            source, native, repaired = _validated_field(row["fields"][name], name)
            equal_native = source == native
            native_matches[name] += equal_native
            row_native_exact = row_native_exact and equal_native
            repaired_ordered_matches[name] += source == repaired
            repaired_same_count[name] += source["elements"] == repaired["elements"]
            if name == "uvCoordinates":
                repaired_same_uv_names += source["names"] == repaired["names"]
            elif name == "packedColors":
                repaired_same_color_sets += source["sets"] == repaired["sets"]
            elif name == "skinIndicesWeights":
                repaired_same_skin_width += (
                    source["bonesPerVertex"] == repaired["bonesPerVertex"])
        fields = row["fields"]
        position_aligned = (
            fields["positions"]["source"] == fields["positions"]["repaired"])
        repaired_position_aligned_rows += position_aligned
        if position_aligned:
            source_normal = fields["normals"]["source"]
            repaired_normal = fields["normals"]["repaired"]
            normal_comparable = source_normal["elements"] == repaired_normal["elements"]
            repaired_comparable_normals_rows += normal_comparable
            repaired_equal_normals_on_aligned_rows += (
                normal_comparable and source_normal == repaired_normal)

            source_uv = fields["uvCoordinates"]["source"]
            repaired_uv = fields["uvCoordinates"]["repaired"]
            uv_comparable = (source_uv["elements"] == repaired_uv["elements"] and
                             source_uv["names"] == repaired_uv["names"])
            repaired_comparable_uv_rows += uv_comparable
            repaired_equal_uv_on_aligned_rows += uv_comparable and source_uv == repaired_uv

            source_color = fields["packedColors"]["source"]
            repaired_color = fields["packedColors"]["repaired"]
            color_comparable = (
                source_color["elements"] == repaired_color["elements"] and
                source_color["sets"] == repaired_color["sets"])
            repaired_comparable_colors_rows += color_comparable
            repaired_equal_colors_on_aligned_rows += (
                color_comparable and source_color == repaired_color)
        all_native_rows += row_native_exact
    color_rows = [row for row in rows if row["path"] == COLOR_DETAIL_PATH]
    if len(color_rows) != 1:
        raise VariantMeshPayloadError("target color path coverage differs")
    color_detail = _validate_color_detail(
        result.get("colorDetail"), color_rows[0], include_cache=True)
    mismatch_rows = {row["path"]: row for row in rows
                     if row["fields"]["packedColors"]["source"] !=
                     row["fields"]["packedColors"]["native"]}
    mismatch_details = result.get("nativeColorMismatchDetails")
    if (not isinstance(mismatch_details, list) or
            len(mismatch_details) != len(mismatch_rows) or
            len(mismatch_details) > 126):
        raise VariantMeshPayloadError("native color mismatch detail coverage differs")
    detail_paths = set()
    for detail in mismatch_details:
        path = detail.get("path") if isinstance(detail, dict) else None
        if path not in mismatch_rows or path in detail_paths:
            raise VariantMeshPayloadError("native color mismatch path differs")
        _validate_color_detail(detail, mismatch_rows[path], include_cache=False)
        if detail["differentEntries"] < 1:
            raise VariantMeshPayloadError("native color mismatch has no differing value")
        detail_paths.add(path)
    if detail_paths != set(mismatch_rows):
        raise VariantMeshPayloadError("native color mismatch paths are incomplete")
    compact = {key: result[key] for key in expected}
    compact.update({
        "status": "SOURCE_NATIVE_VARIANT_MESH_PAYLOAD_READBACK",
        "blenderVersion": result["blenderVersion"],
        "mappedRows": len(rows),
        "matchingNativeRowsByField": native_matches,
        "allComparedNativeFieldsMatchRows": all_native_rows,
        "repairedOrderedDigestEqualRowsByField": repaired_ordered_matches,
        "repairedSameElementCountRowsByField": repaired_same_count,
        "repairedSameUvLayerNamesRows": repaired_same_uv_names,
        "repairedSameColorSetCountRows": repaired_same_color_sets,
        "repairedSameBonesPerVertexRows": repaired_same_skin_width,
        "repairedPositionAlignedRows": repaired_position_aligned_rows,
        "repairedComparableNormalsOnAlignedRows": repaired_comparable_normals_rows,
        "repairedEqualNormalsOnAlignedRows": repaired_equal_normals_on_aligned_rows,
        "repairedComparableUvOnAlignedRows": repaired_comparable_uv_rows,
        "repairedEqualUvOnAlignedRows": repaired_equal_uv_on_aligned_rows,
        "repairedComparableColorsOnAlignedRows": repaired_comparable_colors_rows,
        "repairedEqualColorsOnAlignedRows": repaired_equal_colors_on_aligned_rows,
        "rowsDigestSha256": hashlib.sha256(base._canonical(rows)).hexdigest(),
        "tangentsCompared": False,
        "materialPayloadCompared": False,
        "repairedSemanticMeshParityClaimed": False,
        "repairedMaterialIndexMeaningCompared": False,
        "repairedSkinBoneIdentityCompared": False,
        "nativeBlendExportApproved": False,
        "colorDetail": color_detail,
        "nativeColorMismatchDetails": mismatch_details,
        "rows": rows,
    })
    if len(base._canonical(compact)) > MAX_JSON_BYTES:
        raise VariantMeshPayloadError("bounded variant mesh result exceeded")
    return compact


def parse_result(stdout: str, gap_rows: list[dict], asset_name: str,
                 blender_sha: str, host_sha: str) -> dict:
    matches = [line[len(RESULT_PREFIX):] for line in stdout.splitlines()
               if line.startswith(RESULT_PREFIX)]
    if len(matches) != 1 or len(matches[0].encode("utf-8")) > MAX_JSON_BYTES:
        raise VariantMeshPayloadError("Blender emitted no unique bounded readback")
    try:
        raw = json.loads(matches[0])
    except json.JSONDecodeError as exc:
        raise VariantMeshPayloadError("variant mesh JSON is malformed") from exc
    return interpret_readback(raw, gap_rows, asset_name, blender_sha, host_sha)


def run_probe(*, registry_path: Path, blender_executable: Path,
              sdk_script_root: Path, asset_name: str,
              timeout_seconds: int = 900) -> dict:
    if type(timeout_seconds) is not int or timeout_seconds < 1:
        raise VariantMeshPayloadError("timeout must be a positive integer")
    before = _inputs(registry_path, asset_name)
    pins = _pins(asset_name)
    blender = _unlinked_path(blender_executable, "Blender executable")
    blender_sha = file_sha256(blender)
    if blender_sha not in BLENDER_VERSION_PINS:
        raise VariantMeshPayloadError("Blender executable differs from reviewed pins")
    require_hash(blender, blender_sha, "Blender executable")
    sdk = require_sdk_pins(sdk_script_root)
    mapper_worker = require_hash(base.MAPPER_WORKER, base.MAPPER_WORKER_SHA256,
                                 "mapped path worker")
    worker = require_hash(WORKER, WORKER_SHA256, "variant mesh worker")
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
        raise VariantMeshPayloadError(f"Blender exited {completed.returncode}: {tail}")
    result = parse_result(completed.stdout, before["gapRows"],
                          asset_name, blender_sha, host_sha)
    after = _inputs(registry_path, asset_name)
    if any(before[key] != after[key] for key in (
            "registrySha256", "sourceRoot", "blend", "usf", "gapRows",
            "worklist", "summary", "native", "summarySha256", "nativeUsfSha256")):
        raise VariantMeshPayloadError("variant inputs changed during readback")
    for path, digest, label in (
            (before["blend"], pins["blendSha256"], "variant Blend"),
            (before["usf"], pins["repairedUsfSha256"], "variant repaired USF"),
            (before["native"], pins["nativeUsfSha256"], "variant native USF"),
            (before["summary"], pins["summarySha256"], "variant summary"),
            (blender, blender_sha, "Blender executable"),
            (mapper_worker, base.MAPPER_WORKER_SHA256, "mapper worker"),
            (worker, WORKER_SHA256, "variant mesh worker"),
            (Path(__file__), host_sha, "variant mesh host")):
        require_hash(path, digest, label + " after readback")
    require_sdk_pins(sdk)
    result.update({
        "sourceUnchanged": True, "sdkUnchanged": True,
        "nativeExportUnchanged": True, "repairedUsfUnchanged": True,
        "inventorySha256": INVENTORY_SHA256,
        "workerSha256": WORKER_SHA256,
    })
    if len(base._canonical(result)) > MAX_JSON_BYTES:
        raise VariantMeshPayloadError("bounded final variant result exceeded")
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
    except (VariantMeshPayloadError, variant.VariantMeshInventoryError,
            base.MeshPayloadError, LeftPushProbeError, BlenderAuthoringError,
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
