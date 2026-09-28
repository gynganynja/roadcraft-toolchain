"""Pinned, no-save D11 access-ladder hierarchy reconstruction diagnostic."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roadcraft.blender_ladder import (  # noqa: E402
    BLEND_SHA256, BLENDER_VERSION_PINS, LadderError, RESULT_PREFIX,
    USF_SHA256, require_hash, require_sdk_pins,
)
from roadcraft.blender_armature_parity import compare_static_armature  # noqa: E402
from roadcraft.blender_push_branches_worker import (  # noqa: E402
    chain, repaired_paths, source_paths, unique_node,
)


ARMATURE = "D11T_Rig.005"
CHASSIS = "BoneChassis_cdt"
NAMES = ("BoneAccess_LadderMount", "BoneAccess_Swivel",
         "BoneAccess_LadderHinge", "BoneAccess_Ladder")
PREFIX = ("@root", ARMATURE, CHASSIS)
TOLERANCE = 1e-5


def need(condition: bool, message: str) -> None:
    if not condition:
        raise LadderError(message)


def _max_flat_error(left: list[float], right: list[float]) -> float:
    return max(abs(a - b) for a, b in zip(left, right, strict=True))


def run(*, blend: Path, usf: Path, sdk_root: Path,
        worker_sha256: str, blender_sha256: str,
        loaded_scene: bool = False, push_and_roll_present: bool = False) -> dict:
    need(blender_sha256 in BLENDER_VERSION_PINS,
         "Blender executable pin is not reviewed")
    require_hash(Path(bpy.app.binary_path), blender_sha256, "Blender executable")
    require_hash(Path(__file__), worker_sha256, "ladder worker")
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
    nodes = {name: unique_node(root, PREFIX + NAMES[:index + 1])
             for index, name in enumerate(NAMES)}
    for index, name in enumerate(NAMES):
        node = nodes[name]
        children = [] if index == len(NAMES) - 1 else [NAMES[index + 1]]
        need(node.mesh is None and node.anim is None and
             sorted(child.name for child in node.children) == children,
             f"repaired ladder node differs: {name}")

    if loaded_scene:
        need(Path(bpy.data.filepath).resolve() == blend.resolve(),
             "loaded scene is not the pinned source Blend")
    else:
        need(not push_and_roll_present,
             "combined repairs require an explicitly loaded scene")
        bpy.ops.wm.open_mainfile(filepath=str(blend), load_ui=False)
    arms = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    need(len(arms) == 1 and arms[0].name == ARMATURE,
         "source armature is not unique")
    need(bpy.context.scene.frame_current == 1, "source frame differs")
    arm = arms[0]
    need(sum(obj.type == "MESH" for obj in bpy.context.scene.objects) == 210,
         "source scene mesh count differs")
    before = source_paths(arm, convert_to_saber_transform)
    baseline = compare_static_armature(before, repaired)
    expected_before = ((389, 388, 1, 12, 0) if push_and_roll_present else
                       (384, 378, 6, 22, 0))
    need((len(before), baseline["sharedPathCount"],
          len(baseline["sourceOnlyPaths"]),
          len(baseline["repairedOnlyPaths"]),
          baseline["changedMatrixCount"]) == expected_before,
         "source static baseline differs")
    ladder = arm.pose.bones.get(NAMES[-1])
    need(ladder is not None and chain(ladder) == [CHASSIS, NAMES[-1]] and
         not ladder.children and not ladder.constraints and
         not ladder.bone.use_connect and
         all(arm.pose.bones.get(name) is None for name in NAMES[:-1]),
         "source ladder hierarchy differs")
    attached = [obj for obj in bpy.context.scene.objects
                if obj.parent == arm and obj.parent_type == "BONE" and
                obj.parent_bone == NAMES[-1]]
    need(not attached, "source ladder has bone-parented objects")

    def desired_armature(node):
        world = FROM_SABER_CONVERT @ node.matrix_world @ TO_SABER_CONVERT
        return arm.matrix_world.inverted() @ world

    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    parent_name = CHASSIS
    for name in NAMES:
        parent = arm.pose.bones[parent_name]
        rest = (parent.bone.matrix_local @ parent.matrix.inverted() @
                desired_armature(nodes[name]))
        bpy.ops.object.mode_set(mode="EDIT")
        edit = arm.data.edit_bones
        bone = edit.get(name)
        if bone is None:
            bone = edit.new(name)
            bone.length = 0.25  # USF does not encode edit-bone length.
        need(bone is not None and edit.get(parent_name) is not None,
             f"ladder edit bone is missing: {name}")
        bone.parent = edit[parent_name]
        bone.matrix = rest
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.context.view_layer.update()
        parent_name = name

    after = source_paths(arm, convert_to_saber_transform)
    comparison = compare_static_armature(after, repaired)
    targets = []
    for index, name in enumerate(NAMES):
        path = "|".join(("",) + PREFIX + NAMES[:index + 1])
        need(path in after and path in repaired,
             f"in-memory ladder path is missing: {path}")
        targets.append({"path": path,
                        "maxElementError": _max_flat_error(after[path],
                                                            repaired[path])})
    need(chain(arm.pose.bones[NAMES[-1]]) == [CHASSIS, *NAMES],
         "in-memory ladder chain differs")
    require_hash(blend, BLEND_SHA256, "source Blend after diagnostic")
    require_hash(usf, USF_SHA256, "repaired USF after diagnostic")
    require_sdk_pins(sdk)
    expected_after = ((392, 392, 0, 8) if push_and_roll_present else
                      (387, 382, 5, 18))
    matched = ((len(after), comparison["sharedPathCount"],
                len(comparison["sourceOnlyPaths"]),
                len(comparison["repairedOnlyPaths"])) == expected_after and
               comparison["changedMatrixCount"] == 0 and
               comparison["maxSharedMatrixError"] <= TOLERANCE and
               all(row["maxElementError"] <= TOLERANCE for row in targets))
    return {
        "schemaVersion": 1,
        "status": ("IN_MEMORY_LADDER_MATCH" if matched else
                   "IN_MEMORY_LADDER_DIFFERENT"),
        "asset": "cat_d11t", "blendSha256": BLEND_SHA256,
        "repairedUsfSha256": USF_SHA256,
        "blenderSha256": blender_sha256,
        "blenderVersion": bpy.app.version_string,
        "sceneFrame": bpy.context.scene.frame_current,
        "pushAndRollPresent": push_and_roll_present,
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
        "sourceLadderBoneParentedObjectCount": len(attached),
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
