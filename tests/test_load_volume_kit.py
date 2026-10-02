import unittest

from roadcraft import bro_lint, load_volume as lv


def box(lo, hi):
    """12 triangles of an axis-aligned box."""
    (x0, y0, z0), (x1, y1, z1) = lo, hi
    v = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    return [tri for a, b, c, d in quads for tri in ((v[a], v[b], v[c]), (v[a], v[c], v[d]))]


def prism(poly, z0, z1):
    """Triangles of a convex polygon (counter-clockwise in x/y) extruded from z0 to z1."""
    bottom = [(x, y, z0) for x, y in poly]
    top = [(x, y, z1) for x, y in poly]
    tris = [(bottom[0], bottom[i + 1], bottom[i]) for i in range(1, len(poly) - 1)]
    tris += [(top[0], top[i], top[i + 1]) for i in range(1, len(poly) - 1)]
    for i in range(len(poly)):
        j = (i + 1) % len(poly)
        tris += [(bottom[i], bottom[j], top[j]), (bottom[i], top[j], top[i])]
    return tris


# Dump Twuck: bed pivot (0, 3.677, 4.2), tail lid under the bed.
FRAMES = {"BoneChassis_cdt": (None, (0.0, 0.0, 0.0)), "BoneDump_cdt": ("BoneChassis_cdt", (0.0, 3.677, 4.2)),
          "BoneSandCap_cdt": ("BoneDump_cdt", (0.0, 6.58, 4.5))}
PIVOT = FRAMES["BoneDump_cdt"][1]


def borders(thickness=.05, back_shift=(0, 0, 0)):
    w = thickness
    out = {"left": box((3.9 - w, -1.65, 4.5), (3.9, 6.0, 6.95)), "right": box((-3.9, -1.65, 4.5), (-3.9 + w, 6.0, 6.95)),
           "front": box((-3.9, -1.759, 4.5), (3.9, -1.759 + w, 6.85)), "back": box((-3.9, 6.1, 6.0), (3.9, 7.3, 6.86))}
    out["back"] = lv.shifted(out["back"], back_shift)
    return out


# A heap meeting the walls whose front corners are rounded off, as a convex hull of a sampled heap is.
HULL = prism([(-3.6, -1.745), (3.6, -1.745), (3.9, -1.6), (3.9, 7.3), (-3.9, 7.3), (-3.9, -1.6)], 4.5, 7.2)


class FrameTests(unittest.TestCase):
    def test_back_border_composes_with_its_parent(self):
        self.assertEqual(lv.composition_shift("back", "BoneSandCap_cdt", "BoneDump_cdt", FRAMES), (0, 0, 0))
        self.assertEqual(lv.composition_shift("back", "BoneDump_cdt", "BoneDump_cdt", FRAMES), (0, 3.677, 4.2))

    def test_side_borders_and_volume_read_their_own_parent(self):
        self.assertEqual(lv.composition_shift("left", "BoneDump_cdt", "BoneDump_cdt", FRAMES), (0, 0, 0))
        shift = lv.composition_shift("left", "BoneSandCap_cdt", "BoneDump_cdt", FRAMES)
        self.assertAlmostEqual(shift[1], 3.677 - 6.58)
        self.assertEqual(lv.composition_shift("volume", "BoneDump_cdt", "BoneDump_cdt", FRAMES), (0, 0, 0))


