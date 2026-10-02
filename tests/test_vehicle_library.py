"""Tests of the vehicle-authoring library code: PS text, compiled model reader, suspension model,
BRO pitfall checks, retail data access and the article index."""

from __future__ import annotations

import math
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path

from roadcraft import bro_lint, library, ps_format, retail, tpl_reader, vehicle


def _identity_at(x: float, y: float, z: float) -> list[float]:
    return [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, x, y, z, 1]


def _tpl_bytes(names: list[str], parents: list[int], positions: dict[str, tuple[float, float, float]],
               extra_nodes: int = 0) -> bytes:
    """A minimal byte layout with the node table and parent array of a compiled model."""
    nodes = len(names) + extra_nodes
    table = struct.pack("<IB", len(names), 1)
    for name in names:
        table += struct.pack("<I", len(name)) + name.encode()
    table += struct.pack("<I", len(names)) + struct.pack(f"<{len(names)}H", *range(len(names)))
    table += struct.pack("<I", nodes)
    for index in range(nodes):
        where = positions.get(names[index], (0.0, 0.0, 0.0)) if index < len(names) else (0.0, 0.0, 0.0)
        table += struct.pack("<16f", *_identity_at(*where))
    return b"\x07" * 13 + struct.pack(f"<{nodes}h", *parents) + b"\x05" * 9 + table + b"\x00" * 8


class PsFormatTests(unittest.TestCase):
    def test_round_trip_keeps_values_and_types(self) -> None:
        doc = {"tpl": "mod", "truckSettings": {"diffLock": False, "maxSteerSpeed": 0.03, "count": 4,
                                                "wheelSlots": [{"geomName": "w", "steeringAngle": -14}],
                                                "curve": [0, 1.5, 30]},
               "scroll": {"0": {"distance": 9.5}}}
        self.assertEqual(ps_format.loads(ps_format.dumps(doc)), doc)

    def test_top_level_commas_and_bom_are_accepted(self) -> None:
        self.assertEqual(ps_format.loads("﻿a = 1, b = \"x\""), {"a": 1, "b": "x"})

    def test_unclosed_object_is_an_error(self) -> None:
        with self.assertRaises(ps_format.PsSyntaxError):
            ps_format.loads("a = { b = 1")


class TplReaderTests(unittest.TestCase):
    names = ["BoneChassis_cdt", "BoneWheelFrontLeft", "Bone_IK_arm_Base", "Bone_IK_arm_Rod", "BoneRocker_cdt"]
    parents = [-1, 0, 0, 2, 0]

    def test_reads_names_positions_and_parents(self) -> None:
        data = _tpl_bytes(self.names, self.parents, {"BoneWheelFrontLeft": (1.2, 0.4, 1.8)})
        found = tpl_reader.read_tpl_bytes(data, anchor="BoneWheelFrontLeft")
        self.assertEqual(found.names, self.names)
        self.assertEqual(found.position("BoneWheelFrontLeft"), (1.2000000476837158, 0.4000000059604645, 1.7999999523162842))
        self.assertEqual(found.parent("Bone_IK_arm_Rod"), "Bone_IK_arm_Base")
        self.assertEqual(found.children("BoneChassis_cdt"), ["BoneWheelFrontLeft", "Bone_IK_arm_Base", "BoneRocker_cdt"])

    def test_names_with_spaces_and_unnamed_nodes(self) -> None:
        names = ["root node", "BoneA", "BoneB"]
        found = tpl_reader.read_tpl_bytes(_tpl_bytes(names, [-1, 0, 1, 0], {}, extra_nodes=1), anchor="BoneA")
        self.assertEqual(len(found.matrices), 4)
        self.assertEqual(found.parent("BoneB"), "BoneA")

    def test_missing_table_is_reported(self) -> None:
        with self.assertRaises(tpl_reader.TplFormatError):
            tpl_reader.read_tpl_bytes(b"\x00" * 64)


