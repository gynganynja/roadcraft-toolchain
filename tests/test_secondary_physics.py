import math
import unittest

from roadcraft.vehicle import child_rotation, euler_axis, euler_x_axis, ragdoll_child_rotation


class RagdollRotationTest(unittest.TestCase):
    def test_retail_whip_antenna(self):
        # ai_truck_asphalt_2cargo BoneAntenna_cdt: identity bone, childRotation [0, 0, 90], twist up
        self.assertEqual(ragdoll_child_rotation((0, 1, 0)), [0, 0.0, 90.0])

    def test_round_trip(self):
        for axis in [(1, 0, 0), (0, 0, 1), (0, 0, -1), (0.3, 0.8, -0.5), (-1, 0.2, 0.1)]:
            n = math.sqrt(sum(a * a for a in axis))
            got = euler_x_axis(ragdoll_child_rotation(axis))
            for a, b in zip(got, axis):
                self.assertAlmostEqual(a, b / n, places=4)

    def test_hinge_axes_used_by_the_l275_swinging_parts(self):
        self.assertEqual(child_rotation((1, 0, 0)), [0, 90.0, 0])     # mudflaps, retail mudguard
        self.assertEqual(child_rotation((0, 1, 0)), [-90.0, 0.0, 0])  # reel swing, flag panels
        for rot, axis in [([0, 90, 0], (1, 0, 0)), ([-90, 0, 0], (0, 1, 0))]:
            for a, b in zip(euler_axis(rot), axis):
                self.assertAlmostEqual(a, b, places=6)


if __name__ == '__main__':
    unittest.main()