class GridTests(unittest.TestCase):
    def test_rectangle_insets_and_cell_counts(self):
        g = lv.grid_rect(borders())
        self.assertAlmostEqual(g["minX"], -3.89)
        self.assertAlmostEqual(g["maxX"], 3.89)
        self.assertAlmostEqual(g["frontY"], -1.749)
        self.assertAlmostEqual(g["rearY"], 7.1)
        self.assertEqual((g["nx"], g["ny"]), (31, 32))   # 35.9 cells along y clamp to 32

    def test_fitted_borders_leave_no_cell_at_the_pivot(self):
        report = lv.emulate(HULL, borders(), PIVOT)
        self.assertEqual(report["pivotCells"], [])
        self.assertEqual(lv.grid_findings(report), [])

    def test_back_border_under_the_bed_hangs_a_curtain(self):
        # Revision 3: the bed pivot applied twice pushed the grid 3.7 m past the tail.
        shift = lv.composition_shift("back", "BoneDump_cdt", "BoneDump_cdt", FRAMES)
        report = lv.emulate(HULL, borders(back_shift=shift), PIVOT)
        self.assertGreater(report["grid"]["rearY"], 10.7)
        self.assertGreater(len(report["pivotCells"]), 100)
        codes = {c for c, _, _ in lv.grid_findings(report, {"back": shift}, {"min": (-3.99, -2, 0), "max": (3.99, 7.8, 9)})}
        self.assertTrue({"RC040", "RC042", "RC044"} <= codes)

    def test_thin_edge_border_is_missed_by_the_nudged_samples(self):
        # Dump Twuck v5's 2 cm front slab: corner samples move 1/64 m inward, off the slab and past the heap.
        thin = lv.emulate(HULL, borders(thickness=.02), PIVOT)
        self.assertEqual(len(thin["pivotCells"]), 2)
        self.assertEqual(lv.emulate(HULL, borders(thickness=lv.BORDER_THICKNESS), PIVOT)["pivotCells"], [])

    def test_sheet_range_and_edge_steps(self):
        tall = lv.emulate(box((-3.9, -1.6, 4.5), (3.9, 7.3, 8.6)), borders(), PIVOT)
        self.assertIn("RC041", {c for c, _, _ in lv.grid_findings(tall)})
        low = borders()
        low["back"] = box((-3.9, 6.1, 4.6), (3.9, 7.3, 4.8))   # back block far below the sand beside it
        stepped = lv.emulate(box((-3.9, -1.6, 4.5), (3.9, 6.0, 7.6)), low, PIVOT)
        self.assertIn("RC043", {c for c, _, _ in lv.grid_findings(stepped)})


class SettingsTests(unittest.TestCase):
    NAMES = {"left": "b_left", "right": "b_right", "front": "b_front", "back": "b_back"}

    def test_settings_follow_the_shipped_shape(self):
        doc = lv.load_settings(volume="vol", parent_body="BoneDump_cdt", borders=self.NAMES, capacity=143.41,
                               mass=93032, lid={"constraint": "sand_cap", "open": "opened", "closed": "closed"},
                               refill_offset=(0, 9.75, -2))
        self.assertEqual(doc["bodySettings"]["backWall"], "b_back")
        self.assertEqual(doc["particleLoadVolumeSettings"]["sfxMovableDumpPositionBone"], "vol")
        self.assertAlmostEqual(doc["density"], round(93032 / 143.41, 4))
        self.assertTrue(doc["canBeDynamicallyOpened"] and doc["hydraulicLid"]["lidConstraint"] == "sand_cap")
        self.assertEqual(doc["loadVolumeWarningSettings"]["markerLocator"], "vol")
        self.assertEqual([f[0] for f in bro_lint.lint_truck({"loadVolumeSettings": doc}) if f["code"] == "RC035"], [])

    def test_open_backed_tub_and_refusals(self):
        open_back = {k: v for k, v in self.NAMES.items() if k != "back"}
        doc = lv.load_settings(volume="vol", parent_body="BoneCart_cdt", borders=open_back, capacity=7, mass=5000)
        self.assertNotIn("backWall", doc["bodySettings"])
        self.assertFalse(doc["canBeDynamicallyOpened"])
        with self.assertRaises(ValueError):
            lv.load_settings(volume="vol", parent_body="b", borders=open_back, capacity=7, mass=5000,
                             lid={"constraint": "lid", "open": "open", "closed": "close"})
        with self.assertRaises(ValueError):
            lv.load_settings(volume="vol", parent_body="b", borders={"left": "l"}, capacity=7, mass=5000)

    def test_settings_findings_and_markup(self):
        doc = lv.load_settings(volume="vol", parent_body="BoneDump_cdt", borders=self.NAMES, capacity=10, mass=1000)
        found = lv.settings_findings(doc, {"vol", "BoneDump_cdt", "b_left", "b_right", "b_front"})
        self.assertEqual([(c, s) for c, s, _ in found], [("RC036", "error")])
        self.assertIn("b_back", found[0][2])
        hidden = lv.hidden_markup(["vol"])
        self.assertIs(hidden["vol"]["visibility"]["visibleDefault"], False)
        self.assertEqual(hidden["vol"]["visibility"]["__type"], "tpl_markup_visibility_flags")


if __name__ == "__main__":
    unittest.main()
