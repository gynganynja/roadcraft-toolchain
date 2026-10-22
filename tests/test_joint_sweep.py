"""Hull contact over a joint's travel: the separating-axis shapes and collision filter of roadcraft.joint_sweep, the
physics report's sweep.* fields (physics_report.joint_sweeps) and the RC082 validator rule.

Synthetic fixtures need no SDK.  The Mammoth RC69/RC70 run needs the LAN share and skips with a reason otherwise.
"""

import math
import shutil
import tempfile
import unittest
from pathlib import Path

from roadcraft import joint_sweep as js
from roadcraft import physics_report as pr
from roadcraft import schema as schema_mod
from roadcraft import validate as v
from test_body_inertia import _reachable, make_tpl

AXES = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]


def box(name, body, center, size):
    return js.box_shape(name, body, center, AXES, size)


class ShapeTests(unittest.TestCase):
    def test_boxes(self):
        a = box("a", "A", (0, 0, 0), (1, 1, 1))
        self.assertTrue(js.touching(a, box("b", "B", (0.9, 0, 0), (1, 1, 1))))
        self.assertFalse(js.touching(a, box("b", "B", (1.004, 0, 0), (1, 1, 1))))    # within the contact epsilon
        self.assertFalse(js.touching(a, box("b", "B", (1.2, 1.2, 0), (1, 1, 1))))
        turned = js.box_shape("r", "R", (1.3, 1.3, 0), [(0.7071068, 0.7071068, 0), (-0.7071068, 0.7071068, 0),
                                                       (0, 0, 1)], (1, 1, 1))
        self.assertFalse(js.touching(a, turned))                     # apart only along the edge-edge diagonal
        self.assertTrue(js.touching(a, turned.moved(offset=(-0.5, -0.5, 0))))

    def test_cylinder(self):
        wheel = js.cylinder_shape("w", "w", (0, 0, 0), (1, 0, 0), radius=1.0, width=0.5)
        self.assertTrue(js.touching(wheel, box("b", "B", (0, 0, 1.1), (0.2, 0.2, 0.4))))
        self.assertFalse(js.touching(wheel, box("b", "B", (0, 0, 1.25), (0.2, 0.2, 0.4))))
        # a box off the rim's diagonal: inside the bounding square, outside the circle
        self.assertFalse(js.touching(wheel, box("b", "B", (0, 0.85, 0.85), (0.2, 0.2, 0.2))))
        self.assertTrue(js.touching(wheel, box("b", "B", (0, 0.65, 0.65), (0.2, 0.2, 0.2))))


