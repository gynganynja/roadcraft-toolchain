"""Tracked-vehicle support checks (roadcraft.tracks, RC046-RC048) on KGS25-shaped fixtures.

KGS25 candidate 03 (2026-10-02): real idler/sprocket 0.30-0.33 m above seven stop fakes per track,
2.5 t welded track frames of 41,180 kg: one track sank 19 cm in pivot turns (editor bench). Fix 2:
the retail EPEC layout (end road wheels real and rigid) and 7.5 t frames held roll to 0.2 deg.
"""

import unittest

from roadcraft import bro_lint, tracks
from roadcraft.tpl_reader import TplNodes

STOPS = {"min": 0, "max": 0.22, "height": 0.05, "strength": 0.0013, "damping": 0.55}
RIGID = {"min": 0, "max": 0, "height": 0, "strength": 1, "damping": 0.85}
SPRUNG = {"min": -0.13, "max": 0.13, "height": 0.06, "strength": 0.05, "damping": 0.75}
CONTACT_Z = (-2.275, -1.515, -0.75, 0.0, 0.785, 1.525, 2.285)


def matrix(x, y, z):
    return (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, x, y, z, 1)


def model(frame_under_chassis=True):
    """Native positions (X left, Y up, Z forward) of the left track of the KGS25."""
    names = ["BoneChassis_cdt", "BoneTrackSusp_L_cdt", "kgs_L_idler0", "kgs_L_drive0"] + \
            [f"kgs_L_contact{i}" for i in range(7)]
    mats = [matrix(0, 0, 0), matrix(1.385, 0.5, 0), matrix(1.385, 0.7, -2.975), matrix(1.385, 0.7, 2.985)]
    mats += [matrix(1.385, 0.265, z) for z in CONTACT_Z]
    parents = [-1, 0] + [1 if frame_under_chassis else 0] * 9
    return TplNodes(names=names, index={n: i for i, n in enumerate(names)}, matrices=mats, parents=parents)


def truck(contact_axle, *, real_ends=False, end_axle="Fixed"):
    slots = [{"geomName": "kgs_L_idler0", "editableWheel": "idler", "suspensionCollectionItem": "Fixed"},
             {"geomName": "kgs_L_drive0", "editableWheel": "drive", "suspensionCollectionItem": "Fixed"}]
    for i in range(7):
        end = real_ends and i in (0, 6)
        slots.append({"geomName": f"kgs_L_contact{i}", "editableWheel": "contact",
                      "suspensionCollectionItem": end_axle if end else "Contact"})
    real = [0, 1, 2, 8] if real_ends else [0, 1]
    fake = [3, 4, 5, 6, 7] if real_ends else [2, 3, 4, 5, 6, 7, 8]
    return {"wheelPool": {"idler": {"scale": 0.3}, "drive": {"scale": 0.33}, "contact": {"scale": 0.2}},
            "truckSettings": {"useSuspensionCollection": True,
                              "suspensionCollection": {"Fixed": dict(RIGID), "Contact": dict(contact_axle)},
                              "wheelSlots": slots,
                              "tracks": [{"wheelIds": real, "fakeWheelIds": fake,
                                          "parentTracker": {"locator": "BoneTrackSusp_L_cdt"}}]}}


def markup(frame_mass=2500, hull_mass=19900, joint="tpl_markup_constraint_fixed", motor=None):
    def body(name, mass, entity=None):
        info = {"objectId": {"name": name}, "properties": [
            {"massFromDensity": False, "mass": mass, "__type": "tpl_markup_object_property_physics"}]}
        if entity:
            info["entities"] = [{"name": name + "_joint", "target": "BoneChassis_cdt", "__type": entity}]
            if motor and "TrackSusp" in name:
                info["entities"][0]["motor"] = {"spring": 1e7, "damping": 1.1e7, "__type": motor}
        return info
    rest = 41180 - hull_mass - 2 * frame_mass
    return {"objectInfos": [body("BoneChassis_cdt", hull_mass), body("BoneTurret_cdt", rest, "tpl_markup_constraint_hinge"),
                            body("BoneTrackSusp_L_cdt", frame_mass, joint), body("BoneTrackSusp_R_cdt", frame_mass, joint)]}


def codes(found):
    return sorted(f[0] for f in found)


class AxleKindTests(unittest.TestCase):
    def test_retail_and_kgs_axles(self):
        self.assertEqual(tracks.axle_kind(RIGID), "rigid")                   # EPEC front, KGS Fixed
        self.assertEqual(tracks.axle_kind({"max": 0, "strength": 0.7}), "rigid")  # Greenway Idler
        self.assertEqual(tracks.axle_kind(STOPS), "stops")                   # KGS c03 contacts
        self.assertEqual(tracks.axle_kind({"min": 0, "max": 0.4, "strength": 0.001}), "stops")  # EPEC fakes
        self.assertEqual(tracks.axle_kind({"min": -0.2, "max": 0.2, "height": 0.2, "strength": 0.06}), "sprung")  # ETV89
        self.assertEqual(tracks.axle_kind(None), "stops")                    # engine default


