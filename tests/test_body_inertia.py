"""Body inertia from collision shapes: the .tpl per-mesh bounds table (tpl_reader.find_bounds), the physics report's
inertia fields (physics_report.body_inertia), the retail spread (physics_report.inertia_distribution) and the
RC080 validator rule (validate.judge_inertia / rule_body_inertia).

Synthetic fixtures need no SDK.  The retail calibration test needs the installed game; the Mammoth RC68/RC69
acceptance needs the LAN share.  Both skip with a reason otherwise.
"""

import shutil
import struct
import tempfile
import unittest
from pathlib import Path

from roadcraft import physics_report as pr
from roadcraft import schema as schema_mod
from roadcraft import tpl_reader
from roadcraft import validate as v
from roadcraft.tpl_reader import MeshBounds, TplNodes

IDENTITY_AXES = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)


def _record(size, center=(0.0, 0.0, 0.0), axes=IDENTITY_AXES) -> bytes:
    """One 89-byte bounds record: a box of ``size`` centred on ``center`` in its node's frame."""
    lo = tuple(c - s / 2 for c, s in zip(center, size))
    hi = tuple(c + s / 2 for c, s in zip(center, size))
    return struct.pack("<I", 4) + b"\x0c" + struct.pack("<21f", *lo, *hi, *lo, *axes, *size)