class FilterTests(unittest.TestCase):
    LAYERS = {}

    def test_direct_parent_only(self):
        f = js.Filter([("body", "chassis"), ("carrier", "chassis"), ("roll", "carrier")], 3, [], self.LAYERS)
        self.assertTrue(f.blocked("carrier", "chassis"))
        self.assertTrue(f.blocked("roll", "carrier"))
        self.assertFalse(f.blocked("roll", "chassis"))               # grandparent
        self.assertFalse(f.blocked("carrier", "body"))               # cousin on a fixed joint
        self.assertTrue(f.blocked("body", "chassis"))

    def test_first_child_not_filtered_against_its_children(self):
        f = js.Filter([("body", "chassis"), ("dump", "body")], 2, [], self.LAYERS)
        self.assertEqual(f.ids["body"], 0)
        self.assertFalse(f.blocked("dump", "body"))

    def test_constraint_cap_and_layer(self):
        f = js.Filter([("carrier", "chassis")], js.CONSTRAINT_CAP, [], {"x": "no_collision"})
        self.assertFalse(f.blocked("carrier", "chassis"))
        self.assertTrue(f.blocked("x", "chassis"))

    def test_collision_group_overwrites_ids(self):
        # body|chassis first (ids 0, 1), the carrier's dontCollideWith is 1; the group's members get id = dont = 2
        # (the engine's sub-system table: "default" 0, "no_self_collision" 1, the first markup group 2)
        f = js.Filter([("body", "chassis"), ("carrier", "chassis"), ("arm", "body")], 3,
                      [["chassis", "body", "dump"]], self.LAYERS, ["main_collision_grp"])
        self.assertEqual((f.ids["chassis"], f.dont["chassis"], f.group_mask["chassis"]), (2, 2, 4))
        self.assertTrue(f.blocked("dump", "chassis"))                # members block each other
        self.assertEqual(f.ids["carrier"], 2)                        # constraint id 2 == the group index:
        self.assertTrue(f.blocked("carrier", "chassis"))             # blocked by coincidence, not by its dont 1
        self.assertFalse(f.blocked("arm", "body"))                   # its dont (body's old id 0) is ignored

    def test_group_indices_follow_the_engine_table(self):
        self.assertEqual(js.group_indices(["main_collision_grp"]), [2])
        self.assertEqual(js.group_indices(["a", "b", "c"]), [2, 3, 4])
        self.assertEqual(js.group_indices(["default", "x", "no_self_collision"]), [0, 3, 1])
        self.assertEqual(js.group_indices([None] * 31)[-1], 0)          # beyond 32 table entries: set to 0
        self.assertEqual(js.group_indices([None] * 30)[-1], 31)
        doc = {"collisionGroups": {"truck": {"objects": ["A", "B"]}, "bad": 3, "dump": {"objects": ["C"]}}}
        self.assertEqual(js.collision_groups(doc), [["A", "B"], ["C"]])
        self.assertEqual(js.collision_group_names(doc), ["truck", "dump"])
        # a group named "default" is index 0 = bit 0, which the pair test clears: its members collide
        f = js.Filter([("body", "chassis")], 1, [["body", "chassis"]], self.LAYERS, ["default"])
        self.assertFalse(f.blocked("body", "chassis"))
        f = js.Filter([("body", "chassis")], 1, [["body", "chassis"]], self.LAYERS, ["truck"])
        self.assertTrue(f.blocked("body", "chassis"))

    def test_body_in_no_group_against_a_group(self):
        # the Mammoth RC75 markup: 23 constraints, one group main_collision_grp (dump, body, chassis, rock ejectors);
        # the engine walks the joint tree breadth first, so body 0, chassis 1, then the chassis's other children in
        # markup order: front-left carrier 2, front-right 3 (the markup lists the dump second, but it is deeper).
        # The group's index is 2: members get id = dont = 2, which is the FL carrier's own id, so FL (and its
        # wheel) is filtered against every member and FR is not (bench 2026-10-22: FR and the rear link jack the
        # truck up on hull contact, FL hangs in the air)
        cons = [("body", "chassis"), ("dump", "body"), ("carrierL", "chassis"), ("carrierR", "chassis")]
        group = [["dump", "body", "chassis", "ejectorL", "ejectorR"]]
        f = js.Filter(cons, 22, group, self.LAYERS, ["main_collision_grp"])
        self.assertEqual([c[0] for c in js.engine_order(cons)], ["body", "carrierL", "carrierR", "dump"])
        self.assertEqual((f.ids["carrierL"], f.dont["carrierL"]), (2, 1))
        self.assertEqual((f.ids["carrierR"], f.dont["carrierR"]), (3, 1))
        self.assertEqual((f.ids["chassis"], f.dont["chassis"], f.group_mask["chassis"]), (2, 2, 4))
        for member in ("chassis", "body", "dump"):
            self.assertTrue(f.blocked("carrierL", member), member)      # own id 2 == group index
            self.assertFalse(f.blocked("carrierR", member), member)     # dont 1 matches nothing any more
        self.assertFalse(f.blocked("carrierL", "carrierR"))  # siblings, neither grouped
        # the bench variant group1 renames the group no_self_collision: index 1 == the carriers' dont, all blocked
        f1 = js.Filter(cons, 22, group, self.LAYERS, ["no_self_collision"])
        for member in ("chassis", "body", "dump"):
            self.assertTrue(f1.blocked("carrierL", member) and f1.blocked("carrierR", member), member)
        old = js.GROUP_BASE
        try:
            js.GROUP_BASE = 0                                # 0-based: index 0 is bit 0, which the test clears
            f0 = js.Filter(cons, 22, group, self.LAYERS)
            for member in ("chassis", "body", "dump"):
                self.assertFalse(f0.blocked("carrierR", member), member)
            self.assertFalse(f0.blocked("body", "chassis"))  # even group members then collide
        finally:
            js.GROUP_BASE = old
        old = js.ENGINE_ORDER
        try:
            js.ENGINE_ORDER = False                          # markup order: the dump takes id 2, both carriers miss
            fm = js.Filter(cons, 22, group, self.LAYERS, ["main_collision_grp"])
            self.assertEqual((fm.ids["carrierL"], fm.ids["carrierR"]), (3, 4))
            self.assertFalse(fm.blocked("carrierL", "chassis") or fm.blocked("carrierR", "chassis"))
        finally:
            js.ENGINE_ORDER = old

    def test_engine_order_is_breadth_first(self):
        cons = [("a2", "a"), ("a", "root"), ("b", "root"), ("b1", "b"), ("x", "y"), ("y", "x")]
        self.assertEqual([c[0] for c in js.engine_order(cons)], ["a", "b", "a2", "b1", "x", "y"])


