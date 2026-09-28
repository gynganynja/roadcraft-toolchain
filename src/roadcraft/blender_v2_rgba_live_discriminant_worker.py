"""Blender-side, unwrapped-SDK v2 target RGBA readback; no save or export."""

from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roadcraft import blender_mesh_variant_payload as variant  # noqa: E402
from roadcraft import blender_v2_rgba_live_discriminant as probe  # noqa: E402
from roadcraft.blender_left_push_probe import (  # noqa: E402
    require_hash, require_sdk_pins,
)
from roadcraft.blender_mesh_inventory import (  # noqa: E402
    WORKER_SHA256 as MAPPER_WORKER_SHA256,
)
from roadcraft.blender_mesh_inventory_worker import (  # noqa: E402
    _predicted_path, _source_object,
)
from roadcraft.blender_mesh_payload import (  # noqa: E402
    FIELD_NAMES, WORKLIST_SHA256, summarize_mesh,
)
from roadcraft.blender_mesh_variant_payload_worker import (  # noqa: E402
    _raw_color_sets, _usf_summaries,
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise probe.LiveRgbaError(message)


def _read_native_mismatch_colors(native: Path, paths: set[str],
                                 asset_name: str, binary_io) -> dict:
    original = binary_io.read_bytearray
    binary_io.read_bytearray = (
        lambda self, size=None: self.io.read(size) if size is not None
        else original(self)
    )
    try:
        return _raw_color_sets(native, paths, asset_name)
    finally:
        binary_io.read_bytearray = original


def run_probe(*, blend: Path, repaired: Path, native: Path, worklist: Path,
              summary: Path, sdk_root: Path, probe_worker_sha256: str,
              probe_host_sha256: str, blender_sha256: str) -> dict:
    _require(blender_sha256 == probe.BLENDER_SHA256,
             "Blender executable is outside pinned 5.2 probe")
    _require(probe_worker_sha256 == probe.WORKER_SHA256,
             "live RGBA worker pin differs")
    require_hash(Path(bpy.app.binary_path), blender_sha256, "Blender executable")
    require_hash(Path(__file__), probe_worker_sha256, "live RGBA worker")
    require_hash(Path(probe.__file__), probe_host_sha256, "live RGBA host")
    require_hash(Path(variant.__file__), probe.VARIANT_HOST_SHA256,
                 "reviewed variant host")
    require_hash(variant.WORKER, probe.VARIANT_WORKER_SHA256,
                 "reviewed variant worker")
    _require(bpy.app.version_string.startswith("5.2."),
             "Blender runtime version differs")
    pins = variant.ASSET_PINS[probe.ASSET]
    for path, digest, label in (
            (blend, pins["blendSha256"], "accepted v2 Blend"),
            (repaired, pins["repairedUsfSha256"], "accepted repaired USF"),
            (native, pins["nativeUsfSha256"], "retained native USF"),
            (worklist, WORKLIST_SHA256, "reconstruction worklist"),
            (summary, pins["summarySha256"], "retained native summary")):
        require_hash(path, digest, label)
    sdk = require_sdk_pins(sdk_root)
    evidence = json.loads(worklist.read_text(encoding="utf-8"))
    assets = [row for row in evidence["assets"]
              if row.get("asset") == probe.ASSET]
    _require(len(assets) == 1, "worklist has no unique v2 asset")
    asset = assets[0]
    _require(asset.get("sourceAssetDigest") == pins["sourceAssetDigest"] and
             asset.get("blendSha256") == pins["blendSha256"] and
             asset.get("repairedUsfSha256") == pins["repairedUsfSha256"] and
             asset.get("scratchNativeUsfSha256") == pins["nativeUsfSha256"] and
             asset.get("summarySha256") == pins["summarySha256"] and
             asset.get("nativeExportRootName") == probe.ASSET and
             asset.get("repairedRootName") == "cat_d11t" and
             asset.get("nativeBlendExportApproved") is False,
             "v2 worklist identity or export gate differs")
    summary_data = json.loads(summary.read_text(encoding="utf-8"))
    _require(summary_data.get("asset") == probe.ASSET and
             summary_data.get("sourceAssetDigest") == pins["sourceAssetDigest"] and
             Path(summary_data["candidateUsfPath"]) == native and
             summary_data.get("candidateUsfSha256") == pins["nativeUsfSha256"] and
             summary_data.get("nativeBlendExportApproved") is False,
             "retained native summary differs")
    paths = sorted(row["path"] for row in asset["findings"]["changedMeshNodes"])
    _require(len(paths) == len(set(paths)) == 126 and
             probe.TARGET_PATH in paths and variant.COLOR_DETAIL_PATH in paths,
             "worklist mesh paths differ")

    sys.path.insert(0, str(sdk))
    from saber.blender.lib.binary_io import BinaryIO
    from saber.blender.lib.usf.mesh import RGBA_CACHE, UsfMesh, UsfMeshColorSet

    original_b_read = UsfMesh.b_read
    original_pack = UsfMeshColorSet.rgba_to_saber
    sdk_mesh_file = (sdk / "saber" / "blender" / "lib" / "usf" / "mesh.py").resolve()
    _require(Path(original_b_read.__code__.co_filename).resolve() == sdk_mesh_file and
             Path(original_pack.__code__.co_filename).resolve() == sdk_mesh_file and
             UsfMeshColorSet.FAST_PACK is False,
             "reviewed SDK functions or color mode differ")

    original_reader = BinaryIO.read_bytearray
    BinaryIO.read_bytearray = (
        lambda self, size=None: self.io.read(size) if size is not None
        else original_reader(self)
    )
    try:
        native_root, native_payload, native_lod2_colors = _usf_summaries(
            native, set(paths), probe.ASSET, "native", capture_colors=True)
        repaired_root, repaired_payload, _ = _usf_summaries(
            repaired, set(paths), "cat_d11t", "repaired")
    finally:
        BinaryIO.read_bytearray = original_reader
    cache_after_usf_reads = len(RGBA_CACHE)
    _require(native_lod2_colors is not None,
             "native LOD2 color detail was not captured")

    bpy.ops.wm.open_mainfile(filepath=str(blend), load_ui=False)
    _require(bpy.context.scene.frame_current == 1, "source frame differs")
    scene_meshes = {obj.name: obj for obj in bpy.context.scene.objects
                    if obj.type == "MESH"}
    _require(len(scene_meshes) == 210, "source scene mesh count differs")
    depsgraph = bpy.context.evaluated_depsgraph_get()
    used = set()
    rows = []
    source_lod2_colors = None
    source_mismatch_colors = {}
    cache_before_lod2 = cache_after_lod2 = None
    cache_before_target = cache_after_target = None
    target_source_summary = target_native_summary = None
    target_source_values = raw_packed = raw_rgba = None
    for path in paths:
        obj = _source_object(path)
        _require(obj is not None and _predicted_path(obj) == path and
                 scene_meshes.get(obj.name) == obj and obj.visible_get() and
                 obj.name not in used,
                 f"source mesh mapping differs: {path}")
        used.add(obj.name)
        evaluated_object = obj.evaluated_get(depsgraph)
        try:
            if path == variant.COLOR_DETAIL_PATH:
                cache_before_lod2 = len(RGBA_CACHE)
            if path == probe.TARGET_PATH:
                cache_before_target = len(RGBA_CACHE)
            # These are the installed SDK functions, never replaced or wrapped.
            projected = UsfMesh().b_read(obj)
            source = summarize_mesh(projected)
            if path == probe.TARGET_PATH:
                target_source_summary = source["packedColors"]
                target_native_summary = native_payload[path]["packedColors"]
                if probe.should_read_live_raw(target_source_summary,
                                              target_native_summary):
                    _require(len(projected.colorsets.sets) == 1 and
                             len(projected.b_mesh.color_attributes) == 1 and
                             not any(attr.name.startswith("saber_colorset_idx_")
                                     for attr in projected.b_mesh.attributes),
                             "target live color-set layout differs")
                    target_source_values = list(projected.colorsets.sets[0].colors)
                    raw_packed, raw_rgba = probe.pack_live_triangles(
                        projected.b_mesh,
                        projected.b_mesh.color_attributes[0].data)
                cache_after_target = len(RGBA_CACHE)
            if source["packedColors"] != native_payload[path]["packedColors"]:
                source_mismatch_colors[path] = [list(color_set.colors)
                                                for color_set in projected.colorsets.sets]
            if path == variant.COLOR_DETAIL_PATH:
                source_lod2_colors = [list(color_set.colors)
                                      for color_set in projected.colorsets.sets]
                cache_after_lod2 = len(RGBA_CACHE)
        finally:
            evaluated_object.to_mesh_clear()
        fields = {name: {"source": source[name],
                         "native": native_payload[path][name],
                         "repaired": repaired_payload[path][name]}
                  for name in FIELD_NAMES}
        rows.append({"path": path, "sourceObject": obj.name, "fields": fields})
        del projected, source
        if len(rows) % 10 == 0:
            gc.collect()
    _require(source_lod2_colors is not None and
             cache_before_lod2 is not None and cache_after_lod2 is not None and
             target_source_summary is not None and target_native_summary is not None and
             cache_before_target is not None and cache_after_target is not None,
             "target or LOD2 projection was not completed")
    _require(UsfMesh.b_read is original_b_read and
             UsfMeshColorSet.rgba_to_saber is original_pack,
             "SDK functions changed during readback")

    color_detail = variant.summarize_color_detail(
        source_lod2_colors, native_lod2_colors)
    color_detail.update({
        "cacheAfterUsfReads": cache_after_usf_reads,
        "cacheBeforeTarget": cache_before_lod2,
        "cacheAfterTarget": cache_after_lod2,
        "cacheAfterAll": len(RGBA_CACHE),
    })
    native_mismatch_colors = {}
    mismatch_details = []
    if source_mismatch_colors:
        native_mismatch_colors = _read_native_mismatch_colors(
            native, set(source_mismatch_colors), probe.ASSET, BinaryIO)
        mismatch_details = [
            variant.summarize_color_detail(source_mismatch_colors[path],
                                           native_mismatch_colors[path], path)
            for path in sorted(source_mismatch_colors)
        ]
    target_differs = probe.should_read_live_raw(target_source_summary,
                                                target_native_summary)
    if target_differs:
        _require(target_source_values is not None and raw_packed is not None and
                 raw_rgba is not None and probe.TARGET_PATH in native_mismatch_colors and
                 len(native_mismatch_colors[probe.TARGET_PATH]) == 1,
                 "conditional target raw/native detail is missing")
        detail = probe.summarize_mismatch(
            target_source_values, native_mismatch_colors[probe.TARGET_PATH][0],
            raw_packed, raw_rgba)
        _require(detail["source"] == target_source_summary and
                 detail["native"] == target_native_summary,
                 "conditional target digests contradict projection")
    else:
        _require(target_source_values is None and raw_packed is None and
                 raw_rgba is None, "raw colors read on matching target")
        detail = None

    raw_result = {
        "schemaVersion": 1, "asset": probe.ASSET,
        "sourceAssetDigest": pins["sourceAssetDigest"],
        "blendSha256": pins["blendSha256"],
        "repairedUsfSha256": pins["repairedUsfSha256"],
        "nativeExportUsfSha256": pins["nativeUsfSha256"],
        "summarySha256": pins["summarySha256"],
        "worklistSha256": WORKLIST_SHA256,
        "blenderSha256": blender_sha256,
        "hostSha256": probe.VARIANT_HOST_SHA256,
        "baseMeshHostSha256": variant.BASE_MESH_HOST_SHA256,
        "mapperWorkerSha256": MAPPER_WORKER_SHA256,
        "blenderVersion": bpy.app.version_string,
        "sceneFrame": bpy.context.scene.frame_current,
        "sourceSceneMeshCount": len(scene_meshes),
        "nativeExportRootName": native_root,
        "repairedUsfRootName": repaired_root,
        "blendSaved": False, "usfExported": False,
        "nativeBlendExportApproved": False,
        "colorDetail": color_detail,
        "nativeColorMismatchDetails": mismatch_details,
        "rows": rows,
    }
    gap_rows = sorted(asset["findings"]["changedMeshNodes"],
                      key=lambda row: row["path"])
    interpreted = variant.interpret_readback(
        raw_result, gap_rows, probe.ASSET, blender_sha256,
        probe.VARIANT_HOST_SHA256)
    for path, digest, label in (
            (blend, pins["blendSha256"], "accepted v2 Blend"),
            (repaired, pins["repairedUsfSha256"], "accepted repaired USF"),
            (native, pins["nativeUsfSha256"], "retained native USF"),
            (worklist, WORKLIST_SHA256, "reconstruction worklist"),
            (summary, pins["summarySha256"], "retained native summary"),
            (Path(__file__), probe_worker_sha256, "live RGBA worker"),
            (Path(probe.__file__), probe_host_sha256, "live RGBA host"),
            (Path(variant.__file__), probe.VARIANT_HOST_SHA256,
             "reviewed variant host"),
            (variant.WORKER, probe.VARIANT_WORKER_SHA256,
             "reviewed variant worker")):
        require_hash(path, digest, label + " after readback")
    require_sdk_pins(sdk)
    _require(UsfMesh.b_read is original_b_read and
             UsfMeshColorSet.rgba_to_saber is original_pack,
             "SDK functions changed after readback")
    return {
        "schemaVersion": 1, "status": "SOURCE_V2_RGBA_LIVE_DISCRIMINANT",
        "asset": probe.ASSET, "targetPath": probe.TARGET_PATH,
        "blenderVersion": bpy.app.version_string,
        "blenderSha256": blender_sha256,
        "probeHostSha256": probe_host_sha256,
        "probeWorkerSha256": probe_worker_sha256,
        "variantHostSha256": probe.VARIANT_HOST_SHA256,
        "variantWorkerSha256": probe.VARIANT_WORKER_SHA256,
        "blendSha256": pins["blendSha256"],
        "nativeUsfSha256": pins["nativeUsfSha256"],
        "repairedUsfSha256": pins["repairedUsfSha256"],
        "worklistSha256": WORKLIST_SHA256,
        "summarySha256": pins["summarySha256"],
        "sdkMeshSha256": probe.SDK_PINS["saber/blender/lib/usf/mesh.py"],
        "sdkFunctionsUnwrapped": True,
        "blendSaved": False, "usfExported": False,
        "nativeBlendExportApproved": False,
        "mappedRows": interpreted["mappedRows"],
        "matchingNativeColorsRows": interpreted["matchingNativeRowsByField"]["packedColors"],
        "otherColorMismatchRows": len(source_mismatch_colors) - target_differs,
        "rowsDigestSha256": interpreted["rowsDigestSha256"],
        "target": {"source": target_source_summary,
                   "native": target_native_summary,
                   "rawReadbackPerformed": target_differs,
                   "detail": detail,
                   "cacheBefore": cache_before_target,
                   "cacheAfter": cache_after_target},
        "sourceUnchanged": True, "sdkUnchanged": True,
        "nativeExportUnchanged": True, "repairedUsfUnchanged": True,
    }


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset", choices=(probe.ASSET,), required=True)
    parser.add_argument("--blend", type=Path, required=True)
    parser.add_argument("--repaired-usf", type=Path, required=True)
    parser.add_argument("--native-usf", type=Path, required=True)
    parser.add_argument("--worklist", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--probe-worker-sha256", required=True)
    parser.add_argument("--probe-host-sha256", required=True)
    parser.add_argument("--blender-sha256", required=True)
    args = parser.parse_args(argv)
    result = run_probe(
        blend=args.blend, repaired=args.repaired_usf,
        native=args.native_usf, worklist=args.worklist,
        summary=args.summary, sdk_root=args.sdk_script_root,
        probe_worker_sha256=args.probe_worker_sha256,
        probe_host_sha256=args.probe_host_sha256,
        blender_sha256=args.blender_sha256)
    print(probe.RESULT_PREFIX + json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