class SuspensionModelTests(unittest.TestCase):
    def test_designed_axle_rests_at_its_lift(self) -> None:
        axle = vehicle.design_axle(0.16, 0.205, lift=0.06, bump=0.16, droop=0.20)
        self.assertAlmostEqual(vehicle.rest_position(axle, 0.205), 0.06, places=3)
        self.assertAlmostEqual(axle["min"], -0.10)
        self.assertAlmostEqual(axle["max"], 0.26)

    def test_height_zero_sinks_by_the_whole_sag(self) -> None:
        axle = {"min": -0.15, "max": 0.18, "height": 0.0, "strength": 0.014}
        report = vehicle.axle_report(axle, 0.25)
        self.assertTrue(report["cases"]["expected"]["onBumpStop"])

    def test_report_includes_the_measured_beta(self) -> None:
        axle = vehicle.design_axle(0.16, 0.205, lift=0.06, bump=0.16, droop=0.20)
        measured = vehicle.axle_report(axle, 0.205)["cases"]["measured"]
        self.assertEqual(measured["beta"], vehicle.SUSPENSION_BETA_MEASURED)
        self.assertGreater(measured["rest"], 0.06)       # a stiffer spring than designed rides higher

    def test_calibration_recovers_the_beta_that_produced_the_rests(self) -> None:
        shares = {"front": 0.2, "rear": 0.3}
        axles = {key: vehicle.design_axle(0.12, share, lift=0.05, bump=0.2, droop=0.3) for key, share in shares.items()}
        seen = [{"axle": axles[key], "rest": vehicle.rest_position(axles[key], shares[key], 80.0), "wheels": 2}
                for key in shares]
        result = vehicle.calibrate_beta(seen)
        self.assertAlmostEqual(result["beta"], 80.0, places=1)
        self.assertAlmostEqual(result["shares"][0], 0.2, places=3)

    def test_calibration_refuses_an_axle_on_its_stop(self) -> None:
        axle = {"min": -0.1, "max": 0.2, "height": 0.2, "strength": 0.02}
        with self.assertRaises(ValueError):
            vehicle.calibrate_beta([{"axle": axle, "rest": 0.2, "wheels": 2}])

    def test_hinge_rotation_round_trip(self) -> None:
        for axis in ((0.0, 1.0, 0.0), (1.0, 0.0, 0.0), (0.0, -0.5, 0.866)):
            back = vehicle.euler_axis(vehicle.child_rotation(axis))
            norm = math.sqrt(sum(c * c for c in axis))
            for got, want in zip(back, axis):
                self.assertAlmostEqual(got, want / norm, places=4)

    def test_frame_conversion_round_trip(self) -> None:
        self.assertEqual(vehicle.native_to_rc(vehicle.rc_to_native((0.9, -1.3, 0.4))), (0.9, -1.3, 0.4))


def _truck(**settings) -> dict:
    base = {
        "wheelPool": {"Front": {"scale": 0.4}},
        "truckSettings": {"maxSteerSpeed": 0.03, "backSteerSpeed": 0.06, "pedalsResponsiveness": 0.35,
                          "useSuspensionCollection": True,
                          # native_suspension.design_axle(0.16, 0.25, lift=0.06): stops at height + min/max
                          "suspensionCollection": {"Front": {"min": -0.32, "max": 0.04, "height": 0.22,
                                                             "strength": 0.0269}},
                          "wheelSlots": [{"geomName": f"W{i}", "editableWheel": "Front",
                                          "suspensionCollectionItem": "Front"} for i in range(4)]},
        "ikSettings": {"useNamedChains": True, "chains": {}},
    }
    base["truckSettings"].update(settings)
    return base


def _codes(findings, severity=None) -> set[str]:
    return {f["code"] for f in findings if severity is None or f["severity"] == severity}


