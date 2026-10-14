"""Physics bench (roadcraft.physics_bench): variant patchers, bench folder and run analysis.

Shaped on the KGS25 bench (2026-10-02); the patchers were checked byte for byte against the original
bench script on all ten KGS variants, and the analysis against its five recorded summaries.
The editor launch itself is not exercised here.
"""

import json
import math
import tempfile
import unittest
from pathlib import Path

from roadcraft import physics_bench as pb

CLASS = ("properties = {\r\n   prop_truck_rb = {\r\n      suspensionAxleCollection = [\r\n"
         "         {\r\n            max = 0\r\n            strength = 0.7\r\n         },\r\n"
         "         {\r\n            max = 0.22\r\n            height = 0.05\r\n            strength = 0.0013\r\n"
         "         }\r\n      ]\r\n      suspensionCollectionMap = {\r\n         Fixed = {\r\n            __value = 0\r\n"
         "         }\r\n         Contact = {\r\n            __value = 1\r\n         }\r\n      }\r\n"
         "      wheelSlots = [\r\n"
         "         {\r\n            geomName = \"L_contact0\"\r\n            scale = 0.2\r\n"
         "            suspensionCollectionAxleIndex = 1\r\n         },\r\n"
         "         {\r\n            geomName = \"L_bare\"\r\n         },\r\n"
         "         {\r\n            geomName = \"L_contact1\"\r\n            suspensionCollectionAxleIndex = 1\r\n         }\r\n"
         "      ]\r\n      tracks = [\r\n         {\r\n            wheelIds = [ 0, 1 ]\r\n"
         "            fakeWheelIds = [ 2, 3 ]\r\n         },\r\n         {\r\n            wheelIds = [\r\n"
         "               4,\r\n               5\r\n            ]\r\n            fakeWheelIds = [ 6 ]\r\n         }\r\n"
         "      ]\r\n   }\r\n}\r\n")

WHEEL = ("properties = {\r\n   prop_truck_wheel = {\r\n      radius = 0.2\r\n      mass = 450\r\n"
         "      decals = {\r\n         mass = 7\r\n         __type = \"TruckEcsMeshDecals\"\r\n      }\r\n   }\r\n}\r\n")

MARKUP = ("objectInfos = [\r\n   {\r\n      objectId = {\r\n         name = \"BoneChassis_cdt\"\r\n      }\r\n"
          "      properties = [\r\n         {\r\n            massFromDensity = False\r\n            mass = 19900\r\n"
          "            __type = \"tpl_markup_object_property_physics\"\r\n         }\r\n      ]\r\n   },\r\n"
          "   {\r\n      objectId = {\r\n         name = \"BoneTrackSusp_L_cdt\"\r\n      }\r\n      properties = [\r\n"
          "         {\r\n            mass = 2500\r\n            hkCenterOfMassOffset = [ 0, 0, 0 ]\r\n"
          "            __type = \"tpl_markup_object_property_physics\"\r\n         }\r\n      ]\r\n   }\r\n]\r\n")

SCENE = "objects = {\r\n   crane = {\r\n      transform = {\r\n         position = [ 0, 60.12, -18 ]\r\n      }\r\n   }\r\n}\r\n"


