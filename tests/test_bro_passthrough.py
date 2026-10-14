"""bro_passthrough: does a BRO field reach the compiled class?  Synthetic fixtures plus SDK-gated retail checks."""
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from roadcraft import bro_lint, bro_passthrough as bp, ps_format

GAME = Path(os.environ.get("ROADCRAFT_GAME_ROOT", r"C:\Program Files (x86)\Steam\steamapps\common\RoadCraft"))
SCHEMA = Path(os.environ.get("ROADCRAFT_SCHEMA_JSON", r"C:\RC_RE\research\schema.json"))
DECOMP = Path(os.environ.get("ROADCRAFT_BRO_DECOMP", r"C:\RC_RE\bro_passthrough\decomp_bro"))

TRUCK_TEMPLATE = {"tpl": "", "truckSettings": {"pedalsResponsiveness": 1, "__type": "TruckSettings"}, "__type": "Truck"}


def truck(name, steer, pedals, scale, ui):
    return {"tpl": name, "chassisInfo": {"uiName": ui, "__type": "ChassisInfo"},
            "truckSettings": {"maxSteerSpeed": steer, "pedalsResponsiveness": pedals, "oldKey": 7.77,
                              "__type": "TruckSettings"},
            "wheelPool": {"front": {"scale": scale, "wheel": {"__type": "WheelDemo"}, "__type": "EditableWheel"}},
            "__type": "Truck"}


WHEEL = {"truckWheel": {"width": 2.5, "mass": 321, "__type": "TruckWheel"}, "__type": "Wheel"}


def truck_class(name, steer, pedals, ui):
    rb = {"maxSteerSpeed": steer}
    if pedals != 1:
        rb["pedalsResponsiveness"] = pedals
    return {"properties": {"geom": {"nameTpl": name}, "prop_truck_view": {"displayName": ui}, "prop_truck_rb": rb}}


def wheel_class(scale):
    return {"properties": {"prop_truck_wheel": {"width": 2.5 * scale, "mass": 321}}}


def make_game(root: Path) -> None:
    (root / "root/prebuild/bro").mkdir(parents=True)
    (root / "root/paks/client/default").mkdir(parents=True)
    with zipfile.ZipFile(root / bp.BRO_PAK, "w") as pak:
        pak.writestr("designer_wizard/trucks/templates/truck.bro", ps_format.dumps(TRUCK_TEMPLATE))
        pak.writestr("designer_wizard/trucks/alpha.bro", ps_format.dumps(truck("alpha", 0.03, 0.2, 0.5, "UID_ALPHA")))
        pak.writestr("designer_wizard/trucks/beta.bro", ps_format.dumps(truck("beta", 0.05, 1, 0.8, "UID_BETA")))
        pak.writestr("designer_wizard/wheels/wheel_demo.bro", ps_format.dumps(WHEEL))
    with zipfile.ZipFile(root / bp.OTHER_PAK, "w") as pak:
        for name, steer, pedals, scale, ui in (("alpha", .03, .2, .5, "UID_ALPHA"), ("beta", .05, 1, .8, "UID_BETA")):
            base = f"{bp.CLS_PREFIX}auto_{name}/"
            pak.writestr(base + f"auto_{name}.cls", ps_format.dumps(truck_class(name, steer, pedals, ui)))
            pak.writestr(base + f"auto_wheel_{name}_front.cls", ps_format.dumps(wheel_class(scale)))


GENERATOR_CS = '''using System;

namespace designer_wizard.trucks.templates.truck;

public class Truck : GenaTemplate
{
\tpublic string tpl;

\tpublic TruckSettings truckSettings;

\tpublic ChassisInfo chassisInfo;

\tpublic SslDictionary<EditableWheel> wheelPool;
}
'''
SETTINGS_CS = '''namespace designer_wizard.trucks.templates.truck;

public class TruckSettings
{
\tpublic float maxSteerSpeed;

\tpublic float pedalsResponsiveness;

\tpublic bool useSuspensionCollection;
}
'''
GEN_CS = '''namespace designer_wizard.trucks.templates.truck_generator;

public class TruckGenerator
{
\tpublic Truck model;

\tpublic virtual void GenerateGeneric(ModelWrapper root)
\t{
\t\tModelWrapper orCreateProperty = utils.GetOrCreateProperty(root, "prop_truck_rb");
\t\tModelWrapper val = ((ModelWrapper)(ref orCreateProperty)).FindChild("maxSteerSpeed");
\t\t((ModelWrapper)(ref val)).Value = new RuntimeObject((object)model.truckSettings.maxSteerSpeed);
\t\tif (model.truckSettings.useSuspensionCollection)
\t\t{
\t\t\tModelWrapper val2 = ((ModelWrapper)(ref orCreateProperty)).FindChild("pedals");
\t\t\t((ModelWrapper)(ref val2)).Value = new RuntimeObject((object)(model.truckSettings.pedalsResponsiveness * 2f));
\t\t}
\t}
}
'''


class SyntheticRetailTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        make_game(root / "game")
        src = root / "cs"
        (src / "truck").mkdir(parents=True)
        (src / "truck/Truck.cs").write_text(GENERATOR_CS, encoding="utf-8")
        (src / "truck/TruckSettings.cs").write_text(SETTINGS_CS, encoding="utf-8")
        (src / "truck/TruckGenerator.cs").write_text(GEN_CS, encoding="utf-8")
        cls.src = src
        cls.result = bp.run(root / "game", generator_src=src)
        cls.fields = cls.result["fields"]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_pairs_both_trucks(self):
        self.assertEqual(self.result["retailTrucks"], 2)

    def test_same_name_passes(self):
        e = self.fields[".bro::TruckSettings.maxSteerSpeed"]
        self.assertEqual(e["status"], "passes")
        self.assertEqual(e["classPath"], "auto_<truck>.cls:properties/prop_truck_rb/maxSteerSpeed")
        self.assertEqual(e["evidence"]["matched"], 2)

    def test_default_value_is_elided_not_dropped(self):
        e = self.fields[".bro::TruckSettings.pedalsResponsiveness"]
        self.assertEqual(e["evidence"]["occurrences"].get("absent"), 1)
        self.assertEqual(e.get("omittedWhen"), 1)

    def test_undeclared_key_is_dropped_by_code(self):
        e = self.fields[".bro::TruckSettings.oldKey"]
        self.assertEqual(e["status"], "dropped")
        self.assertIn("no C# field", e["codeNote"])
        self.assertFalse(e["engineReads"])

    def test_value_under_another_name_is_renamed(self):
        e = self.fields[".bro::ChassisInfo.uiName"]
        self.assertEqual(e["status"], "renamed")
        self.assertTrue(e["classPath"].endswith("prop_truck_view/displayName"))

    def test_wheel_scale_transform(self):
        e = self.fields[".bro::TruckWheel.width"]
        self.assertEqual(e["status"], "transformed")
        self.assertEqual(e["rule"], "class = bro * wheelPool.<pool>.scale")
        self.assertEqual(self.fields[".bro::TruckWheel.mass"]["status"], "passes")

    def test_key_without_csharp_field_drops_its_subtree(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp)
            (src / "Truck.cs").write_text(GENERATOR_CS.replace("\tpublic ChassisInfo chassisInfo;\n", ""),
                                          encoding="utf-8")
            (src / "TruckSettings.cs").write_text(SETTINGS_CS, encoding="utf-8")
            fields = bp.run(Path(self.tmp.name) / "game", generator_src=src)["fields"]
        self.assertEqual(fields[".bro::ChassisInfo.uiName"]["status"], "dropped")
        self.assertIn("inside .bro::Truck.chassisInfo", fields[".bro::ChassisInfo.uiName"]["codeNote"])

    def test_deterministic(self):
        again = bp.run(Path(self.tmp.name) / "game", generator_src=self.src)
        self.assertEqual(json.dumps(again, sort_keys=True), json.dumps(self.result, sort_keys=True))


class CodeIndexTest(unittest.TestCase):
    def test_writes_reads_and_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp)
            (src / "Truck.cs").write_text(GENERATOR_CS, encoding="utf-8")
            (src / "TruckSettings.cs").write_text(SETTINGS_CS, encoding="utf-8")
            (src / "TruckGenerator.cs").write_text(GEN_CS, encoding="utf-8")
            index = bp.CodeIndex.scan(src)
        ev = index.evidence("TruckSettings", "maxSteerSpeed")
        self.assertEqual([w["to"] for w in ev["writes"]], ["properties/prop_truck_rb/maxSteerSpeed"])
        self.assertTrue(ev["writes"][0]["plain"])
        pedals = index.evidence("TruckSettings", "pedalsResponsiveness")["writes"][0]
        self.assertFalse(pedals["plain"])
        self.assertEqual(pedals["gate"], "if (model.truckSettings.useSuspensionCollection)")
        self.assertTrue(index.evidence("TruckSettings", "useSuspensionCollection")["reads"])
        self.assertIs(index.evidence("TruckSettings", "nope")["field"], False)


