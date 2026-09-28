"""Blender-side, no-save static readback of D11 blade collision meshes."""

from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roadcraft.blender_blade_relocation import (  # noqa: E402
    BLEND_SHA256, BLENDER_VERSION_PINS, LEAVES, NATIVE_PARENT,
    REPAIRED_PARENT, RESULT_PREFIX, USF_SHA256, WORKLIST_SHA256,
    BladeRelocationError, require_hash, require_sdk_pins,
)


ARMATURE = "D11T_Rig.005"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BladeRelocationError(message)


def _flatten(matrix) -> list[float]:
    return [float(matrix[row][col]) for row in range(4) for col in range(4)]


def _usf_mesh_counts(mesh) -> dict:
    return {
        "vertices": len(mesh.vertices),
        "faces": len(mesh.faces),
        "normals": len(mesh.normals),
        "materialSlots": len(mesh.materials.data),
        "uvSets": len(mesh.uvsets.uvs),
        "colorSets": len(mesh.colorsets.sets),
        "skinEntries": len(mesh.skin.skin),
        "skinBones": len(mesh.skin.skin_bones),
    }


def _usf_nodes(usf: Path, paths: set[str]) -> tuple[str, dict[str, dict]]:
    from saber.blender.lib.usf.scene import usf_read

    _, scene = usf_read(str(usf))
    root = scene._root_node
    _require(root.name == "cat_d11t", f"USF root differs: {usf.name}")
    found = {}
    stack = [(root, "|@root")]
    while stack:
        node, path = stack.pop()
        if path in paths:
            _require(path not in found, f"duplicate USF path {path}")
            _require(node.mesh is not None, f"USF relocated node is not a mesh: {path}")
            found[path] = {
                "path": path,
                "worldMatrixSaber": _flatten(node.matrix_world),
                "localMatrixSaber": _flatten(node.matrix_local),
                "mesh": _usf_mesh_counts(node.mesh),
            }
        for child in node.children:
            stack.append((child, path + "|" + child.name))
    _require(set(found) == paths, f"USF relocation path coverage differs: {usf.name}")
    del scene, root
    gc.collect()
    return "cat_d11t", found


def _source_object(obj, depsgraph, convert_to_saber_transform) -> dict:
    _require(obj is not None and obj.type == "MESH", "source blade mesh is missing")
    _require(bpy.context.scene.objects.get(obj.name) == obj,
             f"source mesh is outside scene: {obj.name}")
    _require(obj.visible_get(), f"source mesh is hidden: {obj.name}")
    _require(obj.parent is not None and obj.parent.name == ARMATURE and
             obj.parent.type == "ARMATURE" and obj.parent_type == "BONE" and
             obj.parent_bone == "BoneBlade_cdt",
             f"source blade parent differs: {obj.name}")
    _require(bpy.context.scene.collection.objects.get(obj.parent.name) == obj.parent
             and obj.parent.visible_get(),
             f"source armature root is not directly visible: {obj.name}")
    bone = obj.parent.pose.bones.get(obj.parent_bone)
    _require(bone is not None, f"source blade parent bone is missing: {obj.name}")
    lineage = []
    while bone is not None:
        lineage.append(bone.name)
        bone = bone.parent
    lineage.reverse()
    predicted = "|@root|" + ARMATURE + "|" + "|".join(lineage) + "|" + obj.name
    _require(predicted == NATIVE_PARENT + "|" + obj.name,
             f"source blade hierarchy differs: {obj.name}")
    raw = obj.data
    raw.calc_loop_triangles()
    evaluated_obj = obj.evaluated_get(depsgraph)
    evaluated = evaluated_obj.to_mesh()
    _require(evaluated is not None, f"evaluated blade mesh is missing: {obj.name}")
    try:
        evaluated.calc_loop_triangles()
        mesh = {
            "rawVertices": len(raw.vertices),
            "rawPolygons": len(raw.polygons),
            "rawTriangles": len(raw.loop_triangles),
            "evaluatedVertices": len(evaluated.vertices),
            "evaluatedTriangles": len(evaluated.loop_triangles),
            "materialSlots": len(evaluated.materials) or 1,
            "uvSets": len(evaluated.uv_layers),
            "colorSets": len(evaluated.color_attributes) + sum(
                attr.name.startswith("saber_colorset_idx_")
                for attr in evaluated.attributes),
            "vertexGroups": len(obj.vertex_groups),
            "armatureModifiers": sum(mod.type == "ARMATURE" for mod in obj.modifiers),
        }
    finally:
        evaluated_obj.to_mesh_clear()
    return {
        "objectName": obj.name,
        "objectType": obj.type,
        "parentObject": obj.parent.name,
        "parentType": obj.parent_type,
        "parentBone": obj.parent_bone,
        "sourcePredictedPath": predicted,
        "visible": True,
        "worldMatrixSaber": _flatten(convert_to_saber_transform(obj.matrix_world)),
        "mesh": mesh,
    }


