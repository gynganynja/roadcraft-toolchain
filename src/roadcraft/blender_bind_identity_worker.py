"""Blender-side, no-save D11 skin identity and inverse-bind readback."""

from __future__ import annotations

import argparse
import gc
import json
import math
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roadcraft.blender_bind_identity import (  # noqa: E402
    BLEND_SHA256, BLENDER_VERSION_PINS, RESULT_PREFIX, USF_SHA256,
    WORKLIST_SHA256, BindIdentityError, compare_binds, require_hash,
    require_sdk_pins,
)
from roadcraft.blender_mesh_inventory import (  # noqa: E402
    WORKER_SHA256 as MAPPER_WORKER_SHA256,
)
from roadcraft.blender_mesh_inventory_worker import (  # noqa: E402
    _predicted_path, _source_object,
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BindIdentityError(message)


def _flatten(matrix) -> list[float]:
    values = [float(matrix[row][col]) for row in range(4) for col in range(4)]
    _require(len(values) == 16 and all(math.isfinite(x) for x in values),
             "nonfinite inverse matrix")
    return values


def _usf_bind_rows(usf: Path, paths: set[str]) -> tuple[str, dict]:
    from saber.blender.lib.usf.scene import usf_read

    _, scene = usf_read(str(usf))
    root = scene._root_node
    _require(root.name == "cat_d11t", f"USF root differs: {usf.name}")
    uid_nodes = {}
    path_nodes = {}
    stack = [(root, "|@root")]
    while stack:
        node, path = stack.pop()
        _require(type(node.uid) is int and node.uid not in uid_nodes,
                 "USF node UID is missing or duplicated")
        uid_nodes[node.uid] = node
        if path in paths:
            _require(path not in path_nodes and node.mesh is not None,
                     f"mapped USF mesh is absent: {path}")
            path_nodes[path] = node
        for child in node.children:
            stack.append((child, path + "|" + child.name))
    _require(set(path_nodes) == paths, "USF mesh path coverage differs")
    rows = {}
    for path in sorted(paths):
        mesh = path_nodes[path].mesh
        binds = []
        self_error = 0.0
        for bone in mesh.skin.skin_bones:
            target = uid_nodes.get(bone.usf_node_uid)
            _require(target is not None and isinstance(target.source_id, str) and
                     target.source_id.startswith("|"),
                     f"skin bone UID cannot resolve: {path}")
            stored = _flatten(bone.inv_bind_matr)
            resolved = _flatten(target.matrix_world.inverted())
            self_error = max(self_error,
                             max(abs(a - b) for a, b in zip(stored, resolved)))
            binds.append({"sourceId": target.source_id, "inverse": stored})
        _require(len(binds) <= 500, f"unbounded USF skin: {path}")
        rows[path] = {"binds": binds, "selfError": self_error}
    del scene, root, uid_nodes, path_nodes, stack
    gc.collect()
    return "cat_d11t", rows


def _source_binds(obj, convert_to_saber_transform) -> list[dict]:
    from saber.blender.lib.usf.mesh import UsfMeshSkin

    projected = UsfMeshSkin().b_read(obj)
    _require(len(projected.skin_bones) <= 500, "source skin exceeds bound")
    armature_mods = [mod for mod in obj.modifiers if mod.type == "ARMATURE"]
    if projected.skin_bones:
        _require(len(armature_mods) > 0 and armature_mods[0].object is not None,
                 "source skin armature missing")
        arm = armature_mods[0].object
        _require(arm.name == "D11T_Rig.005", "source skin armature differs")
    binds = []
    for bone in projected.skin_bones:
        pose_bone = arm.pose.bones.get(bone.name)
        _require(pose_bone is not None and bone.usf_node_uid == -1,
                 "SDK source bone projection differs")
        matrix = convert_to_saber_transform(arm.matrix_world @ pose_bone.matrix)
        binds.append({"sourceId": bone.usf_node_source_id,
                      "inverse": _flatten(matrix.inverted())})
    return binds


def run_readback(*, blend: Path, repaired: Path, native: Path,
                 worklist: Path, sdk_root: Path, worker_sha256: str,
                 mapper_sha256: str, host_sha256: str,
                 blender_sha256: str, native_sha256: str,
                 summary_sha256: str) -> dict:
    _require(blender_sha256 in BLENDER_VERSION_PINS, "Blender pin not reviewed")
    require_hash(Path(bpy.app.binary_path), blender_sha256, "Blender executable")
    require_hash(Path(__file__), worker_sha256, "bind worker")
    host = Path(__file__).with_name("blender_bind_identity.py")
    require_hash(host, host_sha256, "bind host")
    mapper = Path(__file__).with_name("blender_mesh_inventory_worker.py")
    _require(mapper_sha256 == MAPPER_WORKER_SHA256, "mapper pin differs")
    require_hash(mapper, mapper_sha256, "mapper")
    require_hash(blend, BLEND_SHA256, "source Blend")
    require_hash(repaired, USF_SHA256, "repaired USF")
    require_hash(native, native_sha256, "retained native USF")
    require_hash(worklist, WORKLIST_SHA256, "worklist")
    sdk = require_sdk_pins(sdk_root)
    _require(bpy.app.version_string.startswith(BLENDER_VERSION_PINS[blender_sha256]),
             "Blender version differs")
    evidence = json.loads(worklist.read_text(encoding="utf-8"))
    assets = [x for x in evidence["assets"] if x.get("asset") == "cat_d11t"]
    _require(len(assets) == 1, "base worklist asset not unique")
    asset = assets[0]
    _require(asset.get("blendSha256") == BLEND_SHA256 and
             asset.get("repairedUsfSha256") == USF_SHA256 and
             asset.get("scratchNativeUsfSha256") == native_sha256 and
             asset.get("summarySha256") == summary_sha256 and
             asset.get("nativeBlendExportApproved") is False,
             "worklist pins or blocked gate differ")
    summary = require_hash(Path(asset["summaryPath"]), summary_sha256,
                           "base parity summary")
    summary_data = json.loads(summary.read_text(encoding="utf-8"))
    _require(Path(summary_data["candidateUsfPath"]) == native and
             summary_data["candidateUsfSha256"] == native_sha256 and
             summary_data["nativeBlendExportApproved"] is False,
             "retained native summary differs")
    gaps = sorted(asset["findings"]["changedMeshNodes"],
                  key=lambda row: row["path"])
    paths = [row["path"] for row in gaps]
    _require(len(paths) == len(set(paths)) == 126,
             "mapped mesh gap coverage differs")

    sys.path.insert(0, str(sdk))
    from saber.blender.lib.binary_io import BinaryIO
    from saber.blender.lib.usf.transform import convert_to_saber_transform

    original_reader = BinaryIO.read_bytearray
    BinaryIO.read_bytearray = (
        lambda self, size=None: self.io.read(size) if size is not None
        else original_reader(self)
    )
    try:
        native_root, native_rows = _usf_bind_rows(native, set(paths))
        repaired_root, repaired_rows = _usf_bind_rows(repaired, set(paths))
    finally:
        BinaryIO.read_bytearray = original_reader

    bpy.ops.wm.open_mainfile(filepath=str(blend), load_ui=False)
    _require(bpy.context.scene.frame_current == 1, "source frame differs")
    scene_meshes = {obj.name: obj for obj in bpy.context.scene.objects
                    if obj.type == "MESH"}
    _require(len(scene_meshes) == 210, "source scene mesh count differs")
    used = set()
    rows = []
    for gap in gaps:
        path = gap["path"]
        obj = _source_object(path)
        _require(obj is not None and _predicted_path(obj) == path and
                 scene_meshes.get(obj.name) == obj and obj.visible_get() and
                 obj.name not in used,
                 f"source mesh mapping differs: {path}")
        used.add(obj.name)
        source = _source_binds(obj, convert_to_saber_transform)
        n = native_rows[path]
        r = repaired_rows[path]
        _require(len(n["binds"]) == gap["nativeExportSkinBoneUidCount"] and
                 len(r["binds"]) == gap["repairedSkinBoneUidCount"],
                 f"USF skin counts differ from worklist: {path}")
        rows.append({
            "path": path, "sourceObject": obj.name,
            "sourceNative": compare_binds(source, n["binds"]),
            "sourceRepaired": compare_binds(source, r["binds"]),
            "nativeSelfMaxElementError": n["selfError"],
            "repairedSelfMaxElementError": r["selfError"],
        })
    for path, digest, label in (
            (blend, BLEND_SHA256, "Blend"), (repaired, USF_SHA256, "repaired USF"),
            (native, native_sha256, "native USF"),
            (worklist, WORKLIST_SHA256, "worklist"),
            (summary, summary_sha256, "summary"),
            (host, host_sha256, "host"),
            (Path(__file__), worker_sha256, "worker"),
            (mapper, mapper_sha256, "mapper")):
        require_hash(path, digest, label + " after readback")
    require_sdk_pins(sdk)
    return {
        "schemaVersion": 1, "asset": "cat_d11t",
        "blendSha256": BLEND_SHA256, "repairedUsfSha256": USF_SHA256,
        "nativeExportUsfSha256": native_sha256,
        "worklistSha256": WORKLIST_SHA256, "summarySha256": summary_sha256,
        "blenderSha256": blender_sha256, "hostSha256": host_sha256,
        "mapperWorkerSha256": mapper_sha256,
        "blenderVersion": bpy.app.version_string,
        "sceneFrame": bpy.context.scene.frame_current,
        "sourceSceneMeshCount": len(scene_meshes),
        "nativeExportRootName": native_root,
        "repairedRootName": repaired_root,
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
