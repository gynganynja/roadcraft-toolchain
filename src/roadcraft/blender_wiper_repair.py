"""Guarded, in-memory D11 wiper animation repair for a scratch SDK export.

This module does not save a Blend or write an asset. The caller must use the
pinned scratch-only authoring probe; the native-Blend build gate remains closed
regardless of this repair's outcome. It targets one verified historical Blend
and two verified bundled SDK modules, not arbitrary authoring files.
"""

from __future__ import annotations


BLEND_SHA256 = "1eadf10af8525e2bd72e0db43cba20e05bcb1014c4e8e09354228f7c79115731"
SDK_MISC_SHA256 = "301d79c7e98edee58da0c4e77229524291968ce504a99be07dc76e1a09358a1c"
SDK_SCENE_SHA256 = "386567f324799274fc7b1ab6c3c92898b19d0d04de6f072ab5b4a47001c551fd"
ARMATURE_NAME = "D11T_Rig.005"
WIPER_BONE = "BoneAnim_WiperFront"
ACTION_RANGES = {"d11_wipers_backward": (20, 37),
                 "d11_wipers_forward": (1, 18)}
SLOT_IDENTIFIER = "OBD11T_Rig.005"


class WiperRepairError(RuntimeError):
    """The source or SDK differs from the narrowly reviewed repair target."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise WiperRepairError(message)


def _action_curves(action) -> list:
    return [curve for layer in action.layers for strip in layer.strips
            for bag in strip.channelbags for curve in bag.fcurves]


def install_scratch_wiper_repair(
    bpy, sdk_misc, *, blend_sha256: str, sdk_misc_sha256: str,
    sdk_scene_sha256: str,
) -> dict:
    """Bind the existing wiper actions and bake inclusive endpoints in memory.

    The bundled SDK initializes bone animation only when an armature has an
    active action. Its `_bake_anim` omits each action's final frame, whereas the
    repaired USF has 18 + 18 samples. This patch is intentionally limited to
    the exact pinned Blend, SDK modules, rig and two wiper-only actions.
    """
    _require(blend_sha256 == BLEND_SHA256, "historical Blend pin differs")
    _require(sdk_misc_sha256 == SDK_MISC_SHA256 and
             sdk_scene_sha256 == SDK_SCENE_SHA256, "bundled SDK pin differs")
    _require(bpy.app.version[:2] == (5, 2), "Blender version differs from probe")
    armatures = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    _require(len(armatures) == 1 and armatures[0].name == ARMATURE_NAME,
             "wiper armature is not unique")
    arm = armatures[0]
    bone = arm.pose.bones.get(WIPER_BONE)
    _require(bone is not None and bone.parent is not None and
             bone.parent.name == "BoneChassis_cdt", "wiper bone hierarchy differs")
    data = arm.animation_data
    _require(data is None or (data.action is None and data.action_slot is None),
             "armature already has an active action or slot")
    action_sequence = [action.name for action in bpy.data.actions]
    _require(action_sequence == list(ACTION_RANGES),
             "wiper action order differs from repaired USF")
    actions = {action.name: action for action in bpy.data.actions}
    _require(len(actions) == len(ACTION_RANGES) and
             set(actions) == set(ACTION_RANGES), "wiper actions differ")
    target_path = f'pose.bones["{WIPER_BONE}"].rotation_euler'
    for name, frame_range in ACTION_RANGES.items():
        action = actions[name]
        _require(tuple(int(value) for value in action.frame_range) == frame_range,
                 f"{name} frame range differs")
        _require(len(action.slots) == 1 and
                 action.slots[0].identifier == SLOT_IDENTIFIER and
                 action.slots[0].target_id_type == "OBJECT",
                 f"{name} action slot differs")
        curves = _action_curves(action)
        _require(len(curves) == 3 and
                 {curve.array_index for curve in curves} == {0, 1, 2} and
                 all(curve.data_path == target_path and
                     len(curve.keyframe_points) == 3 for curve in curves),
                 f"{name} F-curves differ")
    _require(callable(sdk_misc._get_action_targets) and
             callable(sdk_misc._bake_anim), "SDK animation hooks are missing")

    # All checks above complete before either mutation. Nothing is saved to
    # the source Blend. The existing authoring helper exports only to scratch.
    data = arm.animation_data_create()
    data.action = actions["d11_wipers_forward"]
    data.action_slot = actions["d11_wipers_forward"].slots[0]
    _require(data.action == actions["d11_wipers_forward"] and
             data.action_slot == actions["d11_wipers_forward"].slots[0],
             "could not bind the forward action")
    trace = {"strategy": "bind-forward-and-include-action-endpoints",
             "actionOrder": [], "sampleCounts": {}, "nativeBlendExportApproved": False}

    def inclusive_bake(action, nodes):
        _require(action.name in ACTION_RANGES, "SDK encountered another action")
        targets = sdk_misc._get_action_targets(action)
        bake_nodes = [node for node in nodes if node.name in targets]
        _require(len(bake_nodes) == 1 and bake_nodes[0].name == WIPER_BONE,
                 "SDK wiper target changed")
        _require(bake_nodes[0].anim.arm_obj is arm,
                 "SDK animation points to another armature")
        data.action = action
        data.action_slot = action.slots[0]
        begin, end = ACTION_RANGES[action.name]
        for frame in range(begin, end + 1):
            bpy.context.scene.frame_set(frame)
            bake_nodes[0].anim.b_read_frame()
        trace["actionOrder"].append(action.name)
        trace["sampleCounts"][action.name] = end - begin + 1
        return [WIPER_BONE]

    sdk_misc._bake_anim = inclusive_bake
    return trace
