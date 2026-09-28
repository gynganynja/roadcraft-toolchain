"""Blender-side, no-save source mesh readback for the pinned D11 base Blend."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roadcraft.blender_mesh_inventory import (  # noqa: E402
    BLEND_SHA256, BLENDER_VERSION_PINS, RESULT_PREFIX, USF_SHA256,
    WORKLIST_SHA256, MeshInventoryError, require_hash, require_sdk_pins,
)


ARMATURE = "D11T_Rig.005"
LOD_CHILD = re.compile(r"^(.*)_LOD([1-9][0-9]*)$")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise MeshInventoryError(message)


def _source_object(path: str):
    leaf = path.rsplit("|", 1)[-1]
    names = [leaf] if LOD_CHILD.fullmatch(leaf) else [leaf, leaf + "_LOD0"]
    matches = [bpy.data.objects[name] for name in names
               if name in bpy.data.objects and bpy.data.objects[name].type == "MESH"]
    return matches[0] if len(matches) == 1 else None


def _parent_prefix(obj) -> str | None:
    parent = obj.parent
    if parent is None:
        # The SDK first visits scene-root collections; a nested collection
        # would add another structural node before this object.
        return ("|@root" if bpy.context.scene.collection.objects.get(obj.name) == obj
                else None)
    if parent.type != "ARMATURE" or parent.name != ARMATURE:
        return None
    if (bpy.context.scene.collection.objects.get(parent.name) != parent or
            not parent.visible_get()):
        return None
    prefix = "|@root|" + ARMATURE
    if obj.parent_type == "BONE" and obj.parent_bone:
        bone = parent.pose.bones.get(obj.parent_bone)
        if bone is None:
            return None
        lineage = []
        while bone is not None:
            lineage.append(bone.name)
            bone = bone.parent
        prefix += "|" + "|".join(reversed(lineage))
    return prefix


def _predicted_path(obj) -> str | None:
    """Reconstruct only the SDK's direct-parent and flat-LOD path cases."""
    prefix = _parent_prefix(obj)
    if prefix is None:
        return None
    name = obj.name
    if obj.parent is None and not obj.visible_get():
        return None
    if name.endswith("_LOD0"):
        return prefix + "|" + name[:-5]
    child = LOD_CHILD.fullmatch(name)
    if child:
        # _process_lod_flat reparents LOD1+ only when a same-parent LOD0
        # exists; _LOD_GRP follows a different SDK branch.
        lod0 = bpy.data.objects.get(child.group(1) + "_LOD0")
        if (lod0 is None or lod0.type != "MESH" or
                lod0.parent != obj.parent or lod0.parent_type != obj.parent_type or
                lod0.parent_bone != obj.parent_bone or
                obj.parent is not None and obj.parent.name.endswith("_LOD_GRP") or
                lod0.parent is None and not lod0.visible_get()):
            return None
        return prefix + "|" + child.group(1) + "|" + name
    return prefix + "|" + name


def _mesh_facts(obj, depsgraph) -> dict:
    raw = obj.data
    raw.calc_loop_triangles()
    armature_modifiers = [mod for mod in obj.modifiers if mod.type == "ARMATURE"]
    first_armature = armature_modifiers[0].object if armature_modifiers else None
    first_bone_count = (len(first_armature.pose.bones)
                        if first_armature and first_armature.pose else 0)
    weighted_vertices = sum(bool(vertex.groups) for vertex in raw.vertices)
    group_names = sorted(group.name for group in obj.vertex_groups)
    evaluated_object = obj.evaluated_get(depsgraph)
    evaluated = evaluated_object.to_mesh()
    _require(evaluated is not None, f"evaluated mesh is missing: {obj.name}")
    try:
        evaluated.calc_loop_triangles()
        triangles = len(evaluated.loop_triangles)
        materials = [mat.name if mat else "blender_default"
                     for mat in evaluated.materials]
        normal_attr = evaluated.attributes.get("saber_normals")
        custom_color_names = sorted(attr.name for attr in evaluated.attributes
                                    if attr.name.startswith("saber_colorset_idx_"))
        return {
            "rawVertices": len(raw.vertices),
            "rawPolygons": len(raw.polygons),
            "rawTriangles": len(raw.loop_triangles),
            "evaluatedVertices": len(evaluated.vertices),
            "evaluatedPolygons": len(evaluated.polygons),
            "evaluatedTriangles": triangles,
            "evaluatedMaterialNames": materials,
            "evaluatedUvNames": [layer.name for layer in evaluated.uv_layers],
            "evaluatedColorNames": [layer.name for layer in evaluated.color_attributes],
            "evaluatedCustomColorNames": custom_color_names,
            "saberNormalsCount": len(normal_attr.data) if normal_attr else None,
            "armatureModifierCount": len(armature_modifiers),
            "firstArmatureTarget": first_armature.name if first_armature else None,
            "firstArmaturePoseBoneCount": first_bone_count,
            "vertexGroupNames": group_names,
            "weightedRawVertices": weighted_vertices,
            "sdkExpectedVertices": triangles * 3,
            "sdkExpectedFaces": triangles,
            "sdkExpectedNormals": (len(normal_attr.data)
                                   if normal_attr else triangles * 3),
            "sdkExpectedUvSets": len(evaluated.uv_layers),
            "sdkExpectedColorSets": (len(evaluated.color_attributes) +
                                      len(custom_color_names)),
            "sdkExpectedMaterialSlots": len(materials) or 1,
            "sdkExpectedSkinEntries": (triangles * 3
                                       if first_bone_count and weighted_vertices else 0),
            "sdkExpectedSkinBones": (first_bone_count
                                     if first_bone_count and weighted_vertices else 0),
        }
    finally:
        evaluated_object.to_mesh_clear()