class PatcherTests(unittest.TestCase):
    def test_axles_by_collection_name_keep_the_other_axle_and_line_ends(self):
        out = pb.patch_axles(CLASS, {"Contact": {"min": 0, "max": 0.4, "height": 0, "strength": 0.001, "damping": 0.3}})
        self.assertIn("         {\r\n            min = 0\r\n            max = 0.4\r\n            height = 0\r\n"
                      "            strength = 0.001\r\n            damping = 0.3\r\n         }\r\n      ]", out)
        self.assertIn("            max = 0\r\n            strength = 0.7\r\n         },", out)
        self.assertNotIn("0.0013", out)
        self.assertEqual(pb.axle_names(CLASS), {"Fixed": 0, "Contact": 1})
        with self.assertRaises(pb.BenchError):
            pb.patch_axles(CLASS, {"Sprung": {"max": 0.2}})
        with self.assertRaises(pb.BenchError):
            pb.patch_axles(CLASS, {"Fixed": {"stiffness": 1}})

    def test_track_lists_inline_and_one_per_line(self):
        out = pb.patch_track_lists(CLASS, 0, [0, 1, 2], [3])
        self.assertIn("wheelIds = [ 0, 1, 2 ]\r\n            fakeWheelIds = [ 3 ]", out)
        out = pb.patch_track_lists(CLASS, 1, [4, 5, 6], [])
        self.assertIn("wheelIds = [\r\n               4,\r\n               5,\r\n               6\r\n            ]", out)
        self.assertIn("fakeWheelIds = [ ]", out)
        with self.assertRaises(pb.BenchError):
            pb.patch_track_lists(CLASS, 2, [1])

    def test_slot_axle_does_not_spill_into_the_next_slot(self):
        out = pb.patch_slot_axle(CLASS, "L_contact0", 0)
        self.assertIn("geomName = \"L_contact0\"\r\n            scale = 0.2\r\n            suspensionCollectionAxleIndex = 0", out)
        self.assertIn("geomName = \"L_contact1\"\r\n            suspensionCollectionAxleIndex = 1", out)
        with self.assertRaises(pb.BenchError):
            pb.patch_slot_axle(CLASS, "L_bare", 0)

    def test_wheel_fields_top_level_only(self):
        out = pb.patch_wheel_fields(WHEEL, {"mass": 1700, "isSoftContactEnabled": False})
        self.assertIn("      mass = 1700\r\n      isSoftContactEnabled = False\r\n      decals = {\r\n         mass = 7", out)
        flat = pb.patch_wheel_fields("prop_truck_wheel = {\n   mass = 1\n}\n", {"softForceScale": 0.5})
        self.assertEqual(flat, "prop_truck_wheel = {\n   mass = 1\n   softForceScale = 0.5\n}\n")

    def test_markup_mass_and_centre_of_mass(self):
        out = pb.patch_markup_body(MARKUP, "BoneChassis_cdt", mass=9900, com=[0, -1, 0])
        self.assertIn("mass = 9900\r\n            __type = \"tpl_markup_object_property_physics\"\r\n"
                      "            hkCenterOfMassOffset = [ 0, -1, 0 ]\r\n", out)
        out = pb.patch_markup_body(out, "BoneTrackSusp_L_cdt", mass=7500, com=[0, -0.2, 0])
        self.assertIn("mass = 7500\r\n            hkCenterOfMassOffset = [ 0, -0.2, 0 ]", out)
        self.assertEqual(out.count("hkCenterOfMassOffset"), 2)
        with self.assertRaises(pb.BenchError):
            pb.patch_markup_body(MARKUP, "BoneBoom_cdt", mass=1)

    def test_spawn_position(self):
        self.assertIn("position = [ 45, 42.65, -18.5 ]", pb.place_vehicle(SCENE, "crane", [45, 42.65, -18.5]))
        with self.assertRaises(pb.BenchError):
            pb.place_vehicle(SCENE, "truck", [0, 0, 0])


class BenchFolderTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.src = self.root / "mod" / "project"
        mods = self.src / "mods_source"
        for rel, text in (("trucks/crane.cls", CLASS), ("trucks/wheel_contact.cls", WHEEL),
                          ("models/crane.tpl_markup", MARKUP), ("scenes/pad.scn", SCENE)):
            (mods / rel).parent.mkdir(parents=True, exist_ok=True)
            (mods / rel).write_bytes(text.encode("utf-8"))
        posix = self.src.resolve().as_posix()
        (self.src / ".project").write_bytes(f"documents-dir: {posix}\r\nmods-dir: $(documents-dir)/mods_source\r\n".encode())
        (self.src / "config").mkdir()
        (self.src / "config" / "editor.cfg").write_bytes(
            f"  ModsSourceLocal: {posix}/mods_source\r\n  Win: {self.src.resolve()}\\mods_source\r\n".encode())
        for d in ("data", "profiles"):
            (self.root / d).mkdir()
            (self.root / d / "x.txt").write_text(d)
        self.files = {"class": "trucks/crane.cls", "markup": "models/crane.tpl_markup",
                      "wheelClasses": {"contact": "trucks/wheel_contact.cls"}}

    def init(self):
        return pb.init_bench(self.src, self.root / "data", self.root / "profiles", self.root / "bench",
                             scene="scenes/pad.scn", vehicle="crane", editor="IntegrationStudio.exe", files=self.files,
                             sdk_editor_directory="SDK/tools/bin/ModEditor")

    def test_init_copies_and_rewrites_project_paths(self):
        report = self.init()
        self.assertEqual(report["leftoverReferences"], [])
        bench = (self.root / "bench").resolve()
        project = (bench / "project" / ".project").read_bytes().decode()
        self.assertIn(f"documents-dir: {(bench / 'project').as_posix()}\r\n", project)
        cfg = (bench / "project" / "config" / "editor.cfg").read_text()
        self.assertIn(str(bench / "project") + "\\mods_source", cfg)
        scenario = (bench / "play.scenario").read_text()
        self.assertIn((bench / "project" / "mods_source" / "scenes" / "pad.scn").as_posix(), scenario)
        self.assertIn("echo BENCH_GAME_MODE_READY", scenario)
        config = pb.load_config(report["config"])
        self.assertEqual((config["vehicle"], config["sdkEditorDirectory"]), ("crane", "SDK/tools/bin/ModEditor"))
        with self.assertRaises(pb.BenchError):         # a bench that cannot reach the probes refuses to run
            pb.run(dict(config, sdkEditorDirectory=""), "c03", {})
        with self.assertRaises(pb.BenchError):
            self.init()

    def test_init_refuses_missing_resources(self):
        self.files["markup"] = "models/missing.tpl_markup"
        with self.assertRaises(pb.BenchError):
            self.init()

    def test_variant_applies_from_pristine_and_empty_variant_restores(self):
        config = pb.load_config(self.init()["config"])
        mods = Path(config["project"]) / "mods_source"
        variant = {"axles": {"Contact": {"min": 0, "max": 0.4}}, "tracks": [{"track": 0, "wheelIds": [0, 1, 2]}],
                   "slotAxles": {"L_contact0": 0}, "wheels": {"contact": {"mass": 1700}},
                   "bodies": {"BoneChassis_cdt": {"mass": 9900}}, "spawn": [1, 2, 3]}
        written = pb.apply_variant(config, variant)
        self.assertEqual(len(written), 4)
        pb.apply_variant(config, variant)          # applied to pristine, not on top of itself
        cls = (mods / "trucks/crane.cls").read_text()
        self.assertEqual(cls.count("max = 0.4"), 1)
        self.assertIn("wheelIds = [ 0, 1, 2 ]", cls)
        self.assertIn("mass = 1700", (mods / "trucks/wheel_contact.cls").read_text())
        self.assertIn("position = [ 1, 2, 3 ]", (mods / "scenes/pad.scn").read_text())
        pb.apply_variant(config, {})
        self.assertEqual((mods / "trucks/crane.cls").read_bytes(), CLASS.encode())
        self.assertEqual((mods / "scenes/pad.scn").read_bytes(), SCENE.encode())
        with self.assertRaises(pb.BenchError):
            pb.apply_variant(config, {"hullCom": [0, -1, 0]})
        with self.assertRaises(pb.BenchError):
            pb.apply_variant(config, {"wheels": {"idler": {"mass": 1}}})


def sample(t, roll_deg=0.0, y=60.0, yaw_deg=0.0, x=0.0, z=0.0, speed=0.0, ground=(1, 1, 1, 1)):
    """One series_probe reply: hull rolled about its forward axis, a level track frame."""
    r, w = math.radians(roll_deg), math.radians(yaw_deg)
    fwd = (math.sin(w), 0.0, math.cos(w))
    left = (math.cos(w), 0.0, -math.sin(w))
    up = tuple(math.cos(r) * u - math.sin(r) * l for u, l in zip((0.0, 1.0, 0.0), left))
    v = lambda vec: " ".join(f"{c:.5f}" for c in vec)  # noqa: E731
    lines = [f"F {int(t * 60)} {speed:.3f} 0 0",
             f"B BoneChassis_cdt {x:.4f} {y:.4f} {z:.4f} {v(up)} {v(fwd)}",
             f"B BoneTrackSusp_L_cdt {x:.4f} {y - 0.5:.4f} {z:.4f} 0 1 0 {v(fwd)}"]
    lines += [f"W 0.1000 0 0 0 {g}" for g in ground]
    return json.dumps({"t": t, "r": "\n".join(lines)})


