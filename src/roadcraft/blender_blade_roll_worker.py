"""Pinned, no-save D11 blade-roll hierarchy and mesh-transform diagnostic."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roadcraft.blender_blade_roll import (  # noqa: E402
    BLEND_SHA256, BLENDER_VERSION_PINS, RESULT_PREFIX, USF_SHA256,
    BladeRollError, require_hash, require_sdk_pins,
)
from roadcraft.blender_armature_parity import compare_static_armature  # noqa: E402
from roadcraft.blender_push_branches_worker import (  # noqa: E402
    chain, matrix_error, repaired_paths, source_paths, unique_node,
)


ARMATURE = "D11T_Rig.005"
CHASSIS = "BoneChassis_cdt"
LIFT = "BoneBladeLift_cdt"
ROLL = "BoneBladeRoll_cdt"
BLADE = "BoneBlade_cdt"
PREFIX = ("@root", ARMATURE, CHASSIS, LIFT)
PATH = "|".join(("",) + PREFIX)
TOLERANCE = 1e-5


def need(condition: bool, message: str) -> None:
    if not condition:
        raise BladeRollError(message)


def _max_flat_error(left: list[float], right: list[float]) -> float:
    return max(abs(a - b) for a, b in zip(left, right, strict=True))


def run(*, blend: Path, usf: Path, sdk_root: Path,
        worker_sha256: str, blender_sha256: str,
        loaded_scene: bool = False, push_branches_present: bool = False) -> dict:
    need(blender_sha256 in BLENDER_VERSION_PINS,
         "Blender executable pin is not reviewed")
    require_hash(Path(bpy.app.binary_path), blender_sha256, "Blender executable")
    require_hash(Path(__file__), worker_sha256, "blade-roll worker")
    blend = require_hash(blend, BLEND_SHA256, "source Blend")
    usf = require_hash(usf, USF_SHA256, "repaired USF")
    sdk = require_sdk_pins(sdk_root)
    need(bpy.app.version_string.startswith(BLENDER_VERSION_PINS[blender_sha256]),
         "Blender version differs")

    sys.path.insert(0, str(sdk))
    from saber.blender.lib.binary_io import BinaryIO
    from saber.blender.lib.usf.scene import usf_read
    from saber.blender.lib.usf.transform import (
        FROM_SABER_CONVERT, TO_SABER_CONVERT, convert_to_saber_transform)

    reader = BinaryIO.read_bytearray
    BinaryIO.read_bytearray = (
        lambda self, size=None: self.io.read(size) if size is not None
        else reader(self))
    try:
        _, parsed = usf_read(str(usf))
    finally:
        BinaryIO.read_bytearray = reader
    root = parsed._root_node
    repaired = repaired_paths(root)
    need(len(repaired) == 400, "repaired structural coverage differs")
    roll_node = unique_node(root, PREFIX + (ROLL,))
    blade_node = unique_node(root, PREFIX + (ROLL, BLADE))
    need(roll_node.mesh is None and roll_node.anim is None and
         sorted(child.name for child in roll_node.children) ==
         [BLADE, "cdt_blade_roll_pivot"],
         "repaired blade-roll node differs")
    mesh_nodes = {}
    for index in range(60):
        name = f"cdt_blade_{index}"
        node = unique_node(root, PREFIX + (ROLL, BLADE, name))
        need(node.mesh is not None, f"repaired blade mesh differs: {name}")
        mesh_nodes[name] = node
    need(sorted(child.name for child in blade_node.children) ==
         sorted(mesh_nodes), "repaired blade child roster differs")

    if loaded_scene:
        need(Path(bpy.data.filepath).resolve() == blend.resolve(),
             "loaded scene is not the pinned source Blend")
    else:
        need(not push_branches_present,
             "push branches require an explicitly loaded scene")
        bpy.ops.wm.open_mainfile(filepath=str(blend), load_ui=False)
    arms = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    need(len(arms) == 1 and arms[0].name == ARMATURE,
         "source armature is not unique")
    need(bpy.context.scene.frame_current == 1, "source frame differs")
    arm = arms[0]
    before = source_paths(arm, convert_to_saber_transform)
    baseline = compare_static_armature(before, repaired)
    expected_baseline = ((388, 386, 2, 14, 0) if push_branches_present else
                         (384, 378, 6, 22, 0))
    need((len(before), baseline["sharedPathCount"],
          len(baseline["sourceOnlyPaths"]),
          len(baseline["repairedOnlyPaths"]),
          baseline["changedMatrixCount"]) == expected_baseline,
         "source static baseline differs")
    lift = arm.pose.bones.get(LIFT)
    blade = arm.pose.bones.get(BLADE)
    need(lift is not None and chain(lift) == [CHASSIS, LIFT] and
         blade is not None and chain(blade) == [CHASSIS, LIFT, BLADE] and
         not blade.constraints and not blade.bone.use_connect and
         not blade.children and arm.pose.bones.get(ROLL) is None,
         "source blade hierarchy differs")
    need(sum(obj.type == "MESH" for obj in bpy.context.scene.objects) == 210,
         "source scene mesh count differs")
    meshes = []
    for name in mesh_nodes:
        obj = bpy.context.scene.objects.get(name)
        need(obj is not None and obj.type == "MESH" and
             obj.parent == arm and obj.parent_type == "BONE" and
             obj.parent_bone == BLADE and obj.visible_get(),
             f"source blade mesh parent differs: {name}")
        meshes.append(obj)
    old_world = {obj.name: obj.matrix_world.copy() for obj in meshes}
    before_mesh_error = max(
        matrix_error(convert_to_saber_transform(obj.matrix_world),
                     mesh_nodes[obj.name].matrix_world) for obj in meshes)
    need(before_mesh_error <= TOLERANCE,
         "source blade mesh world placement differs")

    def desired_armature(node):
        world = FROM_SABER_CONVERT @ node.matrix_world @ TO_SABER_CONVERT
        return arm.matrix_world.inverted() @ world

    roll_rest = (lift.bone.matrix_local @ lift.matrix.inverted() @
                 desired_armature(roll_node))
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    edit = arm.data.edit_bones
    lift_edit = edit.get(LIFT)
    blade_edit = edit.get(BLADE)
    need(lift_edit is not None and blade_edit is not None and
         blade_edit.parent == lift_edit,
         "source blade edit-bone parent differs")
    old_blade_rest = blade_edit.matrix.copy()
    created = edit.new(ROLL)
    created.parent = lift_edit
    created.length = 0.25  # USF does not encode edit-bone length.
    created.matrix = roll_rest
    blade_edit.parent = created
    blade_edit.matrix = old_blade_rest
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.update()

    roll = arm.pose.bones.get(ROLL)
    need(roll is not None, "new blade-roll bone is missing")
    blade_rest = (roll.bone.matrix_local @ roll.matrix.inverted() @
                  desired_armature(blade_node))
    bpy.ops.object.mode_set(mode="EDIT")
    arm.data.edit_bones[BLADE].matrix = blade_rest
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.update()
    drift_before = max(matrix_error(obj.matrix_world, old_world[obj.name])
                       for obj in meshes)
    for obj in meshes:
        obj.matrix_world = old_world[obj.name]
    bpy.context.view_layer.update()

    after = source_paths(arm, convert_to_saber_transform)
    comparison = compare_static_armature(after, repaired)
    roll_path = PATH + "|" + ROLL
    blade_path = roll_path + "|" + BLADE
    need(roll_path in after and blade_path in after and
         chain(arm.pose.bones[BLADE]) == [CHASSIS, LIFT, ROLL, BLADE],
         "in-memory blade-roll paths differ")
    targets = [
        {"path": path,
         "maxElementError": _max_flat_error(after[path], repaired[path])}
        for path in (roll_path, blade_path)
    ]
    drift_after = max(matrix_error(obj.matrix_world, old_world[obj.name])
                      for obj in meshes)
    mesh_world_error = max(
        matrix_error(convert_to_saber_transform(obj.matrix_world),
                     mesh_nodes[obj.name].matrix_world) for obj in meshes)
    blade_saber = convert_to_saber_transform(
        arm.matrix_world @ arm.pose.bones[BLADE].matrix)
    mesh_local_error = max(
        matrix_error(blade_saber.inverted() @
                     convert_to_saber_transform(obj.matrix_world),
                     mesh_nodes[obj.name].matrix_local) for obj in meshes)
    require_hash(blend, BLEND_SHA256, "source Blend after diagnostic")
    require_hash(usf, USF_SHA256, "repaired USF after diagnostic")
    require_sdk_pins(sdk)
    expected_after = ((389, 388, 1, 12) if push_branches_present else
                      (385, 380, 5, 20))
    matched = ((len(after), comparison["sharedPathCount"],
                len(comparison["sourceOnlyPaths"]),
                len(comparison["repairedOnlyPaths"])) == expected_after and
               comparison["changedMatrixCount"] == 0 and
               comparison["maxSharedMatrixError"] <= TOLERANCE and
               all(row["maxElementError"] <= TOLERANCE for row in targets) and
               drift_after <= TOLERANCE and mesh_world_error <= TOLERANCE and
               mesh_local_error <= TOLERANCE)
    return {
        "schemaVersion": 1,
        "status": ("IN_MEMORY_BLADE_ROLL_MATCH" if matched else
                   "IN_MEMORY_BLADE_ROLL_DIFFERENT"),
        "asset": "cat_d11t", "blendSha256": BLEND_SHA256,
        "repairedUsfSha256": USF_SHA256,
        "blenderSha256": blender_sha256,
        "blenderVersion": bpy.app.version_string,
        "sceneFrame": bpy.context.scene.frame_current,
        "pushBranchesPresent": push_branches_present,
        "beforeSourceBoneCount": len(before),
        "afterSourceBoneCount": len(after),
        "repairedStructuralCount": len(repaired),
        "beforeSharedPathCount": baseline["sharedPathCount"],
        "afterSharedPathCount": comparison["sharedPathCount"],
        "afterChangedMatrixCount": comparison["changedMatrixCount"],
        "afterMaxSharedMatrixError": comparison["maxSharedMatrixError"],
        "afterSourceOnlyPaths": comparison["sourceOnlyPaths"],
        "afterRepairedOnlyPaths": comparison["repairedOnlyPaths"],
        "targetMatrixErrors": targets,
        "bladeMeshCount": len(meshes),
        "beforeMeshWorldError": before_mesh_error,
        "meshDriftBeforeRestore": drift_before,
        "meshDriftAfterRestore": drift_after,
        "afterMeshWorldError": mesh_world_error,
        "afterMeshLocalError": mesh_local_error,
        "newBoneEditLength": 0.25,
        "editLengthFromUsf": False,
        "blendSaved": False,
        "usfExported": False,
        "nativeBlendExportApproved": False,
    }


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--blend", type=Path, required=True)
    parser.add_argument("--repaired-usf", type=Path, required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--worker-sha256", required=True)
    parser.add_argument("--blender-sha256", required=True)
    args = parser.parse_args(argv)
    result = run(blend=args.blend, usf=args.repaired_usf,
                 sdk_root=args.sdk_script_root,
                 worker_sha256=args.worker_sha256,
                 blender_sha256=args.blender_sha256)
    print(RESULT_PREFIX + json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
