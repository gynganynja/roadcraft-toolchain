"""No-Blender tests for pinned D11 animation comparison and fail-closed gates."""

from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from roadcraft.blender_animation_payload import (  # noqa: E402
    BLEND_SHA256, BLENDER_VERSION_PINS, USF_SHA256, WORKER_SHA256,
    WORKLIST_SHA256, AnimationPayloadError, compare_records,
    interpret_readback,
)


def _spline(dimension: int, values: list[list[float]]) -> dict:
    return {
        "type": 7 if dimension == 4 else 2, "state": 0,
        "valuesDimension": dimension, "dataDimension": dimension,
        "keysCount": 36, "dataSize": 36 * (dimension + 1) * 4,
        "samples": [{"frame": float(index + 1), "value": value}
                    for index, value in enumerate(values)],
    }


def records() -> tuple[list[dict], dict, dict]:
    actions = []
    for name, begin, target_translation in (
            ("d11_wipers_backward", 20, 2.0),
            ("d11_wipers_forward", 1, 1.0)):
        tracks = []
        for axis in range(3):
            tracks.append({
                "dataPath": 'pose.bones["BoneAnim_WiperFront"].rotation_euler',
                "arrayIndex": axis,
                "keys": [{"frame": float(begin + offset), "value": 0.0,
                          "interpolation": "BEZIER",
                          "handleLeft": [float(begin + offset), 0.0],
                          "handleRight": [float(begin + offset), 0.0]}
                         for offset in (0, 8, 17)],
            })
        samples = [{"frame": begin + index,
                    "translate": [target_translation, 0.0, 0.0],
                    "rotation": [1.0, 0.0, 0.0, 0.0],
                    "scale": [1.0, 1.0, 1.0]}
                   for index in range(18)]
        actions.append({"name": name, "frameRange": [begin, begin + 17],
                        "tracks": tracks, "samples": samples})
    clips = [
        {"name": "d11_wipers_backward", "begin": 1, "end": 18,
         "time": 17 / 30, "frames": 0},
        {"name": "d11_wipers_forward", "begin": 19, "end": 36,
         "time": 17 / 30, "frames": 0},
    ]
    repaired = {
        "nodeCount": 654, "actorName": "cat_d11t",
        "clips": copy.deepcopy(clips),
        "nodeAnimations": [{
            "path": "|@root|D11T_Rig.005|BoneChassis_cdt|BoneAnim_WiperFront",
            "initial": {"translate": [0.0, 0.0, 0.0],
                        "rotation": [1.0, 0.0, 0.0, 0.0],
                        "scale": [1.0, 1.0, 1.0], "visibility": 1.0},
            "splines": {
                "translate": _spline(3, [[2.0 if i < 18 else 1.0, 0.0, 0.0]
                                          for i in range(36)]),
                "rotation": _spline(4, [[1.0, 0.0, 0.0, 0.0]
                                         for _ in range(36)]),
                "scale": _spline(3, [[1.0, 1.0, 1.0]
                                      for _ in range(36)]),
                "visibility": None,
            },
        }],
    }
    native = {"nodeCount": 597, "actorName": "cat_d11t",
              "clips": copy.deepcopy(clips), "nodeAnimations": []}
    return actions, repaired, native


class AnimationPayloadTests(unittest.TestCase):
    def test_clip_name_alignment_and_native_missing_track(self):
        actions, repaired, native = records()
        result = compare_records(actions, repaired, native)
        self.assertEqual(result["sourceTrackCount"], 6)
        self.assertEqual(result["sourceKeyframePointCount"], 18)
        self.assertEqual(result["sourceEvaluatedFramesComparedToRepaired"], 36)
        self.assertTrue(result["sourceRepairedWithinTolerance"])
        self.assertEqual(result["sourceRepairedMaximumErrors"],
                         {"translate": 0.0, "rotationRadians": 0.0,
                          "scale": 0.0})
        self.assertFalse(result["nativeWiperTransformTrackPresent"])

    def test_quaternion_sign_equivalent_but_changed_transform_detected(self):
        actions, repaired, native = records()
        repaired["nodeAnimations"][0]["splines"]["rotation"]["samples"][0]["value"] = [
            -1.0, 0.0, 0.0, 0.0]
        self.assertTrue(compare_records(actions, repaired, native)[
            "sourceRepairedWithinTolerance"])
        repaired["nodeAnimations"][0]["splines"]["translate"]["samples"][0]["value"][0] = 2.1
        result = compare_records(actions, repaired, native)
        self.assertFalse(result["sourceRepairedWithinTolerance"])
        self.assertAlmostEqual(result["sourceRepairedMaximumErrors"]["translate"],
                               0.1)

    def test_incomplete_target_or_spline_rejected(self):
        actions, repaired, native = records()
        native["nodeAnimations"] = copy.deepcopy(repaired["nodeAnimations"])
        with self.assertRaises(AnimationPayloadError):
            compare_records(actions, repaired, native)
        actions, repaired, native = records()
        repaired["nodeAnimations"][0]["splines"]["rotation"]["samples"].pop()
        with self.assertRaises(AnimationPayloadError):
            compare_records(actions, repaired, native)
        actions, repaired, native = records()
        actions[0]["tracks"][0]["keys"].pop()
        with self.assertRaises(AnimationPayloadError):
            compare_records(actions, repaired, native)

    def test_result_identity_and_export_gate(self):
        actions, repaired, native = records()
        blender_sha = next(iter(BLENDER_VERSION_PINS))
        result = {
            "schemaVersion": 1, "asset": "cat_d11t",
            "blendSha256": BLEND_SHA256,
            "repairedUsfSha256": USF_SHA256,
            "nativeExportUsfSha256": "b" * 64,
            "worklistSha256": WORKLIST_SHA256,
            "summarySha256": "c" * 64,
            "blenderSha256": blender_sha,
            "hostSha256": "a" * 64,
            "workerSha256": WORKER_SHA256,
            "blenderVersion": BLENDER_VERSION_PINS[blender_sha] + "1",
            "blendSaved": False, "usfExported": False,
            "nativeBlendExportApproved": False,
            "sourceActions": actions, "repaired": repaired,
            "native": native,
        }
        checked = interpret_readback(result, blender_sha, "b" * 64,
                                     "c" * 64, "a" * 64)
        self.assertEqual(checked["status"],
                         "SOURCE_REPAIRED_NATIVE_ANIMATION_READBACK")
        self.assertFalse(checked["nativeBlendExportApproved"])
        result["usfExported"] = True
        with self.assertRaises(AnimationPayloadError):
            interpret_readback(result, blender_sha, "b" * 64,
                               "c" * 64, "a" * 64)


if __name__ == "__main__":
    unittest.main()