def run_readback(*, blend: Path, usf: Path, worklist: Path, sdk_root: Path,
                 worker_sha256: str, blender_sha256: str) -> dict:
    _require(blender_sha256 in BLENDER_VERSION_PINS, "Blender pin is not reviewed")
    require_hash(Path(bpy.app.binary_path), blender_sha256, "Blender executable")
    require_hash(Path(__file__), worker_sha256, "mesh inventory worker")
    require_hash(blend, BLEND_SHA256, "source Blend")
    require_hash(usf, USF_SHA256, "repaired USF")
    require_hash(worklist, WORKLIST_SHA256, "reconstruction worklist")
    sdk = require_sdk_pins(sdk_root)
    _require(bpy.app.version_string.startswith(BLENDER_VERSION_PINS[blender_sha256]),
             "Blender version differs")
    evidence = json.loads(worklist.read_text(encoding="utf-8"))
    assets = [asset for asset in evidence["assets"] if asset["asset"] == "cat_d11t"]
    _require(len(assets) == 1, "worklist has no unique base asset")
    paths = sorted(row["path"] for row in assets[0]["findings"]["changedMeshNodes"])
    _require(len(paths) == len(set(paths)) == 126, "worklist mesh coverage differs")

    bpy.ops.wm.open_mainfile(filepath=str(blend), load_ui=False)
    _require(bpy.context.scene.frame_current == 1, "source scene frame differs")
    scene_meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    _require(len(scene_meshes) == 210, "source scene mesh count differs")
    depsgraph = bpy.context.evaluated_depsgraph_get()
    rows = []
    for path in paths:
        obj = _source_object(path)
        predicted = _predicted_path(obj) if obj is not None else None
        mapped = bool(obj is not None and predicted == path and obj in scene_meshes)
        rows.append({
            "path": path,
            "sourceObject": obj.name if obj else None,
            "predictedSdkPath": predicted,
            "mappingStatus": "SDK_PATH_RECONSTRUCTED" if mapped else "UNMAPPED",
            "parentObject": obj.parent.name if obj and obj.parent else None,
            "parentBone": obj.parent_bone if obj else None,
            "parentType": obj.parent_type if obj else None,
            "sourceVisible": bool(obj.visible_get()) if obj else None,
            "facts": _mesh_facts(obj, depsgraph) if mapped else None,
        })
    require_hash(blend, BLEND_SHA256, "source Blend after readback")
    require_hash(usf, USF_SHA256, "repaired USF after readback")
    require_hash(worklist, WORKLIST_SHA256, "reconstruction worklist after readback")
    require_sdk_pins(sdk)
    return {
        "schemaVersion": 1,
        "asset": "cat_d11t",
        "blendSha256": BLEND_SHA256,
        "repairedUsfSha256": USF_SHA256,
        "worklistSha256": WORKLIST_SHA256,
        "blenderSha256": blender_sha256,
        "blenderVersion": bpy.app.version_string,
        "sceneFrame": bpy.context.scene.frame_current,
        "sceneMeshObjects": len(scene_meshes),
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
    parser.add_argument("--worklist", type=Path, required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--worker-sha256", required=True)
    parser.add_argument("--blender-sha256", required=True)
    args = parser.parse_args(argv)
    result = run_readback(
        blend=args.blend, usf=args.repaired_usf, worklist=args.worklist,
        sdk_root=args.sdk_script_root, worker_sha256=args.worker_sha256,
        blender_sha256=args.blender_sha256)
    print(RESULT_PREFIX + json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
