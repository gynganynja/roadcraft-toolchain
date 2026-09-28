"""Synthetic, no-Blender boundaries for conditional live RGBA readback."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from roadcraft import blender_v2_rgba_live_discriminant as probe  # noqa: E402


def _rgba(*channels: float):
    return SimpleNamespace(color=channels)


class LiveRgbaTests(unittest.TestCase):
    def test_raw_readback_is_conditional_and_shape_pinned(self):
        native = probe._color_summary([0xFF334C66] * 3)
        source = probe._color_summary([0xFFFFFFFF] * 3)
        self.assertFalse(probe.should_read_live_raw(
            native, native, expected_elements=3,
            native_sha=native["sha256"]))
        self.assertTrue(probe.should_read_live_raw(
            source, native, expected_elements=3,
            native_sha=native["sha256"]))
        with self.assertRaises(probe.LiveRgbaError):
            probe.should_read_live_raw(source, native, expected_elements=6,
                                       native_sha=native["sha256"])
        with self.assertRaises(probe.LiveRgbaError):
            probe.should_read_live_raw(source, native, expected_elements=3,
                                       native_sha="0" * 64)

    def test_triangle_loop_order_and_stateless_sdk_equivalent(self):
        mesh = SimpleNamespace(loop_triangles=[
            SimpleNamespace(loops=(2, 0, 1)),
            SimpleNamespace(loops=(1, 2, 0)),
        ])
        data = [_rgba(1.0, 1.0, 1.0, 1.0),
                _rgba(0.2, 0.3, 0.4, 1.0),
                _rgba(-0.1, 1.5, 0.0, 1.0)]
        packed, raw = probe.pack_live_triangles(
            mesh, data, expected_elements=6)
        self.assertEqual(packed,
                         [0xFF00FF00, 0xFFFFFFFF, 0xFF334C66,
                          0xFF334C66, 0xFF00FF00, 0xFFFFFFFF])
        self.assertEqual(raw[0], (-0.1, 1.5, 0.0, 1.0))
        with self.assertRaises(probe.LiveRgbaError):
            probe.pack_live_triangles(mesh, data, expected_elements=3)
        with self.assertRaises(probe.LiveRgbaError):
            probe.pack_live_triangles(
                SimpleNamespace(loop_triangles=[SimpleNamespace(loops=(9, 0, 1))]),
                data, expected_elements=3)

    def test_mismatch_classification_and_bounded_samples(self):
        gray = (0.2, 0.3, 0.4, 1.0)
        white = (1.0, 1.0, 1.0, 1.0)
        native = [0xFF334C66] * 15
        source = [0xFFFFFFFF] * 15
        native_sha = probe._color_summary(native)["sha256"]
        detail = probe.summarize_mismatch(
            source, native, native, [gray] * 15,
            expected_elements=15, native_sha=native_sha)
        self.assertEqual(detail["finding"],
                         "SDK_PACK_OR_CACHE_DIFFERS_FROM_LIVE_RAW")
        self.assertEqual(detail["different"],
                         {"sourceNative": 15, "rawNative": 0, "sourceRaw": 15})
        self.assertEqual(len(detail["firstDifferences"]), 12)
        detail = probe.summarize_mismatch(
            source, native, source, [white] * 15,
            expected_elements=15, native_sha=native_sha)
        self.assertEqual(detail["finding"], "LIVE_RAW_DIFFERS_FROM_NATIVE")
        with self.assertRaises(probe.LiveRgbaError):
            probe.summarize_mismatch(source, native, source, [gray] * 15,
                                     expected_elements=15, native_sha=native_sha)
        with self.assertRaises(probe.LiveRgbaError):
            probe.summarize_mismatch(native, native, native, [gray] * 15,
                                     expected_elements=15, native_sha=native_sha)

    def test_receipt_rejects_false_no_write_or_conditional_claim(self):
        pins = probe.variant.ASSET_PINS[probe.ASSET]
        native = {"elements": probe.TARGET_ELEMENTS, "sets": 1,
                  "sha256": probe.NATIVE_COLOR_SHA256}
        result = {
            "schemaVersion": 1, "status": "SOURCE_V2_RGBA_LIVE_DISCRIMINANT",
            "asset": probe.ASSET, "targetPath": probe.TARGET_PATH,
            "blenderSha256": probe.BLENDER_SHA256,
            "blenderVersion": "5.2.0",
            "probeHostSha256": "a" * 64,
            "probeWorkerSha256": probe.WORKER_SHA256,
            "variantHostSha256": probe.VARIANT_HOST_SHA256,
            "variantWorkerSha256": probe.VARIANT_WORKER_SHA256,
            "blendSha256": pins["blendSha256"],
            "nativeUsfSha256": pins["nativeUsfSha256"],
            "repairedUsfSha256": pins["repairedUsfSha256"],
            "worklistSha256": probe.variant.WORKLIST_SHA256,
            "summarySha256": pins["summarySha256"],
            "sdkMeshSha256": probe.SDK_PINS["saber/blender/lib/usf/mesh.py"],
            "sdkFunctionsUnwrapped": True,
            "blendSaved": False, "usfExported": False,
            "nativeBlendExportApproved": False,
            "mappedRows": 126, "matchingNativeColorsRows": 126,
            "otherColorMismatchRows": 0,
            "rowsDigestSha256": "b" * 64,
            "target": {"source": native, "native": native,
                       "rawReadbackPerformed": False, "detail": None,
                       "cacheBefore": 85214, "cacheAfter": 135392},
            "sourceUnchanged": True, "sdkUnchanged": True,
            "nativeExportUnchanged": True, "repairedUsfUnchanged": True,
        }

        def emit():
            return probe.RESULT_PREFIX + json.dumps(result)

        self.assertEqual(probe.parse_result(emit(), "a" * 64), result)
        result["target"]["rawReadbackPerformed"] = True
        with self.assertRaises(probe.LiveRgbaError):
            probe.parse_result(emit(), "a" * 64)
        result["target"]["rawReadbackPerformed"] = False
        result["blendSaved"] = True
        with self.assertRaises(probe.LiveRgbaError):
            probe.parse_result(emit(), "a" * 64)
        result["blendSaved"] = False
        with self.assertRaises(probe.LiveRgbaError):
            probe.parse_result(emit() + "\n" + emit(), "a" * 64)


if __name__ == "__main__":
    unittest.main()
