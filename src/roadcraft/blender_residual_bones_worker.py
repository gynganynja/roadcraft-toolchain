"""Pinned, no-save reconstruction of seven absent D11 structural bones."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roadcraft.blender_armature_parity import compare_static_armature  # noqa: E402
from roadcraft.blender_blade_roll import WORKER_SHA256 as ROLL_SHA  # noqa: E402
from roadcraft.blender_blade_roll_worker import run as roll_run  # noqa: E402
from roadcraft.blender_ladder import (  # noqa: E402
    BLEND_SHA256, BLENDER_VERSION_PINS, USF_SHA256,
    WORKER_SHA256 as LADDER_SHA, require_hash, require_sdk_pins,
    validate_result as validate_ladder)
from roadcraft.blender_ladder_worker import run as ladder_run  # noqa: E402
from roadcraft.blender_push_branches import WORKER_SHA256 as PUSH_SHA  # noqa: E402
from roadcraft.blender_push_branches_worker import (  # noqa: E402
    flatten, repaired_paths, source_paths, unique_node,
    run as push_run)
from roadcraft.blender_residual_bones import (  # noqa: E402
    RESULT_PREFIX, ResidualBonesError)


ARMATURE = "D11T_Rig.005"
CHASSIS = "BoneChassis_cdt"
PREFIX = ("@root", ARMATURE, CHASSIS)
SPECS = (
    ("IK_lift_left_base", "d11t_light_inner_L"),
    ("IK_lift_right_base", "d11t_light_inner_R"),
    (CHASSIS, "ctrl_dash_v5_coolant"),
    (CHASSIS, "ctrl_dash_v5_fuel"),
    (CHASSIS, "ctrl_dash_v5_hyd_temp"),
    (CHASSIS, "ctrl_dash_v5_tach"),
    (CHASSIS, "ctrl_dash_v5_trans_temp"),
)
TOLERANCE = 1e-5


def need(condition: bool, message: str) -> None:
    if not condition:
        raise ResidualBonesError(message)


def run(*, blend: Path, usf: Path, sdk_root: Path,
        worker_sha256: str, blender_sha256: str) -> dict:
    need(blender_sha256 in BLENDER_VERSION_PINS,
         "Blender executable pin is not reviewed")
    require_hash(Path(bpy.app.binary_path), blender_sha256,
                 "Blender executable")
    require_hash(Path(__file__), worker_sha256, "residual-bones worker")
    require_hash(blend, BLEND_SHA256, "source Blend")
    require_hash(usf, USF_SHA256, "repaired USF")
    sdk = require_sdk_pins(sdk_root)
    need(bpy.app.version_string.startswith(BLENDER_VERSION_PINS[blender_sha256]),
         "Blender version differs")

    push = push_run(blend=blend, usf=usf, sdk_root=sdk,
                    worker_sha256=PUSH_SHA, blender_sha256=blender_sha256)
    need(push["status"] == "IN_MEMORY_PUSH_BRANCH_MATCH",
         "push branches did not match")
    roll = roll_run(blend=blend, usf=usf, sdk_root=sdk,
                    worker_sha256=ROLL_SHA, blender_sha256=blender_sha256,
                    loaded_scene=True, push_branches_present=True)
    need(roll["status"] == "IN_MEMORY_BLADE_ROLL_MATCH",
         "blade roll did not match")
    ladder = ladder_run(blend=blend, usf=usf, sdk_root=sdk,
                        worker_sha256=LADDER_SHA,
                        blender_sha256=blender_sha256,
                        loaded_scene=True, push_and_roll_present=True)
    validate_ladder(ladder, blender_sha256, push_and_roll_present=True)
    need(ladder["status"] == "IN_MEMORY_LADDER_MATCH",
         "access ladder did not match")

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
    arm = bpy.data.objects.get(ARMATURE)
    need(arm is not None and arm.type == "ARMATURE" and
         bpy.context.scene.frame_current == 1,
         "source armature or frame differs")
    sfx = bpy.data.objects.get("sfx")
    need(sfx is not None and sfx.type == "EMPTY" and sfx.parent == arm and
         sfx.parent_type == "BONE" and sfx.parent_bone == CHASSIS and
         not sfx.children,
         "source sfx Empty differs")
    sfx_path = "|".join(("",) + PREFIX + ("sfx",))
    repaired_sfx = unique_node(root, PREFIX + ("sfx",))
    need(repaired_sfx.mesh is None and repaired_sfx.anim is None and
         not repaired_sfx.children,
         "repaired sfx shape differs")
    meshes_before = {obj.name: tuple(flatten(obj.matrix_world))
                     for obj in bpy.context.scene.objects if obj.type == "MESH"}
    need(len(meshes_before) == 210, "source mesh count differs")
    before = source_paths(arm, convert_to_saber_transform)
    baseline = compare_static_armature(before, repaired)
    need((len(before), baseline["sharedPathCount"],
          baseline["sourceOnlyPaths"],
          baseline["repairedOnlyPaths"]) ==
         (392, 392, [], ladder["afterRepairedOnlyPaths"]),
         "combined source baseline differs")

    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    target_paths = []
    for parent_name, name in SPECS:
        components = (PREFIX if parent_name == CHASSIS
                      else PREFIX + (parent_name,)) + (name,)
        node = unique_node(root, components)
        need(node.mesh is None and node.anim is None and not node.children,
             f"repaired node shape differs: {name}")
        need(arm.pose.bones.get(name) is None and
             bpy.context.scene.objects.get(name) is None,
             f"source node already exists: {name}")
        parent = arm.pose.bones.get(parent_name)
        need(parent is not None, f"source parent is missing: {parent_name}")
        desired_world = FROM_SABER_CONVERT @ node.matrix_world @ TO_SABER_CONVERT
        desired_armature = arm.matrix_world.inverted() @ desired_world
        rest = (parent.bone.matrix_local @ parent.matrix.inverted() @
                desired_armature)
        bpy.ops.object.mode_set(mode="EDIT")
        edit = arm.data.edit_bones
        bone = edit.new(name)
        bone.length = 0.25  # USF omits Blender edit-bone length.
        bone.parent = edit[parent_name]
        bone.matrix = rest
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.context.view_layer.update()
        target_paths.append("|".join(("",) + components))

    after = source_paths(arm, convert_to_saber_transform)
    sfx_matrix = flatten(convert_to_saber_transform(sfx.matrix_world))
    need(sfx_path not in after, "sfx became a pose bone")
    with_empty = {**after, sfx_path: sfx_matrix}
    comparison = compare_static_armature(with_empty, repaired)
    targets = [
        {"path": path,
         "maxElementError": max(abs(a - b) for a, b in
                                zip(after[path], repaired[path], strict=True))}
        for path in target_paths]
    sfx_error = max(abs(a - b) for a, b in
                    zip(sfx_matrix, repaired[sfx_path], strict=True))
    meshes_after = {obj.name: tuple(flatten(obj.matrix_world))
                    for obj in bpy.context.scene.objects if obj.type == "MESH"}
    need(meshes_after.keys() == meshes_before.keys(),
         "source mesh roster changed")
    mesh_error = max(abs(a - b) for name in meshes_before
                     for a, b in zip(meshes_before[name], meshes_after[name],
                                     strict=True))
    require_hash(blend, BLEND_SHA256, "source Blend after diagnostic")
    require_hash(usf, USF_SHA256, "repaired USF after diagnostic")
    require_sdk_pins(sdk)
    require_hash(Path(__file__), worker_sha256,
                 "residual-bones worker after diagnostic")
    matched = (
        len(after) == 399 and len(with_empty) == 400 and
        comparison["sharedPathCount"] == 400 and
        comparison["sourceOnlyPaths"] == [] and
        comparison["repairedOnlyPaths"] == [] and
        comparison["changedMatrixCount"] == 0 and
        comparison["maxSharedMatrixError"] <= TOLERANCE and
        sfx_error <= TOLERANCE and mesh_error <= TOLERANCE and
        all(row["maxElementError"] <= TOLERANCE for row in targets))
    return {
        "schemaVersion": 1,
        "status": ("IN_MEMORY_STRUCTURAL_MATCH" if matched else
                   "IN_MEMORY_STRUCTURAL_DIFFERENT"),
        "asset": "cat_d11t", "blendSha256": BLEND_SHA256,
        "repairedUsfSha256": USF_SHA256,
        "blenderSha256": blender_sha256,
        "blenderVersion": bpy.app.version_string,
        "sceneFrame": bpy.context.scene.frame_current,
        "priorRepairStatuses": [push["status"], roll["status"], ladder["status"]],
        "beforeSourceBoneCount": 392,
        "afterSourceBoneCount": len(after),
        "sourceEmptyNodeCount": 1,
        "repairedStructuralCount": len(repaired),
        "afterSharedPathCount": comparison["sharedPathCount"],
        "afterSourceOnlyPaths": comparison["sourceOnlyPaths"],
        "afterRepairedOnlyPaths": comparison["repairedOnlyPaths"],
        "afterChangedMatrixCount": comparison["changedMatrixCount"],
        "afterMaxSharedMatrixError": comparison["maxSharedMatrixError"],
        "targetMatrixErrors": targets,
        "sfxSourceKind": "bone-parented EMPTY",
        "sfxSourceMatrixError": sfx_error,
        "sourceMeshCount": len(meshes_before),
        "meshWorldError": mesh_error,
        "newBoneEditLength": 0.25,
        "editLengthFromUsf": False,
        "blendSaved": False, "usfExported": False,
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