def run_readback(*, blend: Path, repaired: Path, native: Path, worklist: Path,
                 sdk_root: Path, worker_sha256: str, blender_sha256: str,
                 native_sha256: str, summary_sha256: str) -> dict:
    _require(blender_sha256 in BLENDER_VERSION_PINS, "Blender pin is not reviewed")
    require_hash(Path(bpy.app.binary_path), blender_sha256, "Blender executable")
    require_hash(Path(__file__), worker_sha256, "blade relocation worker")
    require_hash(blend, BLEND_SHA256, "source Blend")
    require_hash(repaired, USF_SHA256, "repaired USF")
    require_hash(native, native_sha256, "retained native USF")
    require_hash(worklist, WORKLIST_SHA256, "reconstruction worklist")
    sdk = require_sdk_pins(sdk_root)
    _require(bpy.app.version_string.startswith(BLENDER_VERSION_PINS[blender_sha256]),
             "Blender version differs")

    sys.path.insert(0, str(sdk))
    from saber.blender.lib.binary_io import BinaryIO
    from saber.blender.lib.usf.transform import convert_to_saber_transform

    # The retained SDK reader needs this in-process byte-array shim for these
    # pinned USFs. The SDK files and input assets remain unchanged.
    original_reader = BinaryIO.read_bytearray
    BinaryIO.read_bytearray = (
        lambda self, size=None: self.io.read(size) if size is not None
        else original_reader(self)
    )
    native_paths = {NATIVE_PARENT + "|" + leaf for leaf in LEAVES}
    repaired_paths = {REPAIRED_PARENT + "|" + leaf for leaf in LEAVES}
    try:
        native_root, native_nodes = _usf_nodes(native, native_paths)
        repaired_root, repaired_nodes = _usf_nodes(repaired, repaired_paths)
    finally:
        BinaryIO.read_bytearray = original_reader

    bpy.ops.wm.open_mainfile(filepath=str(blend), load_ui=False)
    _require(bpy.context.scene.frame_current == 1, "source scene frame differs")
    scene_meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    _require(len(scene_meshes) == 210, "source scene mesh count differs")
    depsgraph = bpy.context.evaluated_depsgraph_get()
    rows = []
    for leaf in LEAVES:
        source = _source_object(bpy.data.objects.get(leaf), depsgraph,
                                convert_to_saber_transform)
        rows.append({
            "leafName": leaf,
            "nativeExportPath": NATIVE_PARENT + "|" + leaf,
            "repairedPath": REPAIRED_PARENT + "|" + leaf,
            "equivalenceVerified": False,
            "source": source,
            "nativeExportNode": native_nodes[NATIVE_PARENT + "|" + leaf],
            "repairedNode": repaired_nodes[REPAIRED_PARENT + "|" + leaf],
        })
    require_hash(blend, BLEND_SHA256, "source Blend after readback")
    require_hash(repaired, USF_SHA256, "repaired USF after readback")
    require_hash(native, native_sha256, "retained native USF after readback")
    require_hash(worklist, WORKLIST_SHA256, "worklist after readback")
    require_sdk_pins(sdk)
    return {
        "schemaVersion": 1,
        "asset": "cat_d11t",
        "blendSha256": BLEND_SHA256,
        "repairedUsfSha256": USF_SHA256,
        "nativeExportUsfSha256": native_sha256,
        "worklistSha256": WORKLIST_SHA256,
        "summarySha256": summary_sha256,
        "blenderSha256": blender_sha256,
        "blenderVersion": bpy.app.version_string,
        "sceneFrame": bpy.context.scene.frame_current,
        "sourceSceneMeshCount": len(scene_meshes),
        "nativeExportRootName": native_root,
        "repairedRootName": repaired_root,
        "blendSaved": False,
        "usfExported": False,
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
    parser.add_argument("--blender-sha256", required=True)
    parser.add_argument("--native-usf-sha256", required=True)
    parser.add_argument("--summary-sha256", required=True)
    args = parser.parse_args(argv)
    result = run_readback(
        blend=args.blend, repaired=args.repaired_usf, native=args.native_usf,
        worklist=args.worklist, sdk_root=args.sdk_script_root,
        worker_sha256=args.worker_sha256, blender_sha256=args.blender_sha256,
        native_sha256=args.native_usf_sha256,
        summary_sha256=args.summary_sha256)
    print(RESULT_PREFIX + json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