class RulesTest(unittest.TestCase):
    def test_constant_factor_named(self):
        rows = [{"value": 10.0, "classValue": 0.174533}, {"value": 90.0, "classValue": 1.570797}]
        self.assertEqual(bp.transform_rule(rows), "class = bro * 0.0174533 (degrees -> radians)")

    def test_offset(self):
        rows = [{"value": 1.0, "classValue": 0.5}, {"value": 3.0, "classValue": 2.5}]
        self.assertEqual(bp.transform_rule(rows), "class = bro + -0.5")

    def test_camel(self):
        self.assertEqual(bp.camel("chassis_kronenwerk_l_34_fork"), "ChassisKronenwerkL34Fork")


class LintTest(unittest.TestCase):
    TABLE = {"dropped": {"Truck.propSfx": "no C# field"}, "engineIgnored": {"LoadVolumeSettings.openingDelay": "x"},
             "typeChains": {"ChassisDemo": ["ChassisDemo", "Truck"]}}

    def test_dropped_and_ignored(self):
        doc = {"propSfx": {}, "loadVolumeSettings": {"openingDelay": 2, "__type": "LoadVolumeSettings"},
               "__type": "ChassisDemo"}
        found = {(f["code"], f["severity"], f["where"]) for f in bro_lint.passthrough_findings(doc, self.TABLE)}
        self.assertEqual(found, {("RC075", "warning", "propSfx"),
                                 ("RC075", "info", "loadVolumeSettings.openingDelay")})

    def test_untyped_nodes_are_skipped(self):
        self.assertEqual(bro_lint.passthrough_findings({"propSfx": 1}, self.TABLE), [])

    def test_shipped_table_loads(self):
        table = bro_lint.passthrough_table()
        if table:
            self.assertIn("dropped", table)
            self.assertIn("Truck", table["typeChains"].get("ChassisAlcesC400", ["Truck"]))


@unittest.skipUnless((GAME / bp.BRO_PAK).is_file() and (GAME / bp.OTHER_PAK).is_file() and SCHEMA.is_file(),
                     "needs the RoadCraft install and schema.json")
class RetailTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = bp.run(GAME, SCHEMA, DECOMP if DECOMP.is_dir() else None)
        cls.fields = cls.result["fields"]

    def test_pairs(self):
        self.assertGreaterEqual(self.result["retailTrucks"], 100)

    def test_soft_force_scale_passes(self):
        e = self.fields[".bro::TruckWheel.softForceScale"]
        self.assertEqual(e["status"], "passes")
        self.assertTrue(e["classPath"].endswith("prop_truck_wheel/softForceScale"))
        self.assertIs(e["engineReads"], True)

    def test_low_range_multiplier_passes_but_engine_ignores(self):
        e = self.fields[".ssl::TruckGearboxParams.lowRangeMultiplier"]
        self.assertEqual(e["status"], "passes")
        self.assertIs(e["engineReads"], False)

    def test_suspension_collection_lands_in_axle_collection(self):
        e = self.fields[".bro::TruckSettings.suspensionCollection"]
        self.assertIn("suspensionAxleCollection", e["classPath"] or "")

    @unittest.skipUnless(DECOMP.is_dir(), "needs the decompiled Bro.Compiled.dll")
    def test_code_cases(self):
        stale = [e["status"] for k, e in self.fields.items()
                 if k.startswith(".bro::") and k.endswith(".isCaterpillarWheel")]
        self.assertTrue(stale)
        self.assertEqual(set(stale), {"dropped"})
        self.assertEqual(self.fields[".bro::Truck.propSfx"]["status"], "dropped")
        writes = bp.CodeIndex.scan(DECOMP).evidence("StaticTruckAxisAction", "strenghtFactor")["writes"]
        self.assertTrue(writes[0]["to"].endswith("staticTruckAxisControls/[]/actionData/strengthFactor"))
        self.assertEqual(writes[0]["gate"], "if (staticTruckAxisAction.actionType != (object)null)")
        self.assertIn("* model.data.scale", self.fields[".bro::TruckWheel.radius"]["rule"])


if __name__ == "__main__":
    unittest.main()
