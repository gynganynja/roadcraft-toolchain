"""Blender-side, no-save D11 v2/v3 mesh-payload readback."""

from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roadcraft.blender_mesh_payload import (  # noqa: E402
    BLENDER_VERSION_PINS, FIELD_NAMES, WORKLIST_SHA256,
    require_hash, require_sdk_pins, summarize_mesh,
)
from roadcraft.blender_mesh_variant_payload import (  # noqa: E402
    ASSET_PINS, BASE_MESH_HOST_SHA256, COLOR_DETAIL_PATH, RESULT_PREFIX,
    VariantMeshPayloadError, summarize_color_detail,
)
from roadcraft.blender_mesh_inventory import (  # noqa: E402
    WORKER_SHA256 as MAPPER_WORKER_SHA256,
)
from roadcraft.blender_mesh_inventory_worker import (  # noqa: E402
    _predicted_path, _source_object,
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VariantMeshPayloadError(message)


def _usf_summaries(usf: Path, paths: set[str], root_name: str,
                   label: str, capture_colors: bool = False) -> tuple[str, dict, list | None]:
    from saber.blender.lib.usf.scene import usf_read

    _, scene = usf_read(str(usf))
    root = scene._root_node
    _require(root.name == root_name, f"{label} root differs")
    found = {}
    captured_colors = None
    stack = [(root, "|@root")]
    while stack:
        node, path = stack.pop()
        if path in paths:
            _require(path not in found and node.mesh is not None,
                     f"duplicate or missing {label} mesh: {path}")
            found[path] = summarize_mesh(node.mesh)
            if capture_colors and path == COLOR_DETAIL_PATH:
                captured_colors = [list(color_set.colors)
                                   for color_set in node.mesh.colorsets.sets]
        for child in node.children:
            stack.append((child, path + "|" + child.name))
    _require(set(found) == paths, f"{label} mesh path coverage differs")
    del scene, root, stack
    gc.collect()
    return root_name, found, captured_colors


def _raw_color_sets(usf: Path, paths: set[str], root_name: str) -> dict:
    from saber.blender.lib.usf.scene import usf_read

    _, scene = usf_read(str(usf))
    root = scene._root_node
    _require(root.name == root_name, "native detail root differs")
    found = {}
    stack = [(root, "|@root")]
    while stack:
        node, path = stack.pop()
        if path in paths:
            _require(path not in found and node.mesh is not None,
                     "native detail path is duplicate or lacks mesh")
            found[path] = [list(color_set.colors)
                           for color_set in node.mesh.colorsets.sets]
        for child in node.children:
            stack.append((child, path + "|" + child.name))
    _require(set(found) == paths, "native detail color path coverage differs")
    return found


def run_readback(*, asset_name: str, blend: Path, repaired: Path,
                 native: Path, worklist: Path, summary: Path, sdk_root: Path,
                 worker_sha256: str, mapper_sha256: str,
                 host_sha256: str, blender_sha256: str) -> dict:
    _require(asset_name in ASSET_PINS, "variant is outside v2/v3 allowlist")
    pins = ASSET_PINS[asset_name]
    _require(blender_sha256 in BLENDER_VERSION_PINS,
             "Blender executable pin is not reviewed")
    require_hash(Path(bpy.app.binary_path), blender_sha256, "Blender executable")
    require_hash(Path(__file__), worker_sha256, "variant mesh worker")
    host = Path(__file__).with_name("blender_mesh_variant_payload.py")
    require_hash(host, host_sha256, "variant mesh host")
    base_host = Path(__file__).with_name("blender_mesh_payload.py")
    require_hash(base_host, BASE_MESH_HOST_SHA256, "base mesh host")
    mapper = Path(__file__).with_name("blender_mesh_inventory_worker.py")
    _require(mapper_sha256 == MAPPER_WORKER_SHA256,
             "mesh mapper worker pin differs")
    require_hash(mapper, mapper_sha256, "mesh mapper worker")
    require_hash(blend, pins["blendSha256"], "variant Blend")
    require_hash(repaired, pins["repairedUsfSha256"], "variant repaired USF")
    require_hash(native, pins["nativeUsfSha256"], "variant native USF")
    require_hash(worklist, WORKLIST_SHA256, "reconstruction worklist")
    require_hash(summary, pins["summarySha256"], "variant summary")
    sdk = require_sdk_pins(sdk_root)
    _require(bpy.app.version_string.startswith(BLENDER_VERSION_PINS[blender_sha256]),
             "Blender version differs")
    evidence = json.loads(worklist.read_text(encoding="utf-8"))
    assets = [row for row in evidence["assets"] if row.get("asset") == asset_name]
    _require(len(assets) == 1, "worklist has no unique variant asset")
    asset = assets[0]
    _require(asset.get("sourceAssetDigest") == pins["sourceAssetDigest"] and
             asset.get("blendSha256") == pins["blendSha256"] and
             asset.get("repairedUsfSha256") == pins["repairedUsfSha256"] and
             asset.get("scratchNativeUsfSha256") == pins["nativeUsfSha256"] and
             asset.get("summarySha256") == pins["summarySha256"] and
             asset.get("nativeExportRootName") == asset_name and
             asset.get("repairedRootName") == "cat_d11t" and
             asset.get("nativeBlendExportApproved") is False,
             "variant worklist inputs or blocked gate differ")
    summary_data = json.loads(summary.read_text(encoding="utf-8"))
    _require(summary_data.get("asset") == asset_name and
             summary_data.get("sourceAssetDigest") == pins["sourceAssetDigest"] and
             Path(summary_data["candidateUsfPath"]) == native and
             summary_data.get("candidateUsfSha256") == pins["nativeUsfSha256"] and
             summary_data.get("nativeBlendExportApproved") is False,
             "variant retained export summary differs")
    paths = sorted(row["path"] for row in asset["findings"]["changedMeshNodes"])
    _require(len(paths) == len(set(paths)) == 126,
             "worklist mesh path coverage differs")

    sys.path.insert(0, str(sdk))
    from saber.blender.lib.binary_io import BinaryIO
    from saber.blender.lib.usf.mesh import RGBA_CACHE, UsfMesh

    original_reader = BinaryIO.read_bytearray
    BinaryIO.read_bytearray = (
        lambda self, size=None: self.io.read(size) if size is not None
        else original_reader(self)
    )
    try:
        native_root, native_payload, native_color_sets = _usf_summaries(
            native, set(paths), asset_name, "native", capture_colors=True)
        repaired_root, repaired_payload, _ = _usf_summaries(
            repaired, set(paths), "cat_d11t", "repaired")
    finally:
        BinaryIO.read_bytearray = original_reader
    cache_after_usf_reads = len(RGBA_CACHE)
    _require(native_color_sets is not None, "native target colors not captured")

    bpy.ops.wm.open_mainfile(filepath=str(blend), load_ui=False)
    _require(bpy.context.scene.frame_current == 1, "source scene frame differs")
    scene_meshes = {obj.name: obj for obj in bpy.context.scene.objects
                    if obj.type == "MESH"}
    _require(len(scene_meshes) == 210, "source scene mesh count differs")
    depsgraph = bpy.context.evaluated_depsgraph_get()
    used = set()
    rows = []
    source_color_sets = None
    source_mismatch_colors = {}
    cache_before_target = None
    cache_after_target = None
    for path in paths:
        obj = _source_object(path)
        _require(obj is not None and _predicted_path(obj) == path and
                 scene_meshes.get(obj.name) == obj and obj.visible_get() and
                 obj.name not in used,
                 f"source mesh mapping differs: {path}")
        used.add(obj.name)
        evaluated_object = obj.evaluated_get(depsgraph)
        try:
            if path == COLOR_DETAIL_PATH:
                cache_before_target = len(RGBA_CACHE)
            projected = UsfMesh().b_read(obj)
            source = summarize_mesh(projected)
            if source["packedColors"] != native_payload[path]["packedColors"]:
                source_mismatch_colors[path] = [list(color_set.colors)
                                                for color_set in projected.colorsets.sets]
            if path == COLOR_DETAIL_PATH:
                source_color_sets = [list(color_set.colors)
                                     for color_set in projected.colorsets.sets]
                cache_after_target = len(RGBA_CACHE)
        finally:
            evaluated_object.to_mesh_clear()
        fields = {name: {"source": source[name],
                         "native": native_payload[path][name],
                         "repaired": repaired_payload[path][name]}
                  for name in FIELD_NAMES}
        rows.append({"path": path, "sourceObject": obj.name,
                     "fields": fields})
        del projected, source
        if len(rows) % 10 == 0:
            gc.collect()
    _require(source_color_sets is not None and cache_before_target is not None and
             cache_after_target is not None,
             "source target colors not captured")
    color_detail = summarize_color_detail(source_color_sets, native_color_sets)
    cache_after_all = len(RGBA_CACHE)
    color_detail.update({
        "cacheAfterUsfReads": cache_after_usf_reads,
        "cacheBeforeTarget": cache_before_target,
        "cacheAfterTarget": cache_after_target,
        "cacheAfterAll": cache_after_all,
    })
    mismatch_details = []
    if source_mismatch_colors:
        BinaryIO.read_bytearray = (
            lambda self, size=None: self.io.read(size) if size is not None
            else original_reader(self)
        )
        try:
            native_mismatch_colors = _raw_color_sets(
                native, set(source_mismatch_colors), asset_name)
        finally:
            BinaryIO.read_bytearray = original_reader
        mismatch_details = [
            summarize_color_detail(source_mismatch_colors[path],
                                   native_mismatch_colors[path], path)
            for path in sorted(source_mismatch_colors)
        ]
    for path, digest, label in (
            (blend, pins["blendSha256"], "variant Blend"),
            (repaired, pins["repairedUsfSha256"], "variant repaired USF"),
            (native, pins["nativeUsfSha256"], "variant native USF"),
            (worklist, WORKLIST_SHA256, "worklist"),
            (summary, pins["summarySha256"], "variant summary"),
            (host, host_sha256, "variant mesh host"),
            (base_host, BASE_MESH_HOST_SHA256, "base mesh host"),
            (Path(__file__), worker_sha256, "variant mesh worker"),
            (mapper, mapper_sha256, "mesh mapper worker")):
        require_hash(path, digest, label + " after readback")
    require_sdk_pins(sdk)
    return {
        "schemaVersion": 1, "asset": asset_name,
        "sourceAssetDigest": pins["sourceAssetDigest"],
        "blendSha256": pins["blendSha256"],
        "repairedUsfSha256": pins["repairedUsfSha256"],
        "nativeExportUsfSha256": pins["nativeUsfSha256"],
        "summarySha256": pins["summarySha256"],
        "worklistSha256": WORKLIST_SHA256,
        "blenderSha256": blender_sha256,
        "hostSha256": host_sha256,
        "baseMeshHostSha256": BASE_MESH_HOST_SHA256,
        "mapperWorkerSha256": mapper_sha256,
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


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset", choices=tuple(ASSET_PINS), required=True)
    parser.add_argument("--blend", type=Path, required=True)
    parser.add_argument("--repaired-usf", type=Path, required=True)
    parser.add_argument("--native-usf", type=Path, required=True)
    parser.add_argument("--worklist", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--worker-sha256", required=True)
    parser.add_argument("--mapper-sha256", required=True)
    parser.add_argument("--host-sha256", required=True)
    parser.add_argument("--blender-sha256", required=True)
    args = parser.parse_args(argv)
    result = run_readback(
        asset_name=args.asset, blend=args.blend,
        repaired=args.repaired_usf, native=args.native_usf,
        worklist=args.worklist, summary=args.summary,
        sdk_root=args.sdk_script_root, worker_sha256=args.worker_sha256,
        mapper_sha256=args.mapper_sha256, host_sha256=args.host_sha256,
        blender_sha256=args.blender_sha256)
    print(RESULT_PREFIX + json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