def entity(name, joint=None, layer="default"):
    fields = {"collisionLayer": pr.V(layer, "explicit", "t")}
    if joint:
        fields["joint.type"] = pr.V(joint, "explicit", "t")
    return {"id": name, "kind": "body", "role": "body", "fields": fields}


def nodes(names, positions, parents, boxes):
    from roadcraft.tpl_reader import MeshBounds, TplNodes
    index = {n: i for i, n in enumerate(names)}
    mats = [(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, x, y, z, 1) for x, y, z in positions]
    bounds = {index[n]: MeshBounds(min=(0, 0, 0), max=(0, 0, 0), origin=tuple(-s / 2 for s in size),
                                   axes=((1, 0, 0), (0, 1, 0), (0, 0, 1)), size=size) for n, size in boxes.items()}
    return TplNodes(names=names, index=index, matrices=mats, parents=parents, bounds=bounds)


def info(name, constraint=None):
    out = {"objectId": {"name": name}}
    if constraint:
        out["entities"] = [constraint]
    return out


PRISMATIC = {"__type": "tpl_markup_constraint_prismatic", "childRotation": [90, 0, 0], "isMinLimit": True,
             "minLimit": -0.2, "isMaxLimit": True, "maxLimit": 0.2}       # + = down (library/headless-bench.md)


