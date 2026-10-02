import unittest

from roadcraft import bro_lint


def truck(particles, enabled=True):
    return {"loadVolumeSettings": {"isEnabled": enabled, "volumeMesh": "hidden__load_volume",
                                   "particleLoadVolumeSettings": particles}}


class LoadVolumeEffectTests(unittest.TestCase):
    def codes(self, doc):
        return {f["code"] for f in bro_lint.lint_truck(doc)}

    def test_refill_stream_fixed_in_truck_space_is_flagged(self):
        # Dump Twuck v2: (0, 2, -1.5) in truck space put the refill stream under the tray.
        doc = truck({"sfxRefillActor": "sfx_sand_refill",
                     "sfxRefillLocalPosition": {"y": 2, "z": -1.5, "__type": "Vector3d"}})
        self.assertIn("RC035", self.codes(doc))

    def test_refill_stream_following_the_load_volume_is_accepted(self):
        # Shipped Aramatsu Bowhead pattern.
        doc = truck({"sfxRefillActor": "sfx_sand_refill", "sfxMovableDumpPositionBone": "_load_volume",
                     "sfxRefillLocalPosition": {"y": 4.5, "z": -1.5, "__type": "Vector3d"}})
        self.assertNotIn("RC035", self.codes(doc))

    def test_disabled_load_volume_is_ignored(self):
        doc = truck({"sfxRefillActor": "sfx_sand_refill"}, enabled=False)
        self.assertNotIn("RC035", self.codes(doc))


if __name__ == "__main__":
    unittest.main()
