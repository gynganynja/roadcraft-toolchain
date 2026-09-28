"""Boundary checks for the bounded D11 v2 RGBA discriminant."""

from __future__ import annotations

import json
import unittest

from roadcraft import blender_rgba_discriminant as probe
from roadcraft.blender_mesh_variant_payload import _color_summary


def _summarize(records, native):
    return probe.summarize_trace(
        records, native, _color_summary([[entry[4] for entry in records]]),
        _color_summary([native]))


class RgbaDiscriminantTests(unittest.TestCase):
    def test_no_mismatch_and_raw_input_mismatch(self):
        records = [((1.0, 1.0, 1.0, 1.0), False, None,
                    0xFFFFFFFF, 0xFFFFFFFF)]
        equal = _summarize(records, [0xFFFFFFFF])
        self.assertEqual(equal["finding"], "MISMATCH_NOT_REPRODUCED")
        self.assertEqual(equal["sourceNativeDifferent"], 0)
        changed = _summarize(records, [0xFF808080])
        self.assertEqual(changed["finding"],
                         "CALL_TIME_RGBA_PACKS_DIFFERENTLY_FROM_NATIVE")
        self.assertEqual(changed["sourceNativeDifferent"], 1)
        self.assertEqual(changed["statelessNativeDifferent"], 1)
        self.assertEqual(changed["sdkStatelessDifferent"], 0)
        self.assertEqual(changed["firstDifferences"][0]["rgba"],
                         [1.0, 1.0, 1.0, 1.0])

    def test_cache_hit_differs_from_stateless(self):
        records = [((0.5, 0.5, 0.5, 1.0), True, 0xFFFFFFFF,
                    0xFF7F7F7F, 0xFFFFFFFF)]
        detail = _summarize(records, [0xFF7F7F7F])
        self.assertEqual(detail["finding"],
                         "CACHE_RETURN_DIFFERS_FROM_STATELESS_PACK")
        self.assertEqual(detail["cacheHitDisagreements"], 1)
        self.assertEqual(detail["statelessNativeDifferent"], 0)

    def test_trace_shape_and_digest_fail_closed(self):
        records = [((1.0, 1.0, 1.0, 1.0), False, None,
                    0xFFFFFFFF, 0xFFFFFFFF)]
        with self.assertRaises(probe.RgbaDiscriminantError):
            probe.summarize_trace(records, [], _color_summary([[0xFFFFFFFF]]),
                                  _color_summary([[]]))
        with self.assertRaises(probe.RgbaDiscriminantError):
            probe.summarize_trace(records, [0xFFFFFFFF],
                                  _color_summary([[0xFF000000]]),
                                  _color_summary([[0xFFFFFFFF]]))
        with self.assertRaises(probe.RgbaDiscriminantError):
            _summarize([((1.0, 1.0, 1.0, 1.0), True, 0xFF000000,
                         0xFFFFFFFF, 0xFFFFFFFF)], [0xFFFFFFFF])

    def test_parse_requires_pin_no_write_and_bounded_detail(self):
        host_sha = "a" * 64
        result = {
            "schemaVersion": 1, "status": "SOURCE_RGBA_DISCRIMINANT",
            "asset": probe.ASSET, "targetPath": probe.TARGET_PATH,
            "blenderSha256": probe.BLENDER_SHA256,
            "probeHostSha256": host_sha,
            "probeWorkerSha256": probe.WORKER_SHA256,
            "variantHostSha256": probe.VARIANT_HOST_SHA256,
            "variantWorkerSha256": probe.VARIANT_WORKER_SHA256,
            "nativeBlendExportApproved": False,
            "blendSaved": False, "usfExported": False,
            "mappedRows": 126, "rowsDigestSha256": "b" * 64,
            "matchingNativeColorsRows": 126,
            "rgbaKeyType": "bpy_prop_array",
            "cacheBeforeTarget": 0, "cacheAfterTarget": 0,
            "sourceUnchanged": True, "sdkUnchanged": True,
            "nativeExportUnchanged": True, "repairedUsfUnchanged": True,
            "detail": {
                "finding": "MISMATCH_NOT_REPRODUCED",
                "elements": probe.TARGET_ELEMENTS,
                "sourceNativeDifferent": 0, "statelessNativeDifferent": 0,
                "sdkStatelessDifferent": 0, "cacheHits": 0,
                "cacheHitDisagreements": 0, "cacheMissDisagreements": 0,
                "firstDifferences": [],
                "source": {"elements": probe.TARGET_ELEMENTS, "sets": 1,
                           "sha256": probe.NATIVE_COLOR_SHA256},
                "stateless": {"elements": probe.TARGET_ELEMENTS, "sets": 1,
                              "sha256": probe.NATIVE_COLOR_SHA256},
                "native": {"elements": probe.TARGET_ELEMENTS, "sets": 1,
                           "sha256": probe.NATIVE_COLOR_SHA256},
            },
        }
        payload = probe.RESULT_PREFIX + json.dumps(result)
        self.assertEqual(probe.parse_result(payload, host_sha)["mappedRows"], 126)
        result["usfExported"] = True
        with self.assertRaises(probe.RgbaDiscriminantError):
            probe.parse_result(probe.RESULT_PREFIX + json.dumps(result), host_sha)
        result["usfExported"] = False
        result["detail"]["firstDifferences"] = [{}] * 13
        with self.assertRaises(probe.RgbaDiscriminantError):
            probe.parse_result(probe.RESULT_PREFIX + json.dumps(result), host_sha)


if __name__ == "__main__":
    unittest.main()