class PrismaticSweepTests(unittest.TestCase):
    """A carrier box under a body box fixed to the chassis (0.10 m gap) and above a chassis box (0.05 m gap)."""

    def run_sweep(self, with_body=True):
        names = ["chassis", "cdt_chassis", "body", "cdt_body", "carrier", "cdt_carrier"]
        tree = nodes(names, [(0, 1, 0), (0, 1.05, 0), (0, 2, 0), (0, 2, 0), (0, 1.5, 0), (0, 1.5, 0)],
                     [-1, 0, 0, 2, 0, 4], {"cdt_chassis": (1, 0.4, 1), "cdt_body": (0.4, 0.4, 0.4),
                                           "cdt_carrier": (0.4, 0.4, 0.4)})
        infos = [info("chassis"), info("carrier", PRISMATIC)]
        bodies = [entity("chassis"), entity("carrier", "prismatic")]
        if with_body:
            infos.insert(1, info("body", {"__type": "tpl_markup_constraint_fixed"}))
            bodies.insert(1, entity("body"))
        pr.joint_sweeps(bodies, [], {}, tree, "m.tpl", infos, [])
        return {k: f["value"] for k, f in bodies[-1]["fields"].items() if k.startswith("sweep.")}

    def test_hit_at_known_distance(self):
        f = self.run_sweep()
        self.assertEqual(f["sweep.status"], "contact within travel")
        self.assertAlmostEqual(f["sweep.low.firstContact"], -0.10 - js.CONTACT_EPS, delta=0.002)
        self.assertEqual(f["sweep.low.pair"], "cdt_carrier (carrier) x cdt_body (body)")
        self.assertAlmostEqual(f["sweep.low.clearance"], -0.095, delta=0.002)

    def test_direct_parent_pair_ignored(self):
        f = self.run_sweep(with_body=False)
        self.assertEqual(f["sweep.status"], "clear")
        self.assertIsNone(f["sweep.high.firstContact"])           # the chassis box 0.05 m below is its parent's
        self.assertIsNone(f["sweep.low.firstContact"])
        self.assertEqual(f["sweep.parent"], "chassis")

    def _spy(self, groups, group_names, slots=(), classes=None, rotate=None):
        """Run joint_sweeps with sweep_truck replaced by a recorder; return its arguments."""
        names = ["chassis", "cdt_chassis", "carrier", "cdt_carrier", "wheel"]
        tree = nodes(names, [(0, 1, 0), (0, 1, 0), (0, 1.5, 0), (0, 1.5, 0), (1.2, 1.5, 0)], [-1, 0, 0, 2, 2],
                     {"cdt_chassis": (1, 0.4, 1), "cdt_carrier": (0.4, 0.4, 0.4)})
        if rotate:
            tree.matrices[names.index("wheel")] = rotate
        seen = {}
        real = js.sweep_truck
        js.sweep_truck = lambda *a: seen.setdefault("args", a) and {}
        try:
            pr.joint_sweeps([entity("chassis"), entity("carrier", "prismatic")], list(slots), classes or {}, tree,
                            "m.tpl", [info("chassis"), info("carrier", PRISMATIC)], groups, group_names)
        finally:
            js.sweep_truck = real
        return seen["args"]

    def test_group_names_reach_the_filter(self):
        # Mammoth RC76: a group renamed no_self_collision must reach sweep_truck, or it is judged as index 2
        args = self._spy([["chassis", "carrier"]], ["no_self_collision"])
        self.assertEqual(args[-1], ["no_self_collision"])
        self.assertEqual(js.group_indices(args[-1]), [1])

    def test_wheel_axle_ignores_the_node_rotation(self):
        # a wheel node with X pointing forward (retail and Mammoth duals) still gets a lateral axle
        slot = {"id": "slot[0]", "physics": True, "fields": {
            "slot.geomName": pr.V("wheel", "explicit", "t"), "slot.parentBody": pr.V("carrier", "explicit", "t"),
            "slot.physicalRadius": pr.V(0.5, "explicit", "t"), "slot.class": pr.V("w", "explicit", "t")}}
        wclass = {"physics": True, "fields": {"class": pr.V("w", "explicit", "t"),
                                              "width": pr.V(2.2, "explicit", "t")}}
        forward = (0, 0, 1, 0, 0, 1, 0, 0, -1, 0, 0, 0, 1.2, 1.5, 0, 1)
        wheels = self._spy([], [], [slot], {"w": wclass}, rotate=forward)[5]
        self.assertEqual(len(wheels), 1)
        self.assertEqual(wheels[0].axes[0], (1.0, 0.0, 0.0))
        self.assertAlmostEqual(wheels[0].half[0], 1.1)

    def test_judge(self):
        res = {"margin": 0.03, "low": {"limit": -0.2, "contact": -0.21, "moving": None, "static": None},
               "high": {"limit": 0.2, "contact": 0.25, "moving": None, "static": None}}
        self.assertEqual([(x["side"], x["severity"]) for x in js.judge(res)], [("low", "info")])
        res["low"]["contact"] = -0.02
        self.assertEqual(js.judge(res)[0]["severity"], "warning")


