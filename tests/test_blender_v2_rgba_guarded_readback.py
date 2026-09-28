"""Synthetic boundaries for the pinned, whole-projection RGBA guard."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from roadcraft import blender_v2_rgba_guarded_readback as host  # noqa: E402


class EqualColor:
    def __init__(self, rgba):
        self.rgba = rgba

    def __iter__(self):
        return iter(self.rgba)

    def __getitem__(self, index):
        return self.rgba[index]

    def __hash__(self):
        return 1

    def __eq__(self, other):
        return isinstance(other, EqualColor)


class MeshObject:
    type = "MESH"

    def __init__(self, rgba, *, fail=False):
        self.rgba = rgba
        self.fail = fail


class ProjectionGuardTests(unittest.TestCase):
    def setUp(self):
        self.opened = False
        self.cache = {}
        cache = self.cache

        class ColorSet:
            FAST_PACK = False

            @staticmethod
            def rgba_to_saber(rgba):
                if rgba in cache:
                    return cache[rgba]
                channels = [int(min(1.0, max(0.0, rgba[i])) * 255)
                            for i in range(4)]
                value = ((channels[3] << 24) | (channels[0] << 16) |
                         (channels[1] << 8) | channels[2])
                cache[rgba] = value
                return value

        class Mesh:
            def b_read(self, obj):
                if obj.fail:
                    raise RuntimeError("projection failed")
                return ColorSet.rgba_to_saber(obj.rgba)

        self.ColorSet = ColorSet
        self.Mesh = Mesh
        self.original_pack = ColorSet.rgba_to_saber
        self.original_getattribute = Mesh.__getattribute__

    def projection(self, count=2):
        return host.ProjectionGuard(
            self.Mesh, self.ColorSet, self.cache,
            source_is_open=lambda: self.opened,
            is_mesh_object=lambda obj: isinstance(obj, MeshObject),
            expected_reads=count)

    def test_preopen_calls_pass_through_then_one_guard_spans_all_rows(self):
        white = MeshObject(EqualColor((1.0, 1.0, 1.0, 1.0)))
        gray = MeshObject(EqualColor((0.2, 0.3, 0.4, 1.0)))
        projection = self.projection()
        with projection:
            self.assertEqual(self.Mesh().b_read(white), 0xFFFFFFFF)
            self.assertEqual(projection.reads, 0)
            self.assertIs(self.ColorSet.rgba_to_saber, self.original_pack)
            self.opened = True
            self.assertEqual(self.Mesh().b_read(white), 0xFFFFFFFF)
            self.assertEqual(projection.reads, 1)
            self.assertIsNot(self.ColorSet.rgba_to_saber, self.original_pack)
            self.assertEqual(set(self.cache), {tuple(white.rgba)})
            self.assertEqual(self.Mesh().b_read(gray), 0xFF334C66)
            self.assertEqual(self.cache, {})
            self.assertIs(self.ColorSet.rgba_to_saber, self.original_pack)
        self.assertEqual(projection.reads, 2)
        self.assertEqual(projection.contexts_entered, 1)
        self.assertEqual(projection.guard_state["packCalls"], 2)
        self.assertTrue(projection.hook_restored)
        self.assertTrue(projection.guard_state["cacheClearedAfter"])
        self.assertIs(self.Mesh.__getattribute__, self.original_getattribute)
        self.assertEqual(self.cache, {})

    def test_projection_error_restores_packer_and_class_hook(self):
        projection = self.projection()
        self.opened = True
        with self.assertRaisesRegex(RuntimeError, "projection failed"):
            with projection:
                self.Mesh().b_read(MeshObject((1.0, 1.0, 1.0, 1.0)))
                self.Mesh().b_read(MeshObject((0.0, 0.0, 0.0, 1.0), fail=True))
        self.assertEqual(projection.reads, 1)
        self.assertTrue(projection.guard_state["restored"])
        self.assertTrue(projection.hook_restored)
        self.assertIs(self.ColorSet.rgba_to_saber, self.original_pack)
        self.assertIs(self.Mesh.__getattribute__, self.original_getattribute)

    def test_incomplete_or_wrong_source_call_fails_closed_and_restores(self):
        projection = self.projection()
        self.opened = True
        with self.assertRaisesRegex(host.GuardedReadbackError, "cover and restore"):
            with projection:
                self.Mesh().b_read(MeshObject((0.0, 0.0, 0.0, 1.0)))
        self.assertIs(self.ColorSet.rgba_to_saber, self.original_pack)
        self.assertIs(self.Mesh.__getattribute__, self.original_getattribute)

        projection = self.projection()
        with self.assertRaisesRegex(host.GuardedReadbackError, "shape"):
            with projection:
                self.Mesh().b_read(MeshObject((1.0, 1.0, 1.0, 1.0)))
                self.Mesh().b_read(object())
        self.assertTrue(projection.hook_restored)
        self.assertTrue(projection.guard_state["restored"])
        self.assertIs(self.ColorSet.rgba_to_saber, self.original_pack)


if __name__ == "__main__":
    unittest.main()
