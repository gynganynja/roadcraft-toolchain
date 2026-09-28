"""Synthetic guards for the opt-in, in-memory D11 wiper scratch repair."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from roadcraft import blender_wiper_repair as repair  # noqa: E402


def _action(name: str, frame_range: tuple[int, int]):
    slot = SimpleNamespace(identifier=repair.SLOT_IDENTIFIER,
                           target_id_type="OBJECT")
    curves = [SimpleNamespace(
        data_path='pose.bones["BoneAnim_WiperFront"].rotation_euler',
        array_index=index, keyframe_points=[object()] * 3,
    ) for index in range(3)]
    bag = SimpleNamespace(fcurves=curves)
    strip = SimpleNamespace(channelbags=[bag])
    layer = SimpleNamespace(strips=[strip])
    return SimpleNamespace(name=name, frame_range=frame_range, slots=[slot],
                           layers=[layer])


class BlenderWiperRepairTests(unittest.TestCase):
    def setUp(self):
        self.frames = []
        self.read_frames = []
        self.data = SimpleNamespace(action=None, action_slot=None)
        bone = SimpleNamespace(parent=SimpleNamespace(name="BoneChassis_cdt"))
        self.arm = SimpleNamespace(
            type="ARMATURE", name=repair.ARMATURE_NAME,
            pose=SimpleNamespace(bones={repair.WIPER_BONE: bone}),
            animation_data=self.data,
        )
        self.arm.animation_data_create = lambda: self.data
        self.actions = [_action(name, span) for name, span in repair.ACTION_RANGES.items()]
        scene = SimpleNamespace(objects=[self.arm],
                                frame_set=lambda frame: self.frames.append(frame))
        self.bpy = SimpleNamespace(app=SimpleNamespace(version=(5, 2, 0)),
                                   context=SimpleNamespace(scene=scene),
                                   data=SimpleNamespace(actions=self.actions))
        self.old_bake = lambda action, nodes: []
        self.sdk = SimpleNamespace(_get_action_targets=lambda action: {repair.WIPER_BONE},
                                   _bake_anim=self.old_bake)

    def _install(self, **overrides):
        pins = {"blend_sha256": repair.BLEND_SHA256,
                "sdk_misc_sha256": repair.SDK_MISC_SHA256,
                "sdk_scene_sha256": repair.SDK_SCENE_SHA256}
        pins.update(overrides)
        return repair.install_scratch_wiper_repair(self.bpy, self.sdk, **pins)

    def test_binds_existing_action_and_samples_both_endpoints(self):
        trace = self._install()
        node = SimpleNamespace(name=repair.WIPER_BONE,
                               anim=SimpleNamespace(arm_obj=self.arm,
                                                    b_read_frame=lambda:
                                                    self.read_frames.append(self.frames[-1])))
        for action in self.actions:
            self.assertEqual(self.sdk._bake_anim(action, [node]), [repair.WIPER_BONE])
        self.assertEqual(len(self.read_frames), 36)
        self.assertEqual(self.read_frames[:18], list(range(20, 38)))
        self.assertEqual(self.read_frames[18:], list(range(1, 19)))
        self.assertEqual(trace["sampleCounts"], {
            "d11_wipers_backward": 18, "d11_wipers_forward": 18})
        self.assertFalse(trace["nativeBlendExportApproved"])
        self.assertEqual(self.data.action, self.actions[-1])
        self.assertEqual(self.data.action_slot, self.actions[-1].slots[0])

    def test_unpinned_source_rejects_before_scene_mutation(self):
        with self.assertRaisesRegex(repair.WiperRepairError, "Blend pin"):
            self._install(blend_sha256="0" * 64)
        self.assertIsNone(self.data.action)
        self.assertIs(self.sdk._bake_anim, self.old_bake)

    def test_extra_curve_rejects_before_scene_mutation(self):
        self.actions[0].layers[0].strips[0].channelbags[0].fcurves.append(
            SimpleNamespace(data_path="other", array_index=3,
                            keyframe_points=[object()]))
        with self.assertRaisesRegex(repair.WiperRepairError, "F-curves differ"):
            self._install()
        self.assertIsNone(self.data.action)
        self.assertIs(self.sdk._bake_anim, self.old_bake)

    def test_existing_active_action_rejects_before_sdk_patch(self):
        self.data.action = self.actions[0]
        with self.assertRaisesRegex(repair.WiperRepairError, "already has"):
            self._install()
        self.assertIs(self.sdk._bake_anim, self.old_bake)

    def test_reversed_action_order_rejects_before_scene_mutation(self):
        self.bpy.data.actions = list(reversed(self.actions))
        with self.assertRaisesRegex(repair.WiperRepairError, "action order differs"):
            self._install()
        self.assertIsNone(self.data.action)
        self.assertIs(self.sdk._bake_anim, self.old_bake)


if __name__ == "__main__":
    unittest.main()
