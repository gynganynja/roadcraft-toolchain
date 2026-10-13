"""Pure numeric heap profiles; importing this helper must not require Blender."""
import math
import unittest

from roadcraft.blender_load import heap_top


class HeapTopTests(unittest.TestCase):
    def cone(self, **overrides):
        parameters = dict(side_x=3.9, crown_z=8.25, side_z=6.95, crown_y=2.0,
                          profile="elliptic_cone", cone_slope_y=.5)
        parameters.update(overrides)
        return heap_top(**parameters)

    def test_default_paraboloid_retains_legacy_values_and_caps(self):
        parameters = dict(side_x=3.9, crown_z=8.25, side_z=6.95, crown_y=2.0,
                          fall_y=.012, front=(-1.77, 7.0, 32), rear=(7.3, 5.0, 30))
        top = heap_top(**parameters)
        explicit = heap_top(**parameters, profile="paraboloid", cone_slope_y=.5)
        for x in (-4.2, -3.9, -1.3, 0, .3, 3.9):
            for y in (-2, -1.77, 0, 2, 4, 7.3, 8):
                with self.subTest(x=x, y=y):
                    expected = min(8.25 - (8.25 - 6.95) * (x / 3.9) ** 2 - .012 * (y - 2) ** 2,
                                   7.0 + math.tan(math.radians(32)) * (y + 1.77),
                                   5.0 + math.tan(math.radians(30)) * (7.3 - y))
                    self.assertEqual(top(x, y), expected)
                    self.assertEqual(explicit(x, y), expected)

    def test_cone_exact_crown_and_side_height(self):
        top = self.cone()
        self.assertEqual(top(0, 2), 8.25)
        self.assertEqual(top(-3.9, 2), 6.95)
        self.assertEqual(top(3.9, 2), 6.95)

    def test_cone_linear_drop_in_both_directions(self):
        top = self.cone()
        for distance in (.1, .5, 1, 2):
            for sign in (-1, 1):
                self.assertAlmostEqual(8.25 - top(0, 2 + sign * distance), .5 * distance)
                self.assertAlmostEqual(8.25 - top(sign * distance, 2), distance / 3)
        # The old crown loses only 4.8 cm over two metres; this one loses a metre.
        self.assertAlmostEqual(top(0, 4), 7.25)
        self.assertAlmostEqual(heap_top(side_x=3.9, crown_z=8.25, side_z=6.95,
                                       crown_y=2, fall_y=.012)(0, 4), 8.202)

    def test_cone_has_no_central_plateau(self):
        top = self.cone()
        for dx, dy in ((1, 0), (0, 1), (1, 1), (-1, 2)):
            heights = [top(dx * d, 2 + dy * d) for d in (0, .001, .01, .1, .25)]
            self.assertTrue(all(a > b for a, b in zip(heights, heights[1:])))
            self.assertAlmostEqual(8.25 - heights[3], 10 * (8.25 - heights[2]))

    def test_cone_diagonal_profile_and_symmetry_ignore_legacy_fall(self):
        top = self.cone(fall_y=100)
        expected = 8.25 - math.sqrt((1.3 / 3) ** 2 + (.5 * 2) ** 2)
        for x, y in ((1.3, 4), (-1.3, 4), (1.3, 0), (-1.3, 0)):
            self.assertAlmostEqual(top(x, y), expected)

    def test_front_and_rear_caps_still_cut_cone(self):
        front = (-1.77, 6.0, 32)
        rear = (7.3, 5.25, 30)
        raw = self.cone()
        top = self.cone(front=front, rear=rear)
        for x, y in ((0, -1.77), (2, -1), (0, 2), (-2, 6), (0, 7.3), (0, 8)):
            expected = min(raw(x, y), 6 + math.tan(math.radians(32)) * (y + 1.77),
                           5.25 + math.tan(math.radians(30)) * (7.3 - y))
            self.assertEqual(top(x, y), expected)
        self.assertEqual(top(0, -1.77), 6.0)
        self.assertEqual(top(0, 7.3), 5.25)
        self.assertEqual(top(0, 2), 8.25)

    def test_invalid_profile_or_nonpositive_nonfinite_cone_is_rejected(self):
        with self.assertRaises(ValueError):
            self.cone(profile="flat")
        for name in ("side_x", "crown_z", "side_z", "crown_y", "cone_slope_y"):
            for value in (float("inf"), float("-inf"), float("nan"), None):
                with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                    self.cone(**{name: value})
        for overrides in ({"side_x": 0}, {"side_x": -1}, {"cone_slope_y": 0},
                          {"cone_slope_y": -.5}, {"side_z": 8.25}, {"side_z": 9},
                          {"side_x": 1e-309, "crown_z": 1e308, "side_z": -1e308}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.cone(**overrides)

    def test_uncapped_cone_has_bounded_slopes(self):
        top = self.cone()
        # Norm of the elliptic-cone gradient is bounded by max(transverse, longitudinal).
        limit = .5
        for x in (-3.9, -1, 0, .25, 2.5, 3.9):
            for y in (-1, 1.5, 2, 2.25, 4):
                for dx, dy in ((.001, 0), (0, .001), (.001, .001), (.001, -.001)):
                    observed = abs(top(x + dx, y + dy) - top(x, y))
                    self.assertLessEqual(observed, limit * math.hypot(dx, dy) + 1e-12)


if __name__ == "__main__":
    unittest.main()