class LayoutTests(unittest.TestCase):
    def test_bottoms_ground_flags_and_body(self):
        (track,) = tracks.track_layout(truck(STOPS), model())
        wheels = {w["geomName"]: w for w in track["wheels"]}
        self.assertAlmostEqual(wheels["kgs_L_contact3"]["bottom"], 0.065, places=3)
        self.assertAlmostEqual(wheels["kgs_L_idler0"]["bottom"], 0.4, places=3)
        self.assertTrue(wheels["kgs_L_contact0"]["ground"])
        self.assertFalse(wheels["kgs_L_drive0"]["ground"])
        self.assertEqual(wheels["kgs_L_contact0"]["body"], "BoneTrackSusp_L_cdt")

    def test_body_from_tracker_without_model(self):
        (track,) = tracks.track_layout(truck(STOPS))
        self.assertTrue(all(w["body"] == "BoneTrackSusp_L_cdt" for w in track["wheels"]))
        self.assertTrue(all(w["ground"] is None for w in track["wheels"]))


class FindingTests(unittest.TestCase):
    def test_candidate03_shape_flags_support_and_light_welded_frame(self):
        found = tracks.track_findings(truck(STOPS), model(), markup())
        self.assertEqual(codes(found), ["RC046", "RC047"])

    def test_fix2_shape_still_flags_its_welded_frames(self):
        # KGS25 fix 2 raised frame mass but kept the weld; the owner on the vanilla HT500: "the track
        # frames have springyness" (Game, 2026-10-13)
        doc = truck({"min": 0, "max": 0.4, "height": 0, "strength": 0.001}, real_ends=True)
        found = tracks.track_findings(doc, model(), markup(frame_mass=7500, hull_mass=9900))
        self.assertEqual(codes(found), ["RC047"])
        self.assertIn("spring_motor", found[0][2])
        self.assertEqual(tracks.stop_fake_axles(doc, model()), {"Contact"})

    def test_ht500_style_sprung_hinge_passes(self):
        doc = truck({"min": 0, "max": 0.4, "height": 0, "strength": 0.001}, real_ends=True)
        frames = markup(frame_mass=7500, hull_mass=9900, joint="tpl_markup_constraint_hinge",
                        motor="tpl_markup_spring_motor")
        self.assertEqual(tracks.track_findings(doc, model(), frames), [])

    def test_epec_layout_with_light_frames_still_warns_about_the_frame(self):
        doc = truck({"min": 0, "max": 0.4, "height": 0, "strength": 0.001}, real_ends=True)
        self.assertEqual(codes(tracks.track_findings(doc, model(), markup())), ["RC047"])

    def test_sprung_fakes_on_light_frame_are_reported_for_measurement(self):
        found = tracks.track_findings(truck(SPRUNG), model(), markup())
        self.assertEqual(codes(found), ["RC047", "RC048"])
        self.assertEqual([f[1] for f in found if f[0] == "RC048"], ["info"])

    def test_unsprung_hinged_bogie_is_rc047(self):
        found = tracks.track_findings(truck(SPRUNG), model(), markup(joint="tpl_markup_constraint_hinge"))
        self.assertEqual(codes(found), ["RC047", "RC048"])
        self.assertIn("no motor", [f for f in found if f[0] == "RC047"][0][2])

    def test_sprung_hinged_light_bogie_is_not_rc047(self):
        found = tracks.track_findings(truck(SPRUNG), model(), markup(joint="tpl_markup_constraint_hinge",
                                                                     motor="tpl_markup_spring_motor"))
        self.assertEqual(codes(found), ["RC048"])

    def test_wheels_on_root_body_have_no_frame_findings(self):
        doc = truck(SPRUNG)
        doc["truckSettings"]["tracks"][0].pop("parentTracker")
        self.assertEqual(tracks.track_findings(doc, model(frame_under_chassis=False), markup()), [])


class LintWiringTests(unittest.TestCase):
    def test_lint_reports_track_codes_with_the_article(self):
        found = bro_lint.lint_truck(truck(STOPS), model=model(), markup=markup())
        mine = [f for f in found if f["code"] in ("RC046", "RC047")]
        self.assertEqual(sorted(f["code"] for f in mine), ["RC046", "RC047"])
        self.assertTrue(all(f["library"] == "library/tracked-vehicles.md" for f in mine))

    def test_epec_stop_fakes_are_info_not_bump_stop_warnings(self):
        doc = truck({"min": 0, "max": 0.4, "height": 0, "strength": 0.001}, real_ends=True)
        found = bro_lint.lint_truck(doc, model=model(), markup=markup(frame_mass=7500, hull_mass=9900))
        contact = [f for f in found if f["where"].endswith("suspensionCollection.Contact")]
        self.assertEqual([(f["code"], f["severity"]) for f in contact], [("RC005", "info")])
        rigid = [f for f in found if f["where"].endswith("suspensionCollection.Fixed") and f["code"] == "RC004"]
        self.assertEqual(rigid, [])


if __name__ == "__main__":
    unittest.main()
