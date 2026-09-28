"""Synthetic boundaries for the opt-in scratch-only RGBA cache guard."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from roadcraft import blender_rgba_cache_guard as guard  # noqa: E402


class ReusedColorWrapper:
    """Two distinct colors whose Blender-like cache keys compare equal."""

    def __init__(self, values):
        self.values = values

    def __iter__(self):
        return iter(self.values)

    def __getitem__(self, index):
        return self.values[index]

    def __hash__(self):
        return 7

    def __eq__(self, other):
        return isinstance(other, ReusedColorWrapper)


class RgbaCacheGuardTests(unittest.TestCase):
    def setUp(self):
        self.cache = {}
        cache = self.cache

        class ColorSet:
            FAST_PACK = False

            @staticmethod
            def rgba_to_saber(rgba):
                if rgba in cache:
                    return cache[rgba]
                channels = [int(min(1.0, max(0.0, rgba[i])) * 255.0)
                            for i in range(4)]
                value = ((channels[3] << 24) | (channels[0] << 16) |
                         (channels[1] << 8) | channels[2])
                cache[rgba] = value
                return value

        self.color_set = ColorSet
        self.original = ColorSet.rgba_to_saber

    def test_value_snapshot_prevents_stale_wrapper_collision(self):
        white = ReusedColorWrapper((1.0, 1.0, 1.0, 1.0))
        gray = ReusedColorWrapper((0.2, 0.3, 0.4, 1.0))
        self.assertEqual(self.original(white), 0xFFFFFFFF)
        self.assertEqual(self.original(gray), 0xFFFFFFFF)  # Reviewed SDK fault.
        with guard.immutable_rgba_cache(self.color_set, self.cache) as receipt:
            self.assertEqual(self.color_set.rgba_to_saber(white), 0xFFFFFFFF)
            self.assertEqual(self.color_set.rgba_to_saber(gray), 0xFF334C66)
            self.assertEqual(set(self.cache), {tuple(white), tuple(gray)})
        self.assertEqual(receipt["packCalls"], 2)
        self.assertTrue(receipt["restored"])
        self.assertTrue(receipt["cacheClearedAfter"])
        self.assertIs(self.color_set.rgba_to_saber, self.original)
        self.assertEqual(self.cache, {})

    def test_original_packing_and_clipping_are_retained(self):
        colors = ((0.0, 0.5, 1.0, 1.0), (0.2, 0.3, 0.4, 1.0),
                  (-1.0, 2.0, 0.999, 0.5), (1.0, 1.0, 1.0, 0.0))
        reference = []
        for color in colors:
            self.cache.clear()
            reference.append(self.original(color))
        with guard.immutable_rgba_cache(self.color_set, self.cache):
            actual = [self.color_set.rgba_to_saber(ReusedColorWrapper(color))
                      for color in colors]
        self.assertEqual(actual, reference)

    def test_original_is_restored_after_export_error(self):
        with self.assertRaisesRegex(RuntimeError, "export failed"):
            with guard.immutable_rgba_cache(self.color_set, self.cache) as receipt:
                self.color_set.rgba_to_saber((1.0, 1.0, 1.0, 1.0))
                raise RuntimeError("export failed")
        self.assertIs(self.color_set.rgba_to_saber, self.original)
        self.assertEqual(self.cache, {})
        self.assertTrue(receipt["restored"])

    def test_unsupported_mode_and_invalid_rgba_fail_closed(self):
        self.color_set.FAST_PACK = True
        with self.assertRaisesRegex(guard.RgbaCacheGuardError, "mode"):
            with guard.immutable_rgba_cache(self.color_set, self.cache):
                self.fail("guard entered with FAST_PACK")
        self.assertIs(self.color_set.rgba_to_saber, self.original)
        self.color_set.FAST_PACK = False
        with guard.immutable_rgba_cache(self.color_set, self.cache):
            with self.assertRaisesRegex(guard.RgbaCacheGuardError, "invalid"):
                self.color_set.rgba_to_saber((float("nan"), 0, 0, 1))

    def test_exact_pins_and_blender_version_are_required(self):
        pins = dict(asset_name=guard.ASSET_NAME,
                    blend_sha256=guard.BLEND_SHA256,
                    baseline_usf_sha256=guard.BASELINE_USF_SHA256,
                    blender_sha256=guard.BLENDER_SHA256,
                    sdk_mesh_sha256=guard.SDK_MESH_SHA256,
                    blender_version="Blender 5.2.0 LTS")
        guard.require_pins(**pins)
        for key in pins:
            changed = dict(pins)
            changed[key] = "other"
            with self.subTest(key=key), self.assertRaises(guard.RgbaCacheGuardError):
                guard.require_pins(**changed)


if __name__ == "__main__":
    unittest.main()
