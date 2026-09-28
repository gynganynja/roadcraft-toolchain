"""No-save reconstruction of both D11 blade push-arm branches in Blender."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roadcraft.blender_push_branches import (  # noqa: E402
    BLEND_SHA256, BLENDER_VERSION_PINS, RESULT_PREFIX, USF_SHA256,
    PushBranchesError, require_hash, require_sdk_pins,
)
from roadcraft.blender_armature_parity import compare_static_armature  # noqa: E402


ARMATURE = "D11T_Rig.005"
CHASSIS = "BoneChassis_cdt"
LIFT = "BoneBladeLift_cdt"
ROOT_PREFIX = f"|@root|{ARMATURE}|{CHASSIS}|{LIFT}"
TOLERANCE = 1e-5


def need(condition: bool, message: str) -> None:
    if not condition:
        raise PushBranchesError(message)


def matrix_error(left, right) -> float:
    return max(abs(float(left[row][col]) - float(right[row][col]))
               for row in range(4) for col in range(4))


def flatten(matrix) -> list[float]:
    return [float(matrix[row][col]) for row in range(4) for col in range(4)]


def chain(bone) -> list[str]:
    names = []
    while bone is not None:
        names.append(bone.name)
        bone = bone.parent
    return list(reversed(names))


def source_paths(arm, convert) -> dict[str, list[float]]:
    result = {}
    for bone in arm.pose.bones:
        path = "|@root|" + ARMATURE + "|" + "|".join(chain(bone))
        need(path not in result, f"duplicate source path {path}")
        result[path] = flatten(convert(arm.matrix_world @ bone.matrix))
    return result


def repaired_paths(root) -> dict[str, list[float]]:
    need(root.name == "cat_d11t", "repaired USF root differs")
    matches = [child for child in root.children if child.name == ARMATURE]
    need(len(matches) == 1, "repaired armature is not unique")
    result = {}
    stack = [(matches[0], "|@root|" + ARMATURE)]
    while stack:
        node, path = stack.pop()
        for child in node.children:
            child_path = path + "|" + child.name
            stack.append((child, child_path))
            if child.mesh is None:
                need(child_path not in result,
                     f"duplicate repaired path {child_path}")
                result[child_path] = flatten(child.matrix_world)
    return result


def unique_node(root, components: tuple[str, ...]):
    need(root.name == "cat_d11t" and components[:1] == ("@root",),
         "repaired root differs")
    node = root
    for name in components[1:]:
        matches = [child for child in node.children if child.name == name]
        need(len(matches) == 1, f"repaired path is not unique at {name}")
        node = matches[0]
    return node


def run(*, blend: Path, usf: Path, sdk_root: Path,
        worker_sha256: str, blender_sha256: str) -> dict:
    need(blender_sha256 in BLENDER_VERSION_PINS,
         "Blender executable pin is not reviewed")
    require_hash(Path(bpy.app.binary_path), blender_sha256, "Blender executable")
    require_hash(Path(__file__), worker_sha256, "push-branch worker")
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

    original_reader = BinaryIO.read_bytearray
    BinaryIO.read_bytearray = (
        lambda self, size=None: self.io.read(size) if size is not None
        else original_reader(self)
    )
    _, scene = usf_read(str(usf))
    root = scene._root_node
    repaired = repaired_paths(root)
    need(len(repaired) == 400, "repaired structural coverage differs")

    bpy.ops.wm.open_mainfile(filepath=str(blend), load_ui=False)
    arms = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    need(len(arms) == 1 and arms[0].name == ARMATURE,
         "source armature is not unique")
    need(bpy.context.scene.frame_current == 1, "source frame differs")
    arm = arms[0]
    before = source_paths(arm, convert_to_saber_transform)
    need(len(before) == 384, "source bone coverage differs")
    before_comparison = compare_static_armature(before, repaired)
    need((before_comparison["sharedPathCount"],
          len(before_comparison["sourceOnlyPaths"]),
          len(before_comparison["repairedOnlyPaths"]),
          before_comparison["changedMatrixCount"]) == (378, 6, 22, 0),
         "source static baseline differs from pinned armature readback")

    parent = arm.pose.bones.get(LIFT)
    need(parent is not None and chain(parent) == [CHASSIS, LIFT],
         "blade lift parent differs")
    targets = {}
    old_tilt_matrices = {}
    base_rest = {}
    for side in ("left", "right"):
        push_base = f"IK_push_arm_{side}_base"
        push_tip = f"IK_push_arm_{side}_tip"
        tilt_base = f"IK_tilt_{side}_base"
        tilt_tip = f"IK_tilt_{side}_tip"
        need(arm.pose.bones.get(push_base) is None and
             arm.pose.bones.get(push_tip) is None,
             f"source already has {side} push-arm bones")
        base = arm.pose.bones.get(tilt_base)
        tip = arm.pose.bones.get(tilt_tip)
        need(base is not None and tip is not None and
             base.parent == parent and tip.parent == base and
             not base.constraints and not tip.constraints and
             not base.bone.use_connect,
             f"source {side} tilt branch differs")
        old_tilt_matrices[side] = (base.matrix.copy(), tip.matrix.copy())
        node_base = unique_node(root, ("@root", ARMATURE, CHASSIS, LIFT,
                                       push_base))
        node_tip = unique_node(root, ("@root", ARMATURE, CHASSIS, LIFT,
                                      push_base, push_tip))
        need(node_base.mesh is None and node_base.anim is None and
             node_tip.mesh is None and node_tip.anim is None and
             sorted(child.name for child in node_base.children) ==
             [push_tip, tilt_base],
             f"repaired {side} push-arm structure differs")
        targets[side] = (node_base.matrix_world.copy(), node_tip.matrix_world.copy())
        desired_world = (FROM_SABER_CONVERT @ node_base.matrix_world @
                         TO_SABER_CONVERT)
        desired_armature = arm.matrix_world.inverted() @ desired_world
        base_rest[side] = (parent.bone.matrix_local @
                           parent.matrix.inverted() @ desired_armature)

    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    edit = arm.data.edit_bones
    lift_edit = edit.get(LIFT)
    need(lift_edit is not None, "source lift edit bone differs")
    for side in ("left", "right"):
        push_base = f"IK_push_arm_{side}_base"
        tilt_base = edit.get(f"IK_tilt_{side}_base")
        need(tilt_base is not None and tilt_base.parent == lift_edit,
             f"source {side} tilt edit parent differs")
        old_matrix = tilt_base.matrix.copy()
        created = edit.new(push_base)
        created.parent = lift_edit
        created.length = 0.25  # USF does not encode Blender edit-bone length.
        created.matrix = base_rest[side]
        tilt_base.parent = created
        tilt_base.matrix = old_matrix
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.update()

    # Compute each tip rest matrix from the newly realized base pose. This
    # avoids assuming Blender's post-edit pose equals the requested transform.
    tip_rest = {}
    for side in ("left", "right"):
        base = arm.pose.bones.get(f"IK_push_arm_{side}_base")
        need(base is not None, f"in-memory {side} push base is missing")
        desired_world = (FROM_SABER_CONVERT @ targets[side][1] @
                         TO_SABER_CONVERT)
        desired_armature = arm.matrix_world.inverted() @ desired_world
        tip_rest[side] = (base.bone.matrix_local @
                          base.matrix.inverted() @ desired_armature)

    bpy.ops.object.mode_set(mode="EDIT")
    edit = arm.data.edit_bones
    for side in ("left", "right"):
        push_base = edit.get(f"IK_push_arm_{side}_base")
        need(push_base is not None, f"in-memory {side} push edit base is missing")
        created = edit.new(f"IK_push_arm_{side}_tip")
        created.parent = push_base
        created.length = 0.25  # Diagnostic only; no Blend is saved.
        created.matrix = tip_rest[side]
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.update()

    after = source_paths(arm, convert_to_saber_transform)
    comparison = compare_static_armature(after, repaired)
    target_rows = []
    tilt_rows = []
    for side in ("left", "right"):
        base_path = ROOT_PREFIX + f"|IK_push_arm_{side}_base"
        target_paths = (base_path, base_path + f"|IK_push_arm_{side}_tip",
                        base_path + f"|IK_tilt_{side}_base",
                        base_path + f"|IK_tilt_{side}_base|IK_tilt_{side}_tip")
        for path in target_paths:
            need(path in after and path in repaired,
                 f"in-memory {side} path is missing: {path}")
            error = max(abs(a - b) for a, b in zip(after[path], repaired[path]))
            target_rows.append({"path": path, "maxElementError": error})
        base = arm.pose.bones.get(f"IK_tilt_{side}_base")
        tip = arm.pose.bones.get(f"IK_tilt_{side}_tip")
        need(base is not None and tip is not None and
             chain(base) == [CHASSIS, LIFT, f"IK_push_arm_{side}_base",
                             f"IK_tilt_{side}_base"] and
             chain(tip) == chain(base) + [f"IK_tilt_{side}_tip"],
             f"in-memory {side} tilt chain differs")
        old_base, old_tip = old_tilt_matrices[side]
        tilt_rows.append({"side": side,
                          "basePoseMatrixMaxChange": matrix_error(base.matrix, old_base),
                          "tipPoseMatrixMaxChange": matrix_error(tip.matrix, old_tip)})

    require_hash(blend, BLEND_SHA256, "source Blend after diagnostic")
    require_hash(usf, USF_SHA256, "repaired USF after diagnostic")
    require_sdk_pins(sdk)
    target_rows.sort(key=lambda row: row["path"])
    matching = (len(after) == 388 and comparison["sharedPathCount"] == 386 and
                len(comparison["sourceOnlyPaths"]) == 2 and
                len(comparison["repairedOnlyPaths"]) == 14 and
                comparison["changedMatrixCount"] == 0 and
                all(row["maxElementError"] <= TOLERANCE for row in target_rows) and
                all(max(row["basePoseMatrixMaxChange"],
                        row["tipPoseMatrixMaxChange"]) <= TOLERANCE
                    for row in tilt_rows))
    return {
        "schemaVersion": 1,
        "status": ("IN_MEMORY_PUSH_BRANCH_MATCH" if matching else
                   "IN_MEMORY_PUSH_BRANCH_DIFFERENT"),
        "asset": "cat_d11t", "blendSha256": BLEND_SHA256,
        "repairedUsfSha256": USF_SHA256,
        "blenderSha256": blender_sha256,
        "blenderVersion": bpy.app.version_string,
        "sceneFrame": bpy.context.scene.frame_current,
        "beforeSourceBoneCount": len(before),
        "afterSourceBoneCount": len(after),
        "repairedStructuralCount": len(repaired),
        "beforeSharedPathCount": before_comparison["sharedPathCount"],
        "afterSharedPathCount": comparison["sharedPathCount"],
        "afterChangedMatrixCount": comparison["changedMatrixCount"],
        "afterMaxSharedMatrixError": comparison["maxSharedMatrixError"],
        "afterSourceOnlyPaths": comparison["sourceOnlyPaths"],
        "afterRepairedOnlyPaths": comparison["repairedOnlyPaths"],
        "targetMatrixErrors": target_rows,
        "tiltPoseChanges": tilt_rows,
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
