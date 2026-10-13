"""Effective physics values and donor comparison (roadcraft.physics_report).

Synthetic class/markup fixtures need no SDK: the context points at a folder without an installation, so
schema defaults come from the module's built-in copy.  SDK-gated tests read the retail EPEC TC305 and skip
with a reason when the game is not installed; share-gated tests read the KGS-25 fixture from the LAN share.
"""

import io
import json
import shutil
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from roadcraft import physics_report as pr
from roadcraft import schema as schema_mod
from roadcraft.tpl_reader import TplNodes

TRUCK = """properties = {
   geom = {
      nameTpl = "t"
   }
   prop_truck_rb = {
      suspensionSet = {
         front = {
            max = 0
            strength = 1
            damping = 0.85
         }
         rearDiffers = True
         rear = {
            max = 0.4
            strength = 0.001
            damping = 0.3
         }
      }
      engine = {
         params = {
            torque = 500000
            __type = "TruckEngineParams"
         }
         __type = "TruckEngine"
      }
      gearbox = {
         params = {
            gears = [
               {
                  angularVelocity = 1
                  gearRatio = 5
               }
            ]
            lowRangeMultiplier = 0.5
            __type = "TruckGearboxParams"
         }
      }
      trackControls = {
         steeringInputToInnerTrackTorqueMult = {
            spline = [ 0, 1, 0.5, 0, 1, -1 ]
            __type = "SplineCurve1d"
         }
         __type = "TruckTrackControls"
      }
      wheelSlotWithDescs = [
         {
            geomName = "w_L0"
            parentFrame = "BoneFrame_L_cdt"
            torqueType = "defaults"
            editableWheel = "drive"
         },
         {
            geomName = "w_L1"
            parentFrame = "BoneFrame_L_cdt"
            isRear = True
            editableWheel = "contact"
         },
         {
            geomName = "w_R0"
            parentFrame = "BoneFrame_R_cdt"
            isRightSided = True
            editableWheel = "drive"
         },
         {
            geomName = "w_R1"
            parentFrame = "BoneFrame_R_cdt"
            isRightSided = True
            isRear = True
            editableWheel = "contact"
         }
      ]
      wheelPool = {
         drive = {
            __value = "auto_wheel_t_drive"
         }
         contact = {
            __value = "auto_wheel_t_contact"
         }
      }
   }
   prop_truck_track = {
      tracks = [
         {
            section = {
               height = 0.07
               tpl = "t_track"
               __type = "TruckTrackSection"
            }
            %TRACKER%
            wheelIds = [ 0 ]
            fakeWheelIds = [ 1 ]
         },
         {
            section = {
               height = 0.07
            }
            wheelIds = [ 2 ]
            fakeWheelIds = [ 3 ]
         }
      ]
   }
}
__type = "truck_view"
"""
TRACKER = """parentTracker = {
               locator = "BoneFrame_L_cdt"
               __type = "Tracker"
            }"""
PREVIEW = """properties = {
   prop_truck_rb = {
      wheelSlotWithDescs = [ { geomName = "w_L0" } ]
   }
}
__type = "truck_customization_preview"
"""
DRIVE = """properties = {
   prop_truck_wheel = {
      mass = 120
      radius = 0.33
   }
   prop_truck_friction_updater = {
      frictionMaterialsList = {
         asphalt = {
            frictionValue = 2
            likeAsphalt = False
            __type = "FrictionMaterial"
         }
         grass = {
            terrainDeformationFactor = 2.5
            __type = "FrictionMaterial"
         }
      }
   }
}
__type = "t_wheel_base"
"""
WHEEL_BASE = """properties = {
   prop_truck_wheel = {
      softForceScale = 0.75
      sidewaysFrictionMultiplier = 0.1
   }
}
__type = "iactor"
"""
CONTACT = """properties = {
   prop_truck_wheel = {
      mass = %MASS%
      radius = 0.2
      softForceScale = %SOFT%
   }
   prop_truck_friction_updater = {
      frictionMaterialsList = {
         default = {
            frictionValue = %FRICTION%
            __type = "FrictionMaterial"
         }
         asphalt = {
            frictionValue = 0.8
            __type = "FrictionMaterial"
         }
         %MUDSAND%
      }
   }
}
__type = "truck_wheel_muted"
"""
MARKUP = """objectInfos = [
   {
      objectId = {
         name = "BoneChassis_cdt"
      }
      properties = [
         {
            massFromDensity = False
            mass = 8000
            angularDamping = 1.5
            __type = "tpl_markup_object_property_physics"
         }
      ]
   },
   {
      objectId = {
         name = "BoneFrame_L_cdt"
      }
      properties = [
         {
            massFromDensity = False
            mass = 2000
            __type = "tpl_markup_object_property_physics"
         }
      ]
      entities = [
         {
            name = "FrameL"
            target = "BoneChassis_cdt"
            motor = {
               tau = 0.5
               spring = 100
               __type = "tpl_markup_position_motor"
            }
            __type = "tpl_markup_constraint_hinge"
         }
      ]
   },
   {
      objectId = {
         name = "BoneFrame_R_cdt"
      }
      properties = [
         {
            mass = 2000
            __type = "tpl_markup_object_property_physics"
         }
      ]
      entities = [
         {
            target = "BoneChassis_cdt"
            __type = "tpl_markup_constraint_fixed"
         }
      ]
   }
]
"""