class SeriesParseTests(unittest.TestCase):
    def test_engine_centre_of_mass_and_wheel_spin_lines(self):
        reply = "\n".join(["F 512 0.3268 0.350 0.000", "G 1 872.4 0 1 0",
                           "B BoneChassis_cdt 5.9 42.5 3.0 0 1 0 0 0 1",
                           "C BoneChassis_cdt 1200.000 0.00000 0.15000 0.00000 5.90 42.65 3.00",
                           "W 0.0000 6.2547 42.5508 3.1846 1 -0.010 -0.0010 0.0735 0.0000 1",
                           "W 0.0000 6.2547 42.6374 2.8640 0"])
        path = Path(tempfile.mkdtemp()) / "series.jsonl"
        path.write_text(json.dumps({"t": 1.5, "r": reply}) + "\n")
        s = pb.parse_series(path)[0]
        self.assertEqual(s["engine"], {"gear": 1, "rpm": 872.4, "handbrake": False, "running": True, "brakePull": False})
        body = s["bodies"]["BoneChassis_cdt"]
        self.assertEqual((body["mass"], body["comLocal"], body["pos"]), (1200.0, [0.0, 0.15, 0.0], [5.9, 42.5, 3.0]))
        self.assertEqual((s["wheels"][0]["spin"], s["wheels"][0]["physicalRadius"], s["wheels"][0]["onTerrain"]),
                         (-0.01, 0.0735, True))
        self.assertNotIn("spin", s["wheels"][1])          # a reply from the older probe


class AnalysisTests(unittest.TestCase):
    def series(self, folder):
        rows = [sample(t / 10) for t in range(0, 100)]                                   # rest, level
        rows += [sample(10 + t / 10, z=0.5 * t / 10, speed=1.5) for t in range(0, 40)]   # forward
        rows += [sample(14 + t / 10, z=2.0) for t in range(0, 80)]                       # stop
        rows += [sample(22 + t / 10, roll_deg=3.0 if t == 20 else 0.0, y=59.81 if t == 20 else 60.0,
                        yaw_deg=-10 * t / 40, z=2.0, speed=1.0, ground=(1, 1, 0, 0) if t == 20 else (1, 1, 1, 1))
                 for t in range(0, 40)]                                                  # pivot+
        rows += [sample(26 + t / 10, yaw_deg=-10, z=2.0) for t in range(0, 20)]          # settle+
        (folder / "series.jsonl").write_text("\n".join(rows) + "\n{\"t\": 1, \"r\": \"\"}\n")

    def test_phases_motion_and_compare(self):
        folder = Path(tempfile.mkdtemp()) / "c03_normal_161400"
        folder.mkdir()
        self.series(folder)
        (folder / "variant.json").write_text(json.dumps({"name": "c03", "schedule": "normal"}))
        (folder / "inputs.json").write_text(json.dumps([{"rc": 0}, {"rc": 0}, {"rc": 1}]))
        summary = pb.analyse(folder)
        self.assertEqual((summary["hull"], summary["frames"]), ("BoneChassis_cdt", ["BoneTrackSusp_L_cdt"]))
        rest, pivot = summary["phases"]["rest"], summary["phases"]["pivot+"]
        self.assertEqual((rest["rollMaxAbs"], rest["maxAirborne"], rest["heightRangeMm"]), (0.0, 0, 0.0))
        self.assertAlmostEqual(pivot["rollMaxAbs"], 3.0, places=1)
        self.assertAlmostEqual(pivot["twistMax"], 3.0, places=1)
        self.assertEqual((pivot["maxAirborne"], pivot["heightRangeMm"]), (2, 190.0))
        self.assertEqual(summary["motion"]["forward"]["moved"], 2.0)
        self.assertAlmostEqual(summary["motion"]["pivot+"]["yaw"], -10.0, places=0)
        self.assertEqual(summary["inputsApplied"], "2/3")
        self.assertTrue((folder / "summary.json").exists())
        table = pb.compare([folder, folder.parent / "missing"])
        self.assertIn("== c03_normal_161400", table)
        self.assertIn("missing: no summary.json", table)
        with self.assertRaises(pb.BenchError):
            pb.summarise(pb.parse_series(folder / "series.jsonl"), hull="BoneBoom_cdt")


if __name__ == "__main__":
    unittest.main()


