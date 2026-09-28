"""Blender-side worker for the pinned, no-save left push-arm experiment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roadcraft.blender_left_push_probe import (  # noqa: E402
    BLENDER_SHA256, BLEND_SHA256, RESULT_PREFIX, USF_SHA256,
    LeftPushProbeError, require_hash, require_sdk_pins,
)


ARMATURE = "D11T_Rig.005"
PARENT = "BoneBladeLift_cdt"
NEW_BONE = "IK_push_arm_left_base"
TILT_BASE = "IK_tilt_left_base"
TILT_TIP = "IK_tilt_left_tip"
USF_PATH = ("@root", ARMATURE, "BoneChassis_cdt", PARENT, NEW_BONE)


def max_matrix_error(left, right) -> float:
    return max(abs(float(left[row][col]) - float(right[row][col]))
               for row in range(4) for col in range(4))


def parent_chain(bone) -> list[str]:
    names = []
    while bone is not None:
        names.append(bone.name)
        bone = bone.parent
    return list(reversed(names))


def unique_node(root, path: tuple[str, ...]):
    """Use every hierarchy component; duplicate names are an error."""
    if root.name != "cat_d11t" or path[0] != "@root":
        raise LeftPushProbeError("repaired USF root differs")
    node = root
    for component in path[1:]:
        matches = [child for child in node.children if child.name == component]
        if len(matches) != 1:
            raise LeftPushProbeError(f"repaired USF path is not unique at {component}")
        node = matches[0]
    return node


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise LeftPushProbeError(message)


def run_in_memory(*, blend: Path, usf: Path, sdk_root: Path, worker_sha256: str) -> dict:
    # Check bytes before Blender opens either input. Nothing here has a file
    # output path; open_mainfile and the edit-bone change stay in process RAM.
    # Blender's embedded Python can report its Python runtime as
    # sys.executable; bpy.app.binary_path is the launched Blender binary.
    require_hash(Path(bpy.app.binary_path), BLENDER_SHA256, "Blender executable")
    require_hash(Path(__file__), worker_sha256, "diagnostic worker")
    blend = require_hash(blend, BLEND_SHA256, "source Blend")
    usf = require_hash(usf, USF_SHA256, "repaired USF")
    sdk = require_sdk_pins(sdk_root)
    _require(bpy.app.version[:2] == (5, 2), "Blender version differs")

    sys.path.insert(0, str(sdk))
    from saber.blender.lib.binary_io import BinaryIO
    from saber.blender.lib.usf.scene import usf_read
    from saber.blender.lib.usf.transform import FROM_SABER_CONVERT, TO_SABER_CONVERT

    # The retained SDK reader requires this harmless byte-array read shim for
    # these USF bytes; it changes only the in-process Python class method.
    original_reader = BinaryIO.read_bytearray
    BinaryIO.read_bytearray = (
        lambda self, size=None: self.io.read(size) if size is not None
        else original_reader(self)
    )
    _, scene = usf_read(str(usf))
    target = unique_node(scene._root_node, USF_PATH)
    _require(target.mesh is None and target.anim is None,
             "repaired intermediate node is not meshless and unanimated")
    _require(any(child.name == TILT_BASE for child in target.children),
             "repaired left tilt base is not beneath intermediate node")
    repaired_world = target.matrix_world.copy()
    repaired_children = [child.name for child in target.children]

    bpy.ops.wm.open_mainfile(filepath=str(blend), load_ui=False)
    arms = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    _require(len(arms) == 1 and arms[0].name == ARMATURE,
             "source armature is not unique")
    arm = arms[0]
    bones = arm.pose.bones
    _require(bones.get(NEW_BONE) is None, "source already has intermediate bone")
    parent = bones.get(PARENT)
    base = bones.get(TILT_BASE)
    tip = bones.get(TILT_TIP)
    _require(parent is not None and base is not None and tip is not None,
             "source left push-arm branch differs")
    _require(base.parent == parent and tip.parent == base,
             "source left tilt hierarchy differs")
    _require(not base.constraints and not tip.constraints,
             "source left tilt constraints differ")
    _require(not base.bone.use_connect, "source tilt base is connected")
    old_base = base.matrix.copy()
    old_tip = tip.matrix.copy()
    old_chain = parent_chain(base)
    _require(old_chain == ["BoneChassis_cdt", PARENT, TILT_BASE],
             "source parent chain differs")

    # Invert the SDK's blend-to-Saber basis conversion, then express the
    # repaired world transform in the source armature's local space.
    desired_world = FROM_SABER_CONVERT @ repaired_world @ TO_SABER_CONVERT
    desired_armature = arm.matrix_world.inverted() @ desired_world
    # The SDK reads pose matrices. The lift parent has a non-rest pose in this
    # Blend, so assigning the target pose matrix directly as an edit/rest
    # matrix would inherit that pose a second time.
    desired_rest = parent.bone.matrix_local @ parent.matrix.inverted() @ desired_armature
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    edit = arm.data.edit_bones
    parent_edit = edit.get(PARENT)
    base_edit = edit.get(TILT_BASE)
    _require(parent_edit is not None and base_edit is not None,
             "edit-bone hierarchy differs")
    prior_base_edit_matrix = base_edit.matrix.copy()
    created = edit.new(NEW_BONE)
    created.parent = parent_edit
    # A newly created edit bone has zero length. Set a diagnostic length
    # before assigning its matrix, or Blender discards the target rotation.
    created.length = 0.25  # A diagnostic choice; the USF does not encode length.
    created.matrix = desired_rest
    base_edit.parent = created
    base_edit.matrix = prior_base_edit_matrix
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.update()

    new_bone = arm.pose.bones.get(NEW_BONE)
    base = arm.pose.bones.get(TILT_BASE)
    tip = arm.pose.bones.get(TILT_TIP)
    _require(new_bone is not None and base is not None and tip is not None,
             "in-memory edit did not produce expected bones")
    result_world = TO_SABER_CONVERT @ (arm.matrix_world @ new_bone.matrix) @ FROM_SABER_CONVERT
    world_error = max_matrix_error(result_world, repaired_world)
    base_error = max_matrix_error(base.matrix, old_base)
    tip_error = max_matrix_error(tip.matrix, old_tip)
    chain = parent_chain(base)
    expected_chain = ["BoneChassis_cdt", PARENT, NEW_BONE, TILT_BASE]
    require_hash(blend, BLEND_SHA256, "source Blend after diagnostic")
    require_hash(usf, USF_SHA256, "repaired USF after diagnostic")
    require_sdk_pins(sdk)
    matching = (chain == expected_chain and world_error <= 1e-5 and
                base_error <= 1e-5 and tip_error <= 1e-5)
    return {
        "schemaVersion": 1,
        "status": "IN_MEMORY_STATIC_PATH_MATCH" if matching else "IN_MEMORY_STATIC_PATH_DIFFERENT",
        "asset": "cat_d11t",
        "blendSha256": BLEND_SHA256,
        "repairedUsfSha256": USF_SHA256,
        "blenderVersion": bpy.app.version_string,
        "repairedPath": "|" + "|".join(USF_PATH),
        "repairedChildNames": repaired_children,
        "oldTiltBaseChain": old_chain,
        "newTiltBaseChain": chain,
        "newBoneWorldMatrixMaxError": world_error,
        "tiltBasePoseMatrixMaxChange": base_error,
        "tiltTipPoseMatrixMaxChange": tip_error,
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
    args = parser.parse_args(argv)
    result = run_in_memory(blend=args.blend, usf=args.repaired_usf,
                           sdk_root=args.sdk_script_root,
                           worker_sha256=args.worker_sha256)
    print(RESULT_PREFIX + json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