def make_tree(root: Path, *, contact_mass=450, soft=1, friction=2.0, mud_sand=False, tracker=True) -> Path:
    files = {
        "ssl/auto_t.cls": TRUCK.replace("%TRACKER%", TRACKER if tracker else ""),
        "ssl/auto_preview_t.cls": PREVIEW,
        "ssl/auto_wheel_t_drive.cls": DRIVE,
        "ssl/t_wheel_base.cls": WHEEL_BASE,
        "ssl/auto_wheel_t_contact.cls": CONTACT.replace("%MASS%", str(contact_mass)).replace("%SOFT%", str(soft))
        .replace("%FRICTION%", str(friction))
        .replace("%MUDSAND%", "mud_sand = {\n frictionValue = 0.5\n __type = \"FrictionMaterial\"\n }" if mud_sand else ""),
        "models/mods/t.tpl.asset/t.tpl_markup": MARKUP,
    }
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def entity(truck, eid):
    return next(e for e in truck["entities"] if e["id"] == eid)


class SyntheticReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.tree = make_tree(self.tmp / "mod")
        self.ctx = pr.Context(self.tmp)            # no installation here: built-in schema defaults, no retail
        self.report = pr.report(self.tree, ctx=self.ctx)
        self.truck = self.report["trucks"][0]

    def test_finds_the_truck_and_skips_previews(self):
        self.assertEqual([t["class"] for t in self.report["trucks"]], ["ssl/auto_t.cls"])
        self.assertEqual(self.truck["kind"], "tracked")
        self.assertEqual(self.report["schema"], "built-in copy")

    def test_body_sources_and_engine_defaults(self):
        hull = entity(self.truck, "BoneChassis_cdt")
        self.assertEqual(hull["role"], "hull")
        self.assertEqual((hull["fields"]["mass"]["value"], hull["fields"]["mass"]["source"]), (8000, "explicit"))
        self.assertIn("objectInfos[0].properties[0].mass", hull["fields"]["mass"]["evidence"])
        self.assertEqual((hull["fields"]["restitution"]["value"], hull["fields"]["restitution"]["source"]),
                         (0.4, "engine-default"))
        self.assertIn("FUN_1430811e0", hull["fields"]["restitution"]["evidence"])
        self.assertEqual(hull["fields"]["fixed"]["source"], "schema-default")

    def test_density_body_mass_is_not_invented(self):
        frame = entity(self.truck, "BoneFrame_R_cdt")
        self.assertIs(frame["fields"]["massFromDensity"]["value"], True)
        self.assertIsNone(frame["fields"]["effectiveMass"]["value"])
        derived = entity(self.truck, "derived")["fields"]
        self.assertEqual(derived["bodyMass"]["value"], 10000)
        self.assertIn("lower bound", derived["bodyMass"]["note"])

    def test_joint_motor_defaults_and_ignored_keys(self):
        frame = entity(self.truck, "BoneFrame_L_cdt")["fields"]
        self.assertEqual(entity(self.truck, "BoneFrame_L_cdt")["role"], "track frame")
        self.assertEqual(frame["joint.type"]["value"], "hinge")
        self.assertEqual((frame["joint.motor.tau"]["value"], frame["joint.motor.tau"]["source"]), (0.5, "explicit"))
        self.assertEqual((frame["joint.motor.damping"]["value"], frame["joint.motor.damping"]["source"]),
                         (0.95, "schema-default"))
        self.assertEqual(frame["joint.motor.ignoredKeys"]["value"], ["spring"])

    def test_inherited_wheel_fields_and_friction_table(self):
        drive = entity(self.truck, "class:drive")
        f = drive["fields"]
        self.assertEqual(drive["role"], "idler/drive wheel")
        self.assertEqual((f["softForceScale"]["value"], f["softForceScale"]["source"]), (0.75, "inherited"))
        self.assertIn("t_wheel_base.cls", f["softForceScale"]["evidence"])
        self.assertEqual((f["friction.default.frictionValue"]["value"], f["friction.default.frictionValue"]["source"]),
                         (2, "engine-default"))
        self.assertIn("prop_truck_friction_updater.ssc", f["friction.default.frictionValue"]["evidence"])
        self.assertEqual((f["friction.asphalt.frictionValue"]["value"], f["friction.asphalt.frictionValue"]["source"]),
                         (2, "explicit"))
        self.assertEqual((f["friction.grass.frictionValue"]["value"], f["friction.grass.frictionValue"]["source"]),
                         (2, "schema-default"))
        self.assertEqual(f["friction.grass.terrainDeformationFactor"]["value"], 2.5)
        self.assertEqual(f["friction.mud_sand.frictionValue"]["source"], "absent")
        self.assertIn("previous friction", f["friction.mud_sand.frictionValue"]["note"])

    def test_slots_axles_and_derived_ratios(self):
        rear = entity(self.truck, "slot[1]")
        self.assertEqual(rear["role"], "contact wheel")
        f = rear["fields"]
        self.assertEqual((f["slot.axle"]["value"], f["slot.axle"]["source"]), ("suspensionSet.rear", "engine-default"))
        self.assertAlmostEqual(f["slot.physicalRadius"]["value"], 0.27)
        self.assertAlmostEqual(f["slot.massRatio"]["value"], 450 / 2000)
        self.assertIsNone(entity(self.truck, "slot[3]")["fields"]["slot.massRatio"]["value"])  # density frame
        axle = entity(self.truck, "suspensionSet.rear")
        self.assertEqual(axle["role"], "axle: contact wheel")
        self.assertEqual(axle["fields"]["strength"]["value"], 0.001)
        self.assertEqual(axle["fields"]["min"]["source"], "schema-default")
        self.assertAlmostEqual(axle["fields"]["travelRange"]["value"], 0.4)
        self.assertEqual(entity(self.truck, "suspensionSet.front")["role"], "axle: idler/drive wheel")
        self.assertNotIn("sag", json.dumps(self.truck).lower())

    def test_tracks_and_truck_level(self):
        t0, t1 = entity(self.truck, "track[0]")["fields"], entity(self.truck, "track[1]")["fields"]
        self.assertEqual(t0["section.height"]["value"], 0.07)
        self.assertEqual(t0["parentTracker"]["value"], "BoneFrame_L_cdt")
        self.assertEqual((t1["parentTracker"]["value"], t1["parentTracker"]["source"]), (None, "engine-default"))
        self.assertEqual((t0["trackTensionDefault"]["value"], t0["trackTensionDefault"]["source"]),
                         (0.04, "schema-default"))
        self.assertEqual(t0["physicsWheels"]["value"], 2)
        truck = entity(self.truck, "truck")["fields"]
        self.assertEqual(truck["trackControls.steeringInputToInnerTrackTorqueMult"]["value"], [0, 1, 0.5, 0, 1, -1])
        self.assertEqual(truck["trackControls.linearVelocityToInnerTrackTorqueMult"]["source"], "engine-default")
        self.assertIn("F1", truck["gearbox.lowRangeMultiplier"]["note"])
        self.assertEqual(truck["physics.stepHz"]["value"], 60)

    def test_every_value_has_a_known_source_and_evidence(self):
        for ent in self.truck["entities"]:
            for name, value in ent["fields"].items():
                self.assertIn(value["source"], pr.SOURCES, name)
                self.assertTrue(value["evidence"], name)

    def test_pak_matches_folder_and_is_deterministic(self):
        pak = self.tmp / "t.pak"
        with zipfile.ZipFile(pak, "w") as archive:
            for path in sorted(self.tree.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(self.tree).as_posix())
        a = pr.report(pak, ctx=pr.Context(self.tmp))
        b = pr.report(pak, ctx=pr.Context(self.tmp))
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
        self.assertEqual(len(a["sha256"]), 64)
        values = lambda rep: {(e["id"], k): v["value"] for e in rep["trucks"][0]["entities"] for k, v in e["fields"].items()}
        self.assertEqual(values(a), values(self.report))

    def test_bone_origin_height_and_track_width(self):
        names = ["BoneChassis_cdt", "BoneFrame_L_cdt", "BoneFrame_R_cdt", "w_L0", "w_L1", "w_R0", "w_R1"]
        pos = [(0, 1.0, 0), (1.2, 0.5, 0), (-1.2, 0.5, 0), (1.2, 0.3, 2), (1.2, 0.25, -2), (-1.2, 0.3, 2),
               (-1.2, 0.25, -2)]
        nodes = TplNodes(names=names, index={n: i for i, n in enumerate(names)},
                         matrices=[(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, x, y, z, 1) for x, y, z in pos])
        bodies = [e for e in self.truck["entities"] if e["kind"] == "body"]
        slots = [e for e in self.truck["entities"] if e["kind"] == "wheel"]
        tracks = [e for e in self.truck["entities"] if e["kind"] == "track"]
        f = pr._derived(bodies, slots, tracks, nodes, "t.tpl")["fields"]
        self.assertAlmostEqual(f["trackWidth"]["value"], 2.4)
        # the right frame is a density body (mass unknown) and is left out; ground = drive wheel bottom
        masses = [(8000, 1.0), (2000, 0.5), (120, 0.3), (450, 0.25), (120, 0.3), (450, 0.25)]
        y = sum(m * h for m, h in masses) / sum(m for m, _ in masses)
        self.assertAlmostEqual(f["boneOriginHeight"]["value"], y - (0.3 - (0.33 + 0.07)), places=5)  # 6 sig. digits
        self.assertIn("NOT the centre of mass", f["boneOriginHeight"]["evidence"])


class SyntheticCompareTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.mod = make_tree(self.tmp / "mod")
        self.donor = make_tree(self.tmp / "donor", contact_mass=1700, soft=0.75, friction=1.0, mud_sand=True,
                               tracker=False)

    def rows(self, result):
        return {(r["role"], r["field"]): r for r in result["pairs"][0]["rows"]}

    def test_donor_tree_without_retail(self):
        result = pr.compare(self.mod, str(self.donor), ctx=pr.Context(self.tmp))
        rows = self.rows(result)
        mass = rows[("contact wheel", "mass")]
        self.assertEqual((mass["mod"]["values"], mass["donor"]["values"]), ([450], [1700]))
        self.assertIn("differs", mass["flags"])
        self.assertIsNone(mass["retail"])
        self.assertIn("differs", rows[("contact wheel", "softForceScale")]["flags"])
        self.assertIn("absent-in-mod", rows[("contact wheel", "friction.mud_sand.frictionValue")]["flags"])
        self.assertIn("differs", rows[("track", "parentTracker")]["flags"])
        self.assertEqual(rows[("contact wheel", "friction.default.frictionValue")]["mod"]["values"], [2])
        text = pr.format_compare(result)
        self.assertIn("contact wheel mass", text)
        self.assertIn("key fields", text)

    def test_retail_distribution_flags(self):
        mod = pr.report(self.mod, ctx=pr.Context(self.tmp))["trucks"][0]
        donor = pr.report(self.donor, ctx=pr.Context(self.tmp))["trucks"][0]
        dist = {"kind": "tracked", "trucks": ["a", "b"],
                "values": {("contact wheel", "mass"): [1000, 1700], ("contact wheel", "softForceScale"): [0.5, 0.85],
                           ("contact wheel", "friction.mud_sand.frictionValue"): [0.5, 1.0],
                           ("track", "parentTracker"): []},
                "withRole": {"contact wheel": 2, "track": 2},
                "withValue": {("contact wheel", "mass"): 2, ("contact wheel", "softForceScale"): 2,
                              ("contact wheel", "friction.mud_sand.frictionValue"): 2}}
        rows = {(r["role"], r["field"]): r for r in pr.compare_trucks(mod, donor, dist, None)}
        self.assertIn("outside-retail", rows[("contact wheel", "mass")]["flags"])
        self.assertIn("outside-retail", rows[("contact wheel", "softForceScale")]["flags"])
        self.assertIn("missing", rows[("contact wheel", "friction.mud_sand.frictionValue")]["flags"])
        self.assertEqual(rows[("contact wheel", "mass")]["retail"]["min"], 1000)
        only = pr.compare_trucks(mod, donor, dist, ["softForce"])
        self.assertEqual({r["field"] for r in only}, {"softForceScale", "softForceScaleStatic"})

    def test_main_exit_codes(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = pr.main(["report", str(self.mod), "--json", "--game-root", str(self.tmp)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["trucks"][0]["kind"], "tracked")
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            self.assertEqual(pr.main(["report", str(self.tmp / "nope"), "--game-root", str(self.tmp)]), 2)
            self.assertEqual(pr.main(["compare", str(self.mod), "--donor", "EPEC TC305",
                                      "--game-root", str(self.tmp)]), 2)      # no retail installation
        out = io.StringIO()
        with redirect_stdout(out):
            code = pr.main(["compare", str(self.mod), "--donor", str(self.donor), "--fields", "mass",
                            "--game-root", str(self.tmp)])
        self.assertEqual(code, 0)
        self.assertIn("contact wheel mass", out.getvalue())


GAME_ROOT = schema_mod.default_game_root()
SDK = schema_mod.sdk_present(GAME_ROOT) and (GAME_ROOT / "root/paks/client").is_dir()
KGS_FIXTURE = Path("//192.168.0.129/Downloads/roadcraft_fixtures/mods/kgs25/installed_pak")


@unittest.skipUnless(SDK, f"RoadCraft SDK/retail data not installed at {GAME_ROOT}")
class RetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = pr.Context(GAME_ROOT)
        cls.name = pr.resolve_retail(cls.ctx, "EPEC TC305")
        cls.truck = pr.retail_report(cls.ctx, cls.name)

    def test_resolves_names(self):
        self.assertEqual(self.name, "epec_tc305_heavy_crane_new")
        self.assertEqual(pr.resolve_retail(self.ctx, "Greenway HT500"), "greenway_ht500_dozer_new")

    def test_tc305_values(self):
        track = entity(self.truck, "track[0]")["fields"]
        self.assertEqual(track["section.height"]["value"], 0.2)
        self.assertEqual(track["trackTensionDefault"]["value"], 0.045)
        self.assertEqual(track["parentTracker"]["source"], "engine-default")
        contact = [e for e in self.truck["entities"] if e["kind"] == "wheelClass" and e["role"] == "contact wheel"]
        self.assertTrue(contact)
        self.assertEqual({e["fields"]["mass"]["value"] for e in contact}, {1700})
        self.assertEqual({e["fields"]["softForceScale"]["value"] for e in contact}, {0.75})
        self.assertEqual(self.ctx.schema() is not None, True)

    @unittest.skipUnless(KGS_FIXTURE.is_dir(), f"KGS-25 fixture share not reachable: {KGS_FIXTURE}")
    def test_kgs_fixture_reproduces_the_desktop_diff(self):
        result = pr.compare(KGS_FIXTURE, "EPEC TC305", ctx=self.ctx,
                            fields=["softForceScale", "mass", "terrainDeformationFactor", "section.height",
                                    "parentTracker", "trackTensionDefault", "frictionValue"])
        rows = {(r["role"], r["field"]): r for r in result["pairs"][0]["rows"]}
        self.assertEqual(rows[("contact wheel", "softForceScale")]["mod"]["values"], [1])
        self.assertIn("outside-retail", rows[("contact wheel", "softForceScale")]["flags"])
        self.assertIn("outside-retail", rows[("idler/drive wheel", "mass")]["flags"])
        self.assertEqual(rows[("track", "section.height")]["donor"]["values"], [0.2])
        self.assertEqual(rows[("contact wheel", "friction.default.frictionValue")]["mod"]["values"], [2])
        self.assertIn("differs", rows[("track", "parentTracker")]["flags"])
        self.assertEqual(rows[("track", "trackTensionDefault")]["donor"]["values"], [0.045])


if __name__ == "__main__":
    unittest.main()
