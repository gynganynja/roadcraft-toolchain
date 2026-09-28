"""Blender-side, no-save D11 v2/v3 material payload readback."""

from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roadcraft.blender_material_payload import (  # noqa: E402
    BLENDER_VERSION_PINS, WORKLIST_SHA256, MaterialPayloadError,
    require_hash, require_sdk_pins, summarize_materials,
)
from roadcraft.blender_material_variant_payload import (  # noqa: E402
    ASSET_PINS, BASE_MATERIAL_HOST_SHA256, RESULT_PREFIX,
    VariantMaterialPayloadError,
)
from roadcraft.blender_mesh_inventory import (  # noqa: E402
    WORKER_SHA256 as MAPPER_WORKER_SHA256,
)
from roadcraft.blender_mesh_inventory_worker import (  # noqa: E402
    _predicted_path, _source_object,
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VariantMaterialPayloadError(message)


def _usf_summaries(usf: Path, paths: set[str], root_name: str,
                   label: str) -> tuple[str, dict]:
    from saber.blender.lib.usf.scene import usf_read

    _, scene = usf_read(str(usf))
    root = scene._root_node
    _require(root.name == root_name, f"{label} root differs")
    found = {}
    stack = [(root, "|@root")]
    while stack:
        node, path = stack.pop()
        if path in paths:
            _require(path not in found and node.mesh is not None,
                     f"duplicate or missing {label} mesh: {path}")
            found[path] = summarize_materials(node.mesh)
        for child in node.children:
            stack.append((child, path + "|" + child.name))
    _require(set(found) == paths, f"{label} material path coverage differs")
    del scene, root, stack
    gc.collect()
    return root_name, found


def run_readback(*, asset_name: str, blend: Path, repaired: Path,
                 native: Path, worklist: Path, summary: Path, sdk_root: Path,
                 worker_sha256: str, mapper_sha256: str,
                 host_sha256: str, blender_sha256: str) -> dict:
    _require(asset_name in ASSET_PINS, "variant is outside v2/v3 allowlist")
    pins = ASSET_PINS[asset_name]
    _require(blender_sha256 in BLENDER_VERSION_PINS,
             "Blender executable pin is not reviewed")
    require_hash(Path(bpy.app.binary_path), blender_sha256, "Blender executable")
    require_hash(Path(__file__), worker_sha256, "variant material worker")
    host = Path(__file__).with_name("blender_material_variant_payload.py")
    require_hash(host, host_sha256, "variant material host")
    base_host = Path(__file__).with_name("blender_material_payload.py")
    require_hash(base_host, BASE_MATERIAL_HOST_SHA256, "base material host")
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
    from saber.blender.lib.usf.mesh import UsfMesh

    original_reader = BinaryIO.read_bytearray
    BinaryIO.read_bytearray = (
        lambda self, size=None: self.io.read(size) if size is not None
        else original_reader(self)
    )
    try:
        native_root, native_payload = _usf_summaries(
            native, set(paths), asset_name, "native")
        repaired_root, repaired_payload = _usf_summaries(
            repaired, set(paths), "cat_d11t", "repaired")
    finally:
        BinaryIO.read_bytearray = original_reader

    bpy.ops.wm.open_mainfile(filepath=str(blend), load_ui=False)
    _require(bpy.context.scene.frame_current == 1, "source scene frame differs")
    scene_meshes = {obj.name: obj for obj in bpy.context.scene.objects
                    if obj.type == "MESH"}
    _require(len(scene_meshes) == 210, "source scene mesh count differs")
    depsgraph = bpy.context.evaluated_depsgraph_get()
    used = set()
    rows = []
    for path in paths:
        obj = _source_object(path)
        _require(obj is not None and _predicted_path(obj) == path and
                 scene_meshes.get(obj.name) == obj and obj.visible_get() and
                 obj.name not in used,
                 f"source mesh mapping differs: {path}")
        used.add(obj.name)
        evaluated_object = obj.evaluated_get(depsgraph)
        try:
            projected = UsfMesh().b_read(obj)
            source = summarize_materials(projected)
        finally:
            evaluated_object.to_mesh_clear()
        rows.append({"path": path, "sourceObject": obj.name,
                     "source": source, "native": native_payload[path],
                     "repaired": repaired_payload[path]})
        del projected, source
        if len(rows) % 10 == 0:
            gc.collect()
    for path, digest, label in (
            (blend, pins["blendSha256"], "variant Blend"),
            (repaired, pins["repairedUsfSha256"], "variant repaired USF"),
            (native, pins["nativeUsfSha256"], "variant native USF"),
            (worklist, WORKLIST_SHA256, "worklist"),
            (summary, pins["summarySha256"], "variant summary"),
            (host, host_sha256, "variant material host"),
            (base_host, BASE_MATERIAL_HOST_SHA256, "base material host"),
            (Path(__file__), worker_sha256, "variant material worker"),
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
        "baseMaterialHostSha256": BASE_MATERIAL_HOST_SHA256,
        "mapperWorkerSha256": mapper_sha256,
        "blenderVersion": bpy.app.version_string,
        "sceneFrame": bpy.context.scene.frame_current,
        "sourceSceneMeshCount": len(scene_meshes),
        "nativeExportRootName": native_root,
        "repairedUsfRootName": repaired_root,
        "blendSaved": False, "usfExported": False,
        "nativeBlendExportApproved": False,
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