class HingeSweepTests(unittest.TestCase):
    def test_flap_hits_a_box_at_the_expected_angle(self):
        flap = box("cdt_flap", "flap", (0.5, 0, 0), (1, 0.1, 0.1))
        other = box("cdt_post", "post", (0.5, 0.4, 0), (0.4, 0.2, 0.2))      # x 0.3..0.7, y 0.3..0.5
        res = js.sweep_joint("hinge", [flap], [other], lambda a, b: True, (0, 0, 0), (0, 0, 1), -30.0, 60.0)
        # the flap's upper face (0.05 m off its axis) passes the post's corner (0.7, 0.3) by the epsilon
        expected = next(d / 100 for d in range(0, 6000) if 0.3 * math.cos(math.radians(d / 100))
                        - 0.7 * math.sin(math.radians(d / 100)) <= 0.05 - js.CONTACT_EPS)
        self.assertAlmostEqual(res["high"]["contact"], expected, delta=0.1)
        self.assertIsNone(res["low"]["contact"])
        self.assertEqual(res["restOverlaps"], [])

    def test_wheel_cylinder_on_the_moving_body(self):
        # a hinge arm carrying a wheel; the wheel (r 0.5, axle along x) swings into a box of an unrelated body
        arm = box("cdt_arm", "arm", (0, 0, 1), (0.1, 0.1, 2))
        wheel = js.cylinder_shape("w", "w", (0, 0, 2), (1, 0, 0), 0.5, 0.3)
        post = box("cdt_post", "post", (0, 1.2, 2), (0.3, 0.3, 0.3))    # 0.55 m over the wheel centre
        res = js.sweep_truck([{"child": "arm", "parent": None, "kind": "hinge", "objectIndex": 0,
                               "entity": {"childRotation": [0, 90, 0], "limited": True, "angleStart": -30,
                                          "angleEnd": 30}}], 1, [], {}, {"arm": [arm], "post": [post]}, [wheel],
                             {"w": "arm"}, lambda name: (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1))
        hit = js.judge(res["arm"])
        self.assertEqual(len(hit), 1)
        self.assertEqual(js.describe(hit[0]["moving"]), "wheel w")

    def test_posed_work_part_is_left_out_of_a_wheel_carrier_sweep(self):
        # a sprung carrier (with its wheel) rising into a crane arm box: the arm is on a position motor and
        # carries no wheels, so its modelled pose is one of many and the carrier is judged without it
        identity = (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)
        cons = [{"child": "carrier", "parent": "chassis", "kind": "prismatic", "objectIndex": 0, "entity": PRISMATIC},
                {"child": "arm", "parent": "chassis", "kind": "hinge", "objectIndex": 1,
                 "entity": {"limited": True, "angleStart": -10, "angleEnd": 10,
                            "motor": {"__type": "tpl_markup_position_motor"}}}]
        shapes = {"carrier": [box("cdt_carrier", "carrier", (0, 0, 0), (0.4, 0.4, 0.4))],
                  "arm": [box("cdt_arm", "arm", (0, 0.35, 0), (0.4, 0.2, 0.4))]}
        wheel = js.cylinder_shape("w", "w", (3, -1, 0), (1, 0, 0), 0.5, 0.3)
        res = js.sweep_truck(cons, 2, [], {}, shapes, [wheel], {"w": "carrier"}, lambda name: identity)
        self.assertEqual(res["carrier"]["posedSkipped"], ["arm"])
        self.assertIsNone(res["carrier"]["low"]["contact"])
        res = js.sweep_truck(cons, 2, [], {}, shapes, [], {}, lambda name: identity)    # no wheels: kept
        self.assertAlmostEqual(abs(res["carrier"]["low"]["contact"]), 0.05 + js.CONTACT_EPS, delta=0.002)

    def test_rest_overlap_is_left_out(self):
        flap = box("cdt_flap", "flap", (0.5, 0, 0), (1, 0.1, 0.1))
        res = js.sweep_joint("hinge", [flap], [box("p", "post", (0.5, 0, 0), (0.2, 0.2, 0.2))],
                             lambda a, b: True, (0, 0, 0), (0, 0, 1), -10.0, 10.0)
        self.assertEqual(len(res["restOverlaps"]), 1)
        self.assertEqual(res["pairs"], 0)


TRUCK = """properties = {
   geom = { nameTpl = "m" }
   prop_truck_rb = {
      wheelPool = { W = "auto_wheel_m" }
      wheelSlotWithDescs = [ { geomName = "wheel_fl" editableWheel = "W" } ]
   }
}
"""
WHEEL = "properties = {\n prop_truck_wheel = { mass = 600 radius = 0.5 width = 0.3 }\n}\n"
MARKUP = """objectInfos = [
   {
      objectId = { name = "BoneChassis_cdt" }
      properties = [ { massFromDensity = False mass = 6000 __type = "tpl_markup_object_property_physics" } ]
   },
   {
      objectId = { name = "BoneBody_cdt" }
      properties = [ { massFromDensity = False mass = 2000 __type = "tpl_markup_object_property_physics" } ]
      entities = [ { __type = "tpl_markup_constraint_fixed" } ]
   },
   {
      objectId = { name = "BoneCarrier_cdt" }
      properties = [ { massFromDensity = False mass = 900 __type = "tpl_markup_object_property_physics" } ]
      entities = [ { childRotation = [ 90, 0, 0 ] isMinLimit = True minLimit = -0.2 isMaxLimit = True
                     maxLimit = %s __type = "tpl_markup_constraint_prismatic" } ]
   }
]
"""


