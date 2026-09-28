"""No-Blender validation of the bounded RGBA cache lifetime receipt."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from roadcraft import blender_rgba_cache_lifetime as probe  # noqa: E402


def receipt() -> tuple[dict, str]:
    blender_sha = next(iter(probe.BLENDER_VERSION_PINS))
    return {
        "schemaVersion": 1,
        "status": "SDK_RGBA_STALE_CACHE_REPRODUCED",
        "blenderSha256": blender_sha,
        "blenderVersion": probe.BLENDER_VERSION_PINS[blender_sha] + "0",
        "sdkMeshSha256": probe.SDK_MESH_SHA256,
        "workerSha256": probe.WORKER_SHA256,
        "hostSha256": "a" * 64,
        "maxAttempts": probe.MAX_ATTEMPTS,
        "whiteKeyType": "bpy_prop_array",
        "whitePacked": 0xFFFFFFFF,
        "collision": {
            "attempt": 0, "sameHash": True, "equalKey": True,
            "rawRgba": [0.2, 0.3, 0.4, 1.0],
            "cacheBeforeLookup": 1, "cachedValue": 0xFFFFFFFF,
            "stalePacked": 0xFFFFFFFF, "cacheAfterStale": 1,
            "freshAfterClearPacked": 0xFF334C66, "cacheAfterFresh": 1,
        },
        "acceptedAssetOpened": False, "blendSaved": False,
        "usfExported": False, "sdkFileChanged": False,
        "nativeBlendExportApproved": False,
    }, blender_sha


class CacheLifetimeTests(unittest.TestCase):
    def test_reproduction_receipt_and_bounded_parse(self):
        value, blender_sha = receipt()
        self.assertEqual(probe.interpret_result(value, blender_sha=blender_sha,
                                                host_sha="a" * 64), value)
        line = probe.RESULT_PREFIX + json.dumps(value)
        self.assertEqual(probe.parse_result(line, blender_sha=blender_sha,
                                            host_sha="a" * 64), value)

    def test_no_collision_must_be_explicit_and_cannot_claim_reproduction(self):
        value, blender_sha = receipt()
        value["collision"] = None
        value["status"] = "SDK_RGBA_COLLISION_NOT_REPRODUCED"
        self.assertEqual(probe.interpret_result(value, blender_sha=blender_sha,
                                                host_sha="a" * 64), value)
        value["status"] = "SDK_RGBA_STALE_CACHE_REPRODUCED"
        with self.assertRaises(probe.CacheLifetimeError):
            probe.interpret_result(value, blender_sha=blender_sha,
                                   host_sha="a" * 64)

    def test_wrong_packing_or_no_write_flags_fail_closed(self):
        value, blender_sha = receipt()
        value["collision"]["freshAfterClearPacked"] = 0xFFFFFFFF
        with self.assertRaises(probe.CacheLifetimeError):
            probe.interpret_result(value, blender_sha=blender_sha,
                                   host_sha="a" * 64)
        value, blender_sha = receipt()
        value["acceptedAssetOpened"] = True
        with self.assertRaises(probe.CacheLifetimeError):
            probe.interpret_result(value, blender_sha=blender_sha,
                                   host_sha="a" * 64)

    def test_collision_shape_and_bounds_fail_closed(self):
        value, blender_sha = receipt()
        value["collision"]["attempt"] = probe.MAX_ATTEMPTS
        with self.assertRaises(probe.CacheLifetimeError):
            probe.interpret_result(value, blender_sha=blender_sha,
                                   host_sha="a" * 64)
        value, blender_sha = receipt()
        value["collision"]["rawRgba"][0] = float("nan")
        with self.assertRaises(probe.CacheLifetimeError):
            probe.interpret_result(value, blender_sha=blender_sha,
                                   host_sha="a" * 64)


if __name__ == "__main__":
    unittest.main()
