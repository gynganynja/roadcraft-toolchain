"""No-Blender gates for the pinned D11 v2/v3 animation readbacks."""

from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from roadcraft.blender_animation_payload import (  # noqa: E402
    BLEND_SHA256, BLENDER_VERSION_PINS, WORKLIST_SHA256,
    AnimationPayloadError,
)
from roadcraft.blender_animation_variants import (  # noqa: E402
    BASE_HOST_SHA256, BASE_WORKER_SHA256, VARIANTS, WORKER_SHA256,
    interpret_readback,
)
from tests.test_blender_animation_payload import records  # noqa: E402


def readback(asset: str) -> tuple[dict, str]:
    actions, repaired, native = records()
    native["actorName"] = asset
    blender_sha = next(iter(BLENDER_VERSION_PINS))
    pins = VARIANTS[asset]
    return {
        "schemaVersion": 1, "asset": asset,
        "blendSha256": BLEND_SHA256,
        "repairedUsfSha256": pins["repairedSha256"],
        "nativeExportUsfSha256": pins["nativeSha256"],
        "summarySha256": pins["summarySha256"],
        "sourceAssetDigest": pins["sourceAssetDigest"],
        "worklistSha256": WORKLIST_SHA256,
        "blenderSha256": blender_sha,
        "hostSha256": "a" * 64,
        "workerSha256": WORKER_SHA256,
        "baseHostSha256": BASE_HOST_SHA256,
        "baseWorkerSha256": BASE_WORKER_SHA256,
        "repairedRootName": "cat_d11t",
        "nativeRootName": asset,
        "blenderVersion": BLENDER_VERSION_PINS[blender_sha] + "1",
        "blendSaved": False, "usfExported": False,
        "nativeBlendExportApproved": False,
        "sourceActions": actions, "repaired": repaired, "native": native,
    }, blender_sha


class AnimationVariantTests(unittest.TestCase):
    def test_both_variant_identities_preserve_native_track_omission(self):
        for asset in sorted(VARIANTS):
            with self.subTest(asset=asset):
                result, blender_sha = readback(asset)
                checked = interpret_readback(result, asset, blender_sha, "a" * 64)
                self.assertEqual(checked["status"],
                                 "SOURCE_REPAIRED_NATIVE_VARIANT_ANIMATION_READBACK")
                self.assertTrue(checked["comparison"]["sourceRepairedWithinTolerance"])
                self.assertFalse(checked["comparison"]["nativeWiperTransformTrackPresent"])
                self.assertEqual(checked["native"]["actorName"], asset)

    def test_variant_actor_and_clip_tampering_rejected(self):
        result, blender_sha = readback("cat_d11t_v2")
        bad = copy.deepcopy(result)
        bad["native"]["actorName"] = "cat_d11t"
        with self.assertRaises(AnimationPayloadError):
            interpret_readback(bad, "cat_d11t_v2", blender_sha, "a" * 64)
        bad = copy.deepcopy(result)
        bad["native"]["clips"][0]["name"] = "wrong"
        with self.assertRaises(AnimationPayloadError):
            interpret_readback(bad, "cat_d11t_v2", blender_sha, "a" * 64)

    def test_native_spline_and_export_gate_tampering_rejected(self):
        result, blender_sha = readback("cat_d11t_v3")
        bad = copy.deepcopy(result)
        bad["native"]["nodeAnimations"] = copy.deepcopy(
            bad["repaired"]["nodeAnimations"])
        with self.assertRaises(AnimationPayloadError):
            interpret_readback(bad, "cat_d11t_v3", blender_sha, "a" * 64)
        bad = copy.deepcopy(result)
        bad["nativeBlendExportApproved"] = True
        with self.assertRaises(AnimationPayloadError):
            interpret_readback(bad, "cat_d11t_v3", blender_sha, "a" * 64)


if __name__ == "__main__":
    unittest.main()