class BroLintTests(unittest.TestCase):
    def test_clean_document_has_no_errors_or_warnings(self) -> None:
        findings = bro_lint.lint_truck(_truck())
        self.assertFalse([f for f in findings if f["severity"] in ("error", "warning")], findings)

    def test_collection_without_flag(self) -> None:
        self.assertIn("RC001", _codes(bro_lint.lint_truck(_truck(useSuspensionCollection=False)), "error"))

    def test_missing_steering_speeds(self) -> None:
        doc = _truck()
        del doc["truckSettings"]["maxSteerSpeed"]
        self.assertIn("RC002", _codes(bro_lint.lint_truck(doc), "warning"))

    def test_earlier_design_formula_rests_on_its_top_stop(self) -> None:
        # vehicle.design_axle limits (min = lift - bump) put the top stop at height + min = 0.12, above the
        # designed rest of 0.06 (measured stop geometry, KGS25 bench / Lada trials, 2026-10-02)
        doc = _truck(suspensionCollection={"Front": {"min": -0.1, "max": 0.26, "height": 0.22, "strength": 0.0269}})
        self.assertIn("RC005", _codes(bro_lint.lint_truck(doc), "warning"))

    def test_height_zero_and_bump_stop(self) -> None:
        doc = _truck(suspensionCollection={"Front": {"min": -0.15, "max": 0.18, "height": 0, "strength": 0.014}})
        codes = _codes(bro_lint.lint_truck(doc), "warning")
        self.assertTrue({"RC004", "RC005"} <= codes)

    def test_constraint_count_review_catches_missing_and_extra_entries(self) -> None:
        for count in (0, 1, 2, 4):
            with self.subTest(constraints=count):
                doc = _truck()
                doc["ikSettings"]["chains"] = {"drag": {
                    "ikChainBodies": ["Base", "Pitman", "Rod", "Joint"],
                    "ikConstraints": [{"type": "HINGE2"}] * count}}
                findings = bro_lint.lint_truck(doc)
                self.assertIn("RC014", _codes(findings, "warning"))
                self.assertNotIn("RC014", _codes(findings, "error"))

    def test_complete_constraint_count_and_empty_chains_are_clean(self) -> None:
        doc = _truck()
        doc["ikSettings"]["chains"] = {"drag": {
            "ikChainBodies": ["Base", "Pitman", "Rod", "Joint"],
            "ikConstraints": [{"type": "HINGE2"}] * 3},
            "empty": {"ikChainBodies": ["Base"], "ikConstraints": []}}
        self.assertNotIn("RC014", _codes(bro_lint.lint_truck(doc)))

    def test_chain_on_a_wheel_slot_needs_the_axle_controller(self) -> None:
        doc = _truck()
        doc["ikSettings"]["chains"] = {"arm": {"ikChainBodies": ["BoneChassis_cdt", "A", "B"],
                                               "effectors": [{"bodyPhysName": "W0", "bodyIKName": "B"}]}}
        names = ["BoneChassis_cdt", "W0", "A", "B"]
        model = tpl_reader.read_tpl_bytes(_tpl_bytes(names, [-1, 0, 0, 2], {}))
        self.assertIn("RC010", _codes(bro_lint.lint_truck(doc), "warning"))
        self.assertIn("RC010", _codes(bro_lint.lint_truck(doc, model=model), "error"))
        doc["axleControllerSettings"] = {"independentAxleSettings": [{"frameName": "W0", "isIndependent": True}]}
        self.assertNotIn("RC010", _codes(bro_lint.lint_truck(doc, model=model)))

    def test_slot_under_a_moving_body_is_not_flagged(self) -> None:
        doc = _truck()
        doc["ikSettings"]["chains"] = {"arm": {"ikChainBodies": ["BoneChassis_cdt", "A", "B"],
                                               "effectors": [{"bodyPhysName": "W0", "bodyIKName": "B"}]}}
        names = ["BoneChassis_cdt", "BoneRocker_cdt", "W0", "A", "B"]
        model = tpl_reader.read_tpl_bytes(_tpl_bytes(names, [-1, 0, 1, 0, 3], {}))
        self.assertNotIn("RC010", _codes(bro_lint.lint_truck(doc, model=model)))

    def test_compiled_class_that_lost_settings(self) -> None:
        doc = _truck()
        doc["axleControllerSettings"] = {"independentAxleSettings": [{"frameName": "W0"}]}
        codes = _codes(bro_lint.lint_truck(doc, compiled_class="prop_truck_rb = { }"), "error")
        self.assertTrue({"RC030", "RC031"} <= codes)

    def test_model_must_hold_lamp_and_dashboard_names(self) -> None:
        doc = _truck()
        doc["dataDashboard"] = {"dashboard": {"Speed": {"nameBone": "ctrl_dashboard_speed"}}}
        doc["blueprint"] = {"nodes": {"n": {"__type": "BlueprintNodeShowHideGeomObjects",
                                            "objNameRef": {"def": ["tail_lights_on"]}}}}
        codes = _codes(bro_lint.lint_truck(doc, model=["W0", "W1", "W2", "W3"]), "error")
        self.assertTrue({"RC021", "RC022"} <= codes)


class RetailTests(unittest.TestCase):
    def test_reads_bros_members_and_survey(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp)
            (game / "root/prebuild/bro").mkdir(parents=True)
            truck = ps_format.dumps(_truck() | {"tpl": "scout"})
            with zipfile.ZipFile(game / "root/prebuild/bro/Bro.Compiled.pak", "w") as pak:
                pak.writestr("designer_wizard/trucks/scout.bro", truck)
            (game / "root/paks/client/default").mkdir(parents=True)
            with zipfile.ZipFile(game / "root/paks/client/default/default_tpl_1.pak", "w") as pak:
                pak.writestr("models/database/vehicles/scout.tpl.asset/scout.tpl_markup",
                             "objectInfos = [ { properties = [ { mass = 1800 } ] } ]")
            retail._INDEX.clear()
            self.assertEqual(retail.retail_bro(game, "scout")["tpl"], "scout")
            self.assertEqual(len(retail.find_members(game, "*scout.tpl_markup")), 1)
            self.assertEqual([name for name, _ in retail.find_members(game, "designer_wizard/*")],
                             ["designer_wizard/trucks/scout.bro"])
            survey = retail.suspension_survey(game)
            self.assertEqual(survey["axles"], 1)
            self.assertAlmostEqual(survey["medianBeta"], round(1 / (4 * 0.0269 * 0.22), 2))
            with self.assertRaises(retail.RetailDataError):
                retail.read_member(game, "missing/file")


class LibraryTests(unittest.TestCase):
    def test_topics_articles_and_search(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "wheels.md").write_text("# Wheels and slots\n\n## Display\nThe model shows unchanged.\n",
                                            encoding="utf-8")
            (root / "lamps.md").write_text("Lamps without a heading\n", encoding="utf-8")
            self.assertEqual([t["topic"] for t in library.topics(root)], ["lamps", "wheels"])
            self.assertEqual(library.topics(root)[1]["title"], "Wheels and slots")
            hits = library.search("unchanged", root)
            self.assertEqual((hits[0]["topic"], hits[0]["heading"]), ("wheels", "Display"))
            with self.assertRaises(LookupError):
                library.article("missing", root)


if __name__ == "__main__":
    unittest.main()