def make_tpl(names, positions, parents, boxes) -> bytes:
    """A compiled-model-shaped blob: parent array, node table, then the bounds bitset and records.
    ``boxes`` maps node index -> box size (centred on the node)."""
    count = len(names)
    data = b"\x00" * 8 + struct.pack(f"<{count}h", *parents) + b"\x00" * 8
    data += struct.pack("<I", count) + b"\x00"
    for name in names:
        data += struct.pack("<I", len(name)) + name.encode()
    data += struct.pack("<I", count) + struct.pack(f"<{count}H", *range(count)) + struct.pack("<I", count)
    for x, y, z in positions:
        data += struct.pack("<16f", 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, x, y, z, 1)
    mask = sum(1 << i for i in boxes)
    data += b"\x00" * 8 + mask.to_bytes((count + 7) // 8, "little")
    for i in sorted(boxes):
        data += _record(boxes[i])
    return data + b"\x00" * 16


class BoundsTableTests(unittest.TestCase):
    def test_bitset_maps_records_to_nodes_in_order(self):
        names = ["root", "a", "cdt_a", "b", "cdt_b"]
        data = make_tpl(names, [(0, 0, 0)] * 5, [-1, 0, 1, 0, 3], {2: (1, 2, 3), 4: (0.3, 0.3, 0.3)})
        nodes = tpl_reader.read_tpl_bytes(data, parents=True, bounds=True)
        self.assertEqual(sorted(nodes.bounds), [2, 4])
        self.assertEqual(tuple(round(s, 4) for s in nodes.bounds[2].size), (1, 2, 3))
        self.assertEqual(tuple(round(s, 4) for s in nodes.bounds[4].center()), (0, 0, 0))
        self.assertEqual(nodes.parent("cdt_b"), "b")

    def test_no_table_leaves_a_note(self):
        nodes = tpl_reader.read_tpl_bytes(make_tpl(["r", "s"], [(0, 0, 0)] * 2, [-1, 0], {})[:-16],
                                          parents=False, bounds=True)
        self.assertIsNone(nodes.bounds)
        self.assertIn("No per-mesh bounds table found", nodes.notes)

    def test_parent_tie_break(self):
        names = ["root", "body", "cdt_x"]
        data = make_tpl(names, [(0, 0, 0)] * 3, [-1, 0, 1], {2: (1, 1, 1)})
        data = struct.pack("<3h", -1, 0, 0) + b"\x00" * 4 + data       # a second valid tree: cdt_x under root
        nodes = tpl_reader.read_tpl_bytes(data, parents=False)
        tpl_reader.find_parents(data, nodes)
        self.assertIsNone(nodes.parents)                                 # tie without a tie-break
        tpl_reader.find_parents(data, nodes, tiebreak=pr._cdt_under_bodies({"body"}))
        self.assertEqual(nodes.parent("cdt_x"), "body")

    def test_oriented_box_centre(self):
        box = MeshBounds(min=(0, 0, 0), max=(1, 1, 1), origin=(1.0, 0.0, 0.0),
                         axes=((0.0, 0.0, 1.0), (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0)), size=(2.0, 1.0, 1.0))
        self.assertEqual(box.center(), (0.5, 0.5, 1.0))


def V(value, source="explicit"):  # noqa: N802 - mirrors physics_report.V
    return pr.V(value, source, "test")


def body(name, mass, offset=(0, 0, 0), role="body", root=False, **extra):
    fields = {"effectiveMass": V(mass, "derived"), "hkCenterOfMassOffset": V(list(offset)),
              "boneCenterOfMassOffset": V([0, 0, 0]), "havokMassCenter": V(True)}
    return {"id": name, "kind": "body", "role": role, "fields": fields, "root": root, **extra}


def slot(parent, mass, radius):
    return {"kind": "wheel", "physics": True,
            "fields": {"slot.parentBody": V(parent), "slot.effectiveMass": V(mass, "derived"),
                       "slot.physicalRadius": V(radius, "derived")}}


def nodes_of(names, positions, parents, boxes):
    index = {n: i for i, n in enumerate(names)}
    mats = [(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, x, y, z, 1) for x, y, z in positions]
    bounds = {index[n]: MeshBounds(min=(0, 0, 0), max=(0, 0, 0), origin=tuple(-s / 2 for s in size),
                                   axes=((1, 0, 0), (0, 1, 0), (0, 0, 1)), size=size) for n, size in boxes.items()}
    return TplNodes(names=names, index=index, matrices=mats, parents=parents, bounds=bounds)


class BodyInertiaTests(unittest.TestCase):
    def value(self, ent, key):
        return ent["fields"][key]["value"]

    def test_token_cube_carrier_like_mammoth_rc68(self):
        nodes = nodes_of(["chassis", "carrier", "cdt_carrier"], [(0, 0, 0), (2.5, 1.7, 3.4), (0.45, 1.7, 3.4)],
                         [-1, 0, 1], {"cdt_carrier": (0.3, 0.3, 0.3)})
        carrier = body("carrier", 9000.0, offset=(2.05, 0, 0))
        pr.body_inertia([body("chassis", 60000.0, root=True), carrier], [slot("carrier", 6000.0, 1.581)],
                        nodes, "m.tpl")
        for axis in "xyz":
            self.assertAlmostEqual(self.value(carrier, f"inertia.{axis}"), 135.0, places=3)
            self.assertAlmostEqual(self.value(carrier, f"inertiaRatio.{axis}"), 1 / 6, places=5)
        self.assertAlmostEqual(self.value(carrier, "inertiaPerMass.mid"), 0.015, places=6)
        self.assertAlmostEqual(self.value(carrier, "inertia.extent"), 0.3, places=6)
        self.assertEqual(self.value(carrier, "inertia.shapes"), 1)
        # the COM offset moves the centre of mass, not the tensor; the shifted reading is reported apart
        self.assertAlmostEqual(self.value(carrier, "inertiaAboutCom.x"), 135.0, places=3)
        self.assertAlmostEqual(self.value(carrier, "inertiaAboutCom.y"), 135.0 + 9000 * 2.05 ** 2, places=1)
        wheel_i = 0.5 * 6000 * 1.581 ** 2
        self.assertAlmostEqual(self.value(carrier, "wheels.inertia"), wheel_i, delta=0.01)   # V() keeps 6 digits
        self.assertAlmostEqual(self.value(carrier, "inertiaToWheelInertia"), 135.0 / wheel_i, places=6)
        self.assertEqual(carrier["fields"]["inertia.x"]["source"], "derived")

    def test_two_boxes_use_the_parallel_axis_theorem(self):
        nodes = nodes_of(["hull", "cdt_a", "cdt_b"], [(0, 0, 0), (1, 0, 0), (-1, 0, 0)], [-1, 0, 0],
                         {"cdt_a": (1, 1, 1), "cdt_b": (1, 1, 1)})
        hull = body("hull", 1000.0, role="hull", root=True)
        pr.body_inertia([hull], [], nodes, "m.tpl")
        own = 1000 * (1 + 1) / 12                       # each 500 kg cube about its centre, summed
        self.assertAlmostEqual(self.value(hull, "inertia.x"), own, delta=0.01)
        self.assertAlmostEqual(self.value(hull, "inertia.y"), own + 1000 * 1.0, delta=0.01)
        self.assertAlmostEqual(self.value(hull, "inertia.extent.x"), 3.0, places=6)
        self.assertNotIn("wheels.count", hull["fields"])

    def test_meshes_belong_to_the_nearest_body(self):
        nodes = nodes_of(["hull", "cdt_h", "arm", "cdt_arm", "visual"], [(0, 0, 0)] * 5, [-1, 0, 0, 2, 2],
                         {"cdt_h": (2, 2, 2), "cdt_arm": (0.5, 0.5, 0.5), "visual": (9, 9, 9)})
        hull, arm = body("hull", 1000.0, root=True), body("arm", 100.0)
        pr.body_inertia([hull, arm], [], nodes, "m.tpl")
        self.assertEqual(self.value(hull, "inertia.shapes"), 1)
        self.assertAlmostEqual(self.value(arm, "inertia.extent"), 0.5, places=6)   # the render mesh is ignored

    def test_explicit_inertia_is_reported_as_explicit(self):
        nodes = nodes_of(["b", "cdt_b"], [(0, 0, 0)] * 2, [-1, 0], {"cdt_b": (1, 1, 1)})
        b = body("b", 100.0, root=True, explicitInertia={"value": [10, 20, 30], "evidence": "m:inertia"})
        pr.body_inertia([b], [], nodes, "m.tpl")
        self.assertEqual(b["fields"]["inertia.y"]["value"], 20)
        self.assertEqual(b["fields"]["inertia.y"]["source"], "explicit")
        self.assertAlmostEqual(self.value(b, "inertiaPerMass.mid"), 0.2)
        self.assertEqual(pr._explicit_inertia({"inertia": [1, 2, 3]}, "m", ("objectInfos", 0))["value"], [1, 2, 3])
        self.assertIsNone(pr._explicit_inertia({"mass": 3}, "m", ()))

    def test_no_model_says_why(self):
        b = body("b", 100.0, root=True)
        pr.body_inertia([b], [], None, None)
        self.assertEqual(b["fields"]["inertia.shapes"]["value"], 0)
        self.assertIn("no compiled model", b["fields"]["inertia.shapes"]["evidence"])
        self.assertNotIn("inertiaPerMass.mid", b["fields"])


class JudgeTests(unittest.TestCase):
    def test_floors(self):
        self.assertTrue(v.judge_inertia("wheel carrier", 9000, 0.015, 0.018))        # RC68 front carrier
        self.assertEqual(v.judge_inertia("wheel carrier", 9000, 0.274, 0.33), [])     # RC69
        self.assertEqual(len(v.judge_inertia("wheel carrier", 300, 0.03, 0.05)), 1)   # carriers of any mass
        self.assertEqual(v.judge_inertia("jointed body", 500, 0.0001, None), [])      # light props are not judged
        self.assertTrue(v.judge_inertia("hull", 20000, 0.01, None))
        self.assertEqual(v.judge_inertia("hull", 20000, None, None), [])              # no estimate, no finding
        for role, floor in v.INERTIA_FLOOR.items():
            self.assertLess(floor, v.INERTIA_RETAIL_MIN[role])
        self.assertLess(v.INERTIA_WHEEL_FLOOR, v.INERTIA_WHEEL_RETAIL_MIN)


TRUCK = """properties = {
   geom = { nameTpl = "m" }
   prop_truck_rb = {
      wheelPool = { W = "auto_wheel_m" }
      wheelSlotWithDescs = [
         { geomName = "wheel_fl" editableWheel = "W" parentFrame = "BoneCarrier_cdt" }
      ]
   }
}
"""
WHEEL = "properties = {\n prop_truck_wheel = { mass = 6000 radius = 1.581 }\n}\n"
MARKUP = """objectInfos = [
   {
      objectId = { name = "BoneChassis_cdt" }
      properties = [ { massFromDensity = False mass = 60000 __type = "tpl_markup_object_property_physics" } ]
   },
   {
      objectId = { name = "BoneCarrier_cdt" }
      properties = [ { massFromDensity = False mass = 9000 __type = "tpl_markup_object_property_physics" } ]
      entities = [ { target = "BoneChassis_cdt" __type = "tpl_markup_constraint_prismatic" } ]
   }
]
"""


def make_mod(root: Path, carrier_box) -> Path:
    names = ["BoneChassis_cdt", "cdt_chassis", "BoneCarrier_cdt", "cdt_carrier", "wheel_fl"]
    tpl = make_tpl(names, [(0, 1, 0), (0, 1.5, 0), (2.5, 1.7, 3.4), (0.45, 1.7, 3.4), (2.5, 1.7, 3.4)],
                   [-1, 0, 0, 2, 2], {1: (3.0, 1.5, 10.0), 3: carrier_box})
    files = {"ssl/auto_m.cls": TRUCK, "ssl/auto_wheel_m.cls": WHEEL,
             "models/mods/m.tpl.asset/m.tpl_markup": MARKUP}
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    (root / "models/mods/m.tpl.asset/tpl").mkdir(parents=True, exist_ok=True)
    (root / "models/mods/m.tpl.asset/tpl/m.tpl").write_bytes(tpl)
    return root


class SyntheticRuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.no_game = self.tmp / "no_game"

    def findings(self, box):
        mod = make_mod(self.tmp / f"mod_{box[0]}", box)
        return [f for f in v.validate(mod, rules=["body-inertia"], game_root=self.no_game) if f.code == "RC080"]

    def test_token_cube_carrier_is_flagged(self):
        hits = self.findings((0.3, 0.3, 0.3))
        self.assertEqual(len(hits), 1)
        self.assertEqual((hits[0].severity, hits[0].key), ("warning", "objectInfos[1]"))
        self.assertIn("BoneCarrier_cdt", hits[0].message)
        self.assertIn("135/135/135", hits[0].message)
        self.assertIn("collision shapes", hits[0].fixHint)

    def test_real_sized_carrier_passes(self):
        self.assertEqual(self.findings((0.22, 1.2, 1.8)), [])

    def test_report_carries_role_and_fields(self):
        mod = make_mod(self.tmp / "mod_r", (0.3, 0.3, 0.3))
        truck = pr.report(mod, ctx=pr.Context(self.no_game))["trucks"][0]
        carrier = next(e for e in truck["entities"] if e["id"] == "BoneCarrier_cdt")
        self.assertEqual(carrier["inertiaRole"], "wheel carrier")
        self.assertEqual(carrier["fields"]["wheels.count"]["value"], 1)
        rows = pr.inertia_rows(truck, "m")
        self.assertEqual({r["role"] for r in rows}, {"hull", "wheel carrier"})


GAME_ROOT = schema_mod.default_game_root()
RETAIL = (GAME_ROOT / "root/paks/client").is_dir()
SHARE = Path("//192.168.0.129/Downloads/roadcraft_bench/mammoth_series_spring")
RC68 = SHARE / "mammoth_rc68_twostage_5be91383.pak"
RC69 = SHARE / "mammoth_rc69_seriesspring_6cfd86f5.pak"


@unittest.skipUnless(RETAIL, f"RoadCraft retail paks not installed at {GAME_ROOT}")
class RetailCalibrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.dist = pr.inertia_distribution(pr.Context(GAME_ROOT), cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, True)

    def test_retail_gives_no_rc080(self):
        rows = self.dist["rows"]
        self.assertGreater(len(rows), 1000)
        hits = [r for r in rows if v.judge_inertia(r["role"], pr._num(r["mass"]), r["inertiaPerMass.mid"],
                                                   r["inertiaToWheelInertia"])]
        self.assertEqual(hits, [])

    def test_every_role_has_a_spread(self):
        for role, scope in (("hull", ">=1t"), ("wheel carrier", "all"), ("track frame", "all"),
                            ("jointed body", ">=1t")):          # the RC080 scope of each role
            stats = self.dist["roles"][role][scope]["inertiaPerMass.mid"]
            self.assertGreater(stats["n"], 0, role)
            self.assertGreaterEqual(stats["min"], v.INERTIA_FLOOR[role], role)

    def test_cache_round_trip(self):
        pr._INERTIA.clear()
        again = pr.inertia_distribution(pr.Context(GAME_ROOT), self.tmp)
        self.assertTrue(again["cache"]["hit"])
        self.assertEqual(again["roles"], self.dist["roles"])


@unittest.skipUnless(RC68.is_file() and RC69.is_file(), f"Mammoth bench paks not reachable: {SHARE}")
class MammothAcceptanceTests(unittest.TestCase):
    def test_rc68_front_carriers_flagged_rc69_passes(self):
        hits = [f for f in v.validate(RC68, rules=["body-inertia"]) if f.code == "RC080"]
        self.assertEqual(sorted(f.message.split("'")[1] for f in hits),
                         ["BoneSuspFrontLeft_cdt", "BoneSuspFrontRight_cdt"])
        self.assertEqual([f for f in v.validate(RC69, rules=["body-inertia"]) if f.code == "RC080"], [])


if __name__ == "__main__":
    unittest.main()
