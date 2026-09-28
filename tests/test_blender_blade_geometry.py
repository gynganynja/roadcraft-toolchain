"""Independent numeric cases for the read-only blade geometry comparison."""

from __future__ import annotations

import math
import unittest

from roadcraft.blender_blade_geometry import compare_arrays


IDENTITY = ((1.0, 0.0, 0.0, 0.0),
            (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0),
            (0.0, 0.0, 0.0, 1.0))
POINTS = ((0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (0.0, 3.0, 0.0),
          (0.0, 0.0, 4.0), (2.0, 1.0, 0.0), (1.0, 0.0, 3.0))
NORMALS = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0),
           (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


class BladeGeometryMathTests(unittest.TestCase):
    def test_parent_compensation_and_proper_rigid_fit(self) -> None:
        # Repaired local vertices are rotated/translated while their node world
        # matrix cancels that transform. Normals rotate with inverse transpose.
        transformed = tuple((-p[1]+5.0, p[0]+2.0, p[2]-1.0) for p in POINTS)
        rotated_normals = tuple((-n[1], n[0], n[2]) for n in NORMALS)
        repaired_world = ((0.0, 1.0, 0.0, -2.0),
                          (-1.0, 0.0, 0.0, 5.0),
                          (0.0, 0.0, 1.0, 1.0),
                          (0.0, 0.0, 0.0, 1.0))
        result = compare_arrays(POINTS, transformed, NORMALS, rotated_normals,
                                IDENTITY, repaired_world, IDENTITY, IDENTITY)
        self.assertGreater(result["localPositions"]["max"], 1.0)
        self.assertLess(result["parentCompensatedLocalPositions"]["max"], 1e-12)
        self.assertLess(result["worldPositions"]["max"], 1e-12)
        self.assertLess(result["properRigidFit"]["max"], 1e-12)
        self.assertAlmostEqual(result["properRigidFit"]["determinant"], 1.0)
        self.assertLess(result["normals"]["maxAngleDegrees"], 1e-5)
        self.assertLess(result["normals"]["pairwiseDotMaxDifference"], 1e-12)

    def test_normal_invariant_exposes_change_without_position_change(self) -> None:
        changed = list(NORMALS)
        changed[0] = (0.0, 1.0, 0.0)
        result = compare_arrays(POINTS, POINTS, NORMALS, changed,
                                IDENTITY, IDENTITY, IDENTITY, IDENTITY)
        self.assertEqual(result["worldPositions"]["max"], 0.0)
        self.assertEqual(result["properRigidFit"]["max"], 0.0)
        self.assertEqual(result["normals"]["over0p1Degrees"], 1)
        self.assertAlmostEqual(result["normals"]["maxAngleDegrees"], 90.0)
        self.assertAlmostEqual(result["normals"]["pairwiseDotMaxDifference"], 1.0)

    def test_affine_parent_compensation_uses_inverse_transpose_normals(self) -> None:
        scaled = tuple((2*p[0], p[1], p[2]) for p in POINTS)
        unit = 1/math.sqrt(2)
        before = ((unit, unit, 0.0),)*6
        factor = 1/math.sqrt(1.25)
        after = ((0.5*factor, factor, 0.0),)*6
        repaired_world = ((0.5, 0.0, 0.0, 0.0),
                          (0.0, 1.0, 0.0, 0.0),
                          (0.0, 0.0, 1.0, 0.0),
                          (0.0, 0.0, 0.0, 1.0))
        result = compare_arrays(POINTS, scaled, before, after,
                                IDENTITY, repaired_world, IDENTITY, IDENTITY)
        self.assertLess(result["parentCompensatedLocalPositions"]["max"], 1e-12)
        self.assertLess(result["worldPositions"]["max"], 1e-12)
        self.assertLess(result["normals"]["maxAngleDegrees"], 1e-5)
        self.assertGreater(result["properRigidFit"]["max"], 0.1)

    def test_reflection_cannot_pass_proper_rigid_fit(self) -> None:
        reflected = tuple((-p[0], p[1], p[2]) for p in POINTS)
        result = compare_arrays(POINTS, reflected, NORMALS, NORMALS,
                                IDENTITY, IDENTITY, IDENTITY, IDENTITY)
        self.assertGreater(result["properRigidFit"]["max"], 0.1)
        self.assertAlmostEqual(result["properRigidFit"]["determinant"], 1.0)


if __name__ == "__main__":
    unittest.main()
