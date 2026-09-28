"""Blender-side, no-save D11 source-to-native mesh payload readback."""

from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roadcraft.blender_mesh_payload import (  # noqa: E402
    BLEND_SHA256, BLENDER_VERSION_PINS, FIELD_NAMES, RESULT_PREFIX,
    USF_SHA256, WORKLIST_SHA256, MeshPayloadError, require_hash,
    require_sdk_pins, summarize_mesh,
)
from roadcraft.blender_mesh_inventory import (  # noqa: E402
    WORKER_SHA256 as MAPPER_WORKER_SHA256,
)
from roadcraft.blender_mesh_inventory_worker import (  # noqa: E402
    _predicted_path, _source_object,
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise MeshPayloadError(message)


def _native_summaries(native: Path, paths: set[str]) -> tuple[str, dict]:
    from saber.blender.lib.usf.scene import usf_read

    _, scene = usf_read(str(native))
    root = scene._root_node
    _require(root.name == "cat_d11t", "retained native USF root differs")
    found = {}
    stack = [(root, "|@root")]
    while stack:
        node, path = stack.pop()
        if path in paths:
            _require(path not in found and node.mesh is not None,
                     f"duplicate or missing native mesh: {path}")
            found[path] = summarize_mesh(node.mesh)
        for child in node.children:
            stack.append((child, path + "|" + child.name))
    _require(set(found) == paths, "retained native mesh path coverage differs")
    del scene, root, stack
    gc.collect()
    return "cat_d11t", found


def run_readback(*, blend: Path, repaired: Path, native: Path, worklist: Path,
                 sdk_root: Path, worker_sha256: str, mapper_sha256: str,
                 host_sha256: str, blender_sha256: str, native_sha256: str,
                 summary_sha256: str) -> dict:
    _require(blender_sha256 in BLENDER_VERSION_PINS,
             "Blender executable pin is not reviewed")
    require_hash(Path(bpy.app.binary_path), blender_sha256, "Blender executable")
    require_hash(Path(__file__), worker_sha256, "payload worker")
    host = Path(__file__).with_name("blender_mesh_payload.py")
    require_hash(host, host_sha256, "payload host")
    mapper = Path(__file__).with_name("blender_mesh_inventory_worker.py")
    _require(mapper_sha256 == MAPPER_WORKER_SHA256,
             "mesh path mapper pin differs")
    require_hash(mapper, mapper_sha256, "mesh path mapper")
    require_hash(blend, BLEND_SHA256, "source Blend")
    require_hash(repaired, USF_SHA256, "repaired USF")
    require_hash(native, native_sha256, "retained native USF")
    require_hash(worklist, WORKLIST_SHA256, "reconstruction worklist")
    sdk = require_sdk_pins(sdk_root)
    _require(bpy.app.version_string.startswith(BLENDER_VERSION_PINS[blender_sha256]),
             "Blender version differs")
    evidence = json.loads(worklist.read_text(encoding="utf-8"))
    assets = [row for row in evidence["assets"] if row.get("asset") == "cat_d11t"]
    _require(len(assets) == 1, "worklist has no unique base asset")
    asset = assets[0]
    _require(asset.get("blendSha256") == BLEND_SHA256 and
             asset.get("repairedUsfSha256") == USF_SHA256 and
             asset.get("scratchNativeUsfSha256") == native_sha256 and
             asset.get("summarySha256") == summary_sha256 and
             asset.get("nativeBlendExportApproved") is False,
             "worklist source/native identity or blocked gate differs")
    summary = require_hash(Path(asset["summaryPath"]), summary_sha256,
                           "base parity summary")
    summary_data = json.loads(summary.read_text(encoding="utf-8"))
    _require(Path(summary_data["candidateUsfPath"]) == native and
             summary_data["candidateUsfSha256"] == native_sha256 and
             summary_data["nativeBlendExportApproved"] is False,
             "retained native summary differs")
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
        native_root, native_payload = _native_summaries(native, set(paths))
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
            source = summarize_mesh(projected)
        finally:
            evaluated_object.to_mesh_clear()
        fields = {name: {"source": source[name], "native": native_payload[path][name],
                         "match": source[name] == native_payload[path][name]}
                  for name in FIELD_NAMES}
        rows.append({"path": path, "sourceObject": obj.name, "fields": fields})
        del projected, source
        if len(rows) % 10 == 0:
            gc.collect()
    require_hash(blend, BLEND_SHA256, "source Blend after readback")
    require_hash(repaired, USF_SHA256, "repaired USF after readback")
    require_hash(native, native_sha256, "retained native USF after readback")
    require_hash(worklist, WORKLIST_SHA256, "worklist after readback")
    require_hash(summary, summary_sha256, "summary after readback")
    require_hash(host, host_sha256, "payload host after readback")
    require_hash(Path(__file__), worker_sha256, "payload worker after readback")
    require_hash(mapper, mapper_sha256, "mesh mapper after readback")
    require_sdk_pins(sdk)
    return {
        "schemaVersion": 1, "asset": "cat_d11t",
        "blendSha256": BLEND_SHA256,
        "repairedUsfSha256": USF_SHA256,
        "nativeExportUsfSha256": native_sha256,
        "worklistSha256": WORKLIST_SHA256,
        "summarySha256": summary_sha256,
        "blenderSha256": blender_sha256,
        "hostSha256": host_sha256,
        "mapperWorkerSha256": mapper_sha256,
        "blenderVersion": bpy.app.version_string,
        "sceneFrame": bpy.context.scene.frame_current,
        "sourceSceneMeshCount": len(scene_meshes),
        "nativeExportRootName": native_root,
        "blendSaved": False, "usfExported": False,
        "nativeBlendExportApproved": False,
        "rows": rows,
    }


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--blend", type=Path, required=True)
    parser.add_argument("--repaired-usf", type=Path, required=True)
    parser.add_argument("--native-usf", type=Path, required=True)
    parser.add_argument("--worklist", type=Path, required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--worker-sha256", required=True)
    parser.add_argument("--mapper-sha256", required=True)
    parser.add_argument("--host-sha256", required=True)
    parser.add_argument("--blender-sha256", required=True)
    parser.add_argument("--native-usf-sha256", required=True)
    parser.add_argument("--summary-sha256", required=True)
    args = parser.parse_args(argv)
    result = run_readback(
        blend=args.blend, repaired=args.repaired_usf, native=args.native_usf,
        worklist=args.worklist, sdk_root=args.sdk_script_root,
        worker_sha256=args.worker_sha256, mapper_sha256=args.mapper_sha256,
        host_sha256=args.host_sha256, blender_sha256=args.blender_sha256,
        native_sha256=args.native_usf_sha256,
        summary_sha256=args.summary_sha256)
    print(RESULT_PREFIX + json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