MARKUP_JOINTS = """objectInfos = [
   {
      objectId = {
         name = "BoneTower_cdt"
      }
      entities = [
         {
            name = "slew"
            target = "BoneFront_cdt"
            limited = True
            angleStart = -1.5
            angleEnd = 1.5
            motor = {
               tau = 0.5
               maxForce = 2000000
               __type = "tpl_markup_position_motor"
            }
            __type = "tpl_markup_constraint_hinge"
         }
      ]
   },
   {
      objectId = {
         name = "BoneHook_cdt"
      }
      entities = [
         {
            name = "hook"
            target = "BoneTele3_cdt"
            __type = "tpl_markup_constraint_ball_and_socket"
         }
      ]
   }
]
"""

CLASS_RB = """properties = {
   prop_truck_rb = {
      maxSteerSpeed = 0.02
      engine = {
         params = {
            torque = 420000
         }
      }
      controllableSteeringConstraints = [
         {
            constraintName = "steering"
            angularSpeed = 30
            minAngle = 30
         }
      ]
   }
}
"""


class JointPatcherTests(unittest.TestCase):
    """Kanga 25 bench (2026-10-10): joint motors/limits, truck fields and steering speed as variant keys."""

    def test_constraint_limits_and_motor(self):
        out = pb.patch_markup_constraint(MARKUP_JOINTS, "slew", {"angleStart": 0, "angleEnd": 0,
                                                                  "motor": {"tau": 0.4, "damping": 1.0}})
        self.assertIn("angleStart = 0\n", out)
        self.assertIn("angleEnd = 0\n", out)
        self.assertIn("tau = 0.4", out)
        self.assertIn("damping = 1.0", out)          # added inside the motor block
        self.assertIn("maxForce = 2000000", out)     # untouched
        motor = out[out.index("motor = {"):out.index("__type = \"tpl_markup_position_motor\"")]
        self.assertIn("damping", motor)

    def test_constraint_added_scalar(self):
        out = pb.patch_markup_constraint(MARKUP_JOINTS, "hook", {"massFactor": 0})
        hook = out[out.index('name = "hook"') - 40:]
        self.assertIn("massFactor = 0", hook)
        with self.assertRaises(pb.BenchError):
            pb.patch_markup_constraint(MARKUP_JOINTS, "hook", {"motor": {"tau": 1}})
        with self.assertRaises(pb.BenchError):
            pb.patch_markup_constraint(MARKUP_JOINTS, "missing", {"limited": True})

    def test_truck_fields_and_steering(self):
        out = pb.patch_block_fields(CLASS_RB, "prop_truck_rb", {"maxSteerSpeed": 0.01, "pedalsResponsiveness": 0.2})
        self.assertIn("maxSteerSpeed = 0.01", out)
        self.assertIn("pedalsResponsiveness = 0.2", out)
        self.assertIn("torque = 420000", out)
        out = pb.patch_steering(out, "steering", {"angularSpeed": 18})
        self.assertIn("angularSpeed = 18", out)
        self.assertIn("minAngle = 30", out)

    def test_variant_keys_accepted(self):
        for key in ("constraints", "truck", "steering"):
            self.assertIn(key, pb.VARIANT_KEYS)

class FoldedBenchPathTests(unittest.TestCase):
    def test_sdk_folded_yaml_project_paths_are_relocated(self):
        old = Path("C:/Games/Roadcraft Development Package/mod/project")
        new = Path("C:/Games/isolated-bench/project")
        for original, replacement in ((old.as_posix(), new.as_posix()), (str(old), str(new))):
            folded = original.replace("Development Package", "Development\r\n  Package")
            data = ("documents-dir: " + folded + "\r\nreference: C:/Games/root/.project\r\n").encode()
            result = pb._rewrite_bytes(data, old, new).decode()
            self.assertEqual(result, "documents-dir: " + replacement + "\r\nreference: C:/Games/root/.project\r\n")


class ReverseScheduleTests(unittest.TestCase):
    def test_native_debug_reverse_uses_signed_negative_pedal(self):
        for name in ('normal', 'harsh', 'straight', 'straightfull', 'idle'):
            reverse = [controls for _, controls in pb.SCHEDULES[name]['steps'] if controls[3] == 'REVERSE']
            self.assertTrue(reverse, name)
            for pedal, steer, handbrake, gear in reverse:
                self.assertLess(pedal, 0, name)
                self.assertEqual(handbrake, 'Off', name)