def make_mod(root: Path, max_limit: float) -> Path:
    names = ["BoneChassis_cdt", "cdt_chassis", "BoneBody_cdt", "cdt_body", "BoneCarrier_cdt", "cdt_carrier",
             "wheel_fl"]
    # the carrier box 0.10 m under the body box (fixed to the chassis: a cousin, not filtered); the wheel hangs
    # 1.0 m under the carrier, clear of everything
    tpl = make_tpl(names, [(0, 1, 0), (5, 1, 0), (0, 2, 0), (0, 2, 0), (0, 1.5, 0), (0, 1.5, 0), (0, 0.5, 0)],
                   [-1, 0, 0, 2, 0, 4, 4], {1: (1, 1, 1), 3: (0.4, 0.4, 0.4), 5: (0.4, 0.4, 0.4)})
    files = {"ssl/auto_m.cls": TRUCK, "ssl/auto_wheel_m.cls": WHEEL,
             "models/mods/m.tpl.asset/m.tpl_markup": MARKUP % max_limit}
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

    def test_contact_within_travel_is_a_warning(self):
        mod = make_mod(self.tmp / "mod", 0.2)
        hits = [f for f in v.validate(mod, rules=["joint-sweep"], game_root=self.tmp / "no_game")
                if f.code == "RC082"]
        self.assertEqual([(f.severity, f.key) for f in hits], [("warning", "objectInfos[2]")])
        self.assertIn("0.105 m from rest", hits[0].message)
        self.assertIn("cdt_carrier (BoneCarrier_cdt) x cdt_body (BoneBody_cdt)", hits[0].message)

    def test_report_fields(self):
        mod = make_mod(self.tmp / "mod", 0.2)
        truck = pr.report(mod, ctx=pr.Context(self.tmp / "no_game"))["trucks"][0]
        carrier = next(e for e in truck["entities"] if e["id"] == "BoneCarrier_cdt")["fields"]
        self.assertEqual(carrier["sweep.status"]["value"], "contact within travel")
        self.assertIsNone(carrier["sweep.high.firstContact"]["value"])
        self.assertEqual(carrier["sweep.low.pair"]["value"], "cdt_carrier (BoneCarrier_cdt) x cdt_body (BoneBody_cdt)")
        self.assertEqual(carrier["sweep.parent"]["value"], "BoneChassis_cdt")


GAME_ROOT = schema_mod.default_game_root()
RETAIL = (GAME_ROOT / "root/paks/client").is_dir()
# The one retail wheel-carrying joint with contact inside its travel: the superseded ZiKZ 605E heavy transporter's
# rockers (their own Collision Group, so not filtered against the chassis; the current _res class is clear).
RETAIL_EXPLAINED = {("zikz_605e_heavy_transporter_old", "BoneSuspensionRockerLeft_cdt"),
                    ("zikz_605e_heavy_transporter_old", "BoneSuspensionRockerRight_cdt")}


@unittest.skipUnless(RETAIL, f"RoadCraft retail paks not installed at {GAME_ROOT}")
class RetailCalibrationTests(unittest.TestCase):
    def test_retail_wheel_carrying_joints_have_no_contact_within_travel(self):
        ctx = pr.Context(GAME_ROOT)
        hits, swept = set(), 0
        for name in sorted(pr.retail_trucks(ctx)):
            for ent in pr.retail_report(ctx, name)["entities"]:
                f = ent["fields"]
                if not f.get("sweep.movingWheels", {}).get("value"):
                    continue
                swept += 1
                if f["sweep.status"]["value"] != "clear":
                    hits.add((name, ent["id"]))
            ctx.retail_cache.pop(name, None)
        self.assertGreater(swept, 150)
        self.assertEqual(hits, RETAIL_EXPLAINED)


SHARE = Path("//192.168.0.129/Downloads/roadcraft_bench/mammoth_series_spring")
RC69 = SHARE / "mammoth_rc69_seriesspring_6cfd86f5.pak"
RC70 = SHARE / "mammoth_rc70_swept_6726811a.pak"
SPRUNG = ("BoneSuspFrontLeft_cdt", "BoneSuspFrontRight_cdt", "BoneSuspRear_cdt")


@unittest.skipUnless(_reachable(lambda: RC69.is_file() and RC70.is_file()), f"Mammoth bench paks not reachable: {SHARE}")
class MammothTests(unittest.TestCase):
    def test_sprung_bodies_are_swept(self):
        for pak in (RC69, RC70):
            truck = pr.report(pak)["trucks"][0]
            fields = {e["id"]: e["fields"] for e in truck["entities"] if e["kind"] == "body"}
            for body in SPRUNG:
                self.assertNotEqual(fields[body]["sweep.status"]["value"], "not checked", (pak.name, body))
                self.assertEqual(fields[body]["sweep.parent"]["value"], "BoneChassis_cdt")


if __name__ == "__main__":
    unittest.main()
