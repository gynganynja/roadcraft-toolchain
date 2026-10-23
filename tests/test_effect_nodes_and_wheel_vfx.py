"""lint-bro RC025 on stock effect emitters, RC027 (parentArea emitter on a node without a mesh) and RC028 (wheel vfx
cylinder off the axle), from the 2026-10-23 installed-mod node audit (library/frames.md, cockpit-and-lamps.md)."""

import unittest

from roadcraft import bro_lint
from roadcraft.tpl_reader import MeshBounds, TplNodes

from tests.test_validate import Base, codes, four_wheels, matrix, tpl_bytes, truck_cls

IDENTITY = (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)
RETAIL_WHEEL = (0, 0, -1, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 1)   # rows: local X, Y, Z; native Z along the axle
BOX = MeshBounds(min=(-0.03, -0.03, 0), max=(0.03, 0.03, 0), origin=(-0.03, -0.03, 0),
                 axes=((1, 0, 0), (0, 1, 0), (0, 0, 1)), size=(0.06, 0.06, 0))


def model(rows, bounds=True):
    """rows: (name, has mesh, 16-float matrix or None for identity at the origin)."""
    names = [r[0] for r in rows]
    nodes = TplNodes(names=names, index={n: i for i, n in enumerate(names)},
                     matrices=[r[2] or IDENTITY for r in rows])
    nodes.bounds = {i: BOX for i, r in enumerate(rows) if r[1]} if bounds else None
    return nodes


def emitter(parent=None, source="local__parentArea", visible=None):
    em = {"emission": {"source": {"__type": source}}}
    if parent:
        em["nameParent"] = parent
    if visible is not None:
        em["isVisible"] = visible
    return em


# Stock part_exhaust_small_cars / part_radiator_haze, reduced: visible parentArea smoke, an invisible wind burst.
STOCK = {
    "part_exhaust_small_cars": {"nameParent": "sfx_exhaust_*", "emitters2": {
        "Smoke_Flow_2": emitter(), "CPU_Smoke": emitter(visible=False),
        "wind_expl_01_5": emitter(source="local__geomPrimitive", visible=False)}},
    "part_radiator_haze": {"emitters2": {"CPU_Smoke_6": emitter("sfx_radiator_haze"),
                                         "CPU_Smoke_1": emitter("sfx_radiator_haze", visible=False)}},
    "part_water_impact_long": {"isAutoStart": True, "emitters2": {"Splash": emitter(source="local__externalControl")}},
}


def stock(name):
    return STOCK.get(name)


def lint(nodes, listed=None, started=("part_exhaust_small_cars", "part_radiator_haze")):
    listed = {name: {} for name in started} if listed is None else listed
    return bro_lint.effect_emitter_findings(listed, set(started), nodes, stock)


class StockEmitterNodeTests(unittest.TestCase):
    """RC025 extended: apoc buggy / Warthog start the stock exhaust and haze with no sfx_* node."""

    def test_started_stock_effects_without_nodes_are_errors(self):
        rows = lint(model([("BoneChassis_cdt", True, None)]))
        self.assertEqual([(f["code"], f["severity"], f["where"]) for f in rows],
                         [("RC025", "error", "sfx.list.part_exhaust_small_cars"),
                          ("RC025", "error", "sfx.list.part_radiator_haze")])
        self.assertIn("Smoke_Flow_2", rows[0]["message"])
        self.assertIn("'sfx_exhaust_*'", rows[0]["message"])
        self.assertNotIn("CPU_Smoke", rows[0]["message"])     # invisible emitters are not listed

    def test_helper_meshes_with_wildcard_are_clean(self):
        nodes = model([("BoneChassis_cdt", True, None), ("sfx_exhaust_01", True, None),
                       ("sfx_radiator_haze", True, None)])
        self.assertEqual(lint(nodes), [])

    def test_override_rebinding_to_an_outlet_is_clean(self):
        # Lada / Trophy / Watcher: point-source override on their own outlet empty; haze node present.
        listed = {"part_exhaust_small_cars": {"emitters2": {"Smoke_Flow_2": {
            "nameParent": "ttc_exhaust_outlet", "emission": {"source": {"__type": "local__point"}}}}},
            "part_radiator_haze": {}}
        nodes = model([("ttc_exhaust_outlet", False, None), ("sfx_radiator_haze", True, None)])
        self.assertEqual(lint(nodes, listed), [])

    def test_listed_but_never_started_effects_are_skipped(self):
        # The SDK Lynx effects block copied whole (Dump Twuck, 54 entries): only started ones can show.
        self.assertEqual(lint(model([("BoneChassis_cdt", True, None)]),
                              {"part_exhaust_small_cars": {}, "part_radiator_haze": {}}, started=()), [])

    def test_unbound_auto_start_emitters_are_not_node_bound(self):
        self.assertEqual(lint(model([("x", True, None)]), {"part_water_impact_long": {}}, started=()), [])

    def test_bro_check_needs_the_stock_reader_and_reports_a_pattern_once(self):
        doc = {"blueprint": {"blueprints": {"SFX": {"nodes": {"A": {
            "vfxUidRef": {"def": "part_radiator_haze"}, "__type": "BlueprintNodeVfxRestart"}}}}},
            "effects": {"propSfx": {"list": {"part_radiator_haze": {"emitters2": {"CPU_Smoke_6": {
                "nameParent": "sfx_radiator_haze"}}}}}, "__type": "EffectsSettings"}}
        nodes = model([("BoneChassis_cdt", True, None)])
        without = [f for f in bro_lint.lint_truck(doc, model=nodes) if f["code"] == "RC025"]
        with_stock = [f for f in bro_lint.lint_truck(doc, model=nodes, stock_sfx=stock) if f["code"] == "RC025"]
        self.assertEqual([f["where"] for f in without], ["effects"])
        self.assertEqual([f["where"] for f in with_stock], ["effects"])   # own nameParent already reported
        doc["effects"]["propSfx"]["list"]["part_radiator_haze"] = {}
        with_stock = [f for f in bro_lint.lint_truck(doc, model=nodes, stock_sfx=stock) if f["code"] == "RC025"]
        self.assertEqual([f["where"] for f in with_stock], ["effects.propSfx.list.part_radiator_haze"])


class ParentAreaOnEmptyTests(unittest.TestCase):
    """RC027: CAT 793D sfx_exhaust_02/03 and sfx_radiator_haze are empties (PLAIN_AXES)."""

    def test_parent_area_emitters_on_empties_are_warnings(self):
        nodes = model([("sfx_exhaust_02", False, None), ("sfx_exhaust_03", False, None),
                       ("sfx_radiator_haze", False, None)])
        rows = lint(nodes)
        self.assertEqual([(f["code"], f["severity"]) for f in rows], [("RC027", "warning"), ("RC027", "warning")])
        self.assertIn("['sfx_exhaust_02', 'sfx_exhaust_03']", rows[0]["message"])
        self.assertIn("inferred", rows[0]["message"])

    def test_only_the_empty_match_of_a_wildcard_is_named(self):
        nodes = model([("sfx_exhaust_01", True, None), ("sfx_exhaust_02", False, None),
                       ("sfx_radiator_haze", True, None)])
        rows = lint(nodes)
        self.assertEqual(len(rows), 1)
        self.assertIn("['sfx_exhaust_02']", rows[0]["message"])

    def test_point_sources_on_empties_are_clean(self):
        listed = {"part_exhaust_small_cars": {"emitters2": {"Smoke_Flow_2": {
            "emission": {"source": {"__type": "local__point"}}}}}, "part_radiator_haze": {}}
        nodes = model([("sfx_exhaust_01", False, None), ("sfx_radiator_haze", True, None)])
        self.assertEqual(lint(nodes, listed), [])

    def test_unknown_bounds_skip_the_check(self):
        nodes = model([("sfx_exhaust_01", False, None), ("sfx_radiator_haze", False, None)], bounds=False)
        self.assertEqual(lint(nodes), [])


def vfx(*bones):
    return {"vfxSkeleton": {"vfxBones": list(bones), "__type": "vfx_skel"}}


def cylinder(name="wheel", rotation=None, bone="_wheel"):
    entry = {"name": name, "bone": bone, "geom": {"cylinder": {"height": 0.7, "radius": 0.85},
                                                  "__type": "local__cylinder"}, "systems": 18}
    if rotation is not None:
        entry["boneRotation"] = rotation
    return entry


SHADOW = {"name": "shadow", "geom": {"capsuleScaled": {"radius": 0.6}, "__type": "local__capsuleScaled"}}


class WheelVfxAxisTests(unittest.TestCase):
    def wheel(self, frame):
        return model([("_wheel", False, frame), ("rim", True, None), ("tire", True, None)])

    def test_identity_frame_without_rotation_lies_fore_aft(self):
        # Grader 16M3, 994 loader, Goliath D11 as installed.
        rows = bro_lint.wheel_vfx_findings(vfx(cylinder(), cylinder("wheel_grass"), SHADOW), self.wheel(IDENTITY))
        self.assertEqual([(f["code"], f["severity"], f["where"]) for f in rows],
                         [("RC028", "warning", "propVFX.vfxSkeleton.vfxBones[0]"),
                          ("RC028", "warning", "propVFX.vfxSkeleton.vfxBones[1]")])
        self.assertIn("+Z (fore-aft)", rows[0]["message"])
        self.assertIn("[90, 0, 90]", rows[0]["message"])

    def test_sdk_identity_frame_with_90_0_90_is_clean(self):
        bones = vfx(cylinder(rotation=[90, 0, 90]), cylinder("wheel_grass_affect", [90, 0, 90]))
        self.assertEqual(bro_lint.wheel_vfx_findings(bones, self.wheel(IDENTITY)), [])

    def test_retail_frame_without_rotation_is_clean(self):
        # Retail wheels and Kanga 25 c6 (frame rotated, BRO rotation dropped).
        self.assertEqual(bro_lint.wheel_vfx_findings(vfx(cylinder()), self.wheel(RETAIL_WHEEL)), [])

    def test_retail_frame_keeping_90_0_90_is_flagged(self):
        rows = bro_lint.wheel_vfx_findings(vfx(cylinder(rotation=[90, 0, 90])), self.wheel(RETAIL_WHEEL))
        self.assertEqual([f["code"] for f in rows], ["RC028"])
        self.assertIn("drop its boneRotation", rows[0]["message"])

    def test_other_bones_and_models_without_wheel_frame_are_skipped(self):
        self.assertEqual(bro_lint.wheel_vfx_findings(vfx(cylinder(bone="rim")), self.wheel(IDENTITY)), [])
        self.assertEqual(bro_lint.wheel_vfx_findings(vfx(cylinder()), model([("rim", True, None)])), [])
        self.assertEqual(bro_lint.wheel_vfx_findings(vfx(cylinder()), ["_wheel", "rim"]), [])


SFX = 'nameParent = "sfx_exhaust_*"\nemitters2 = { Smoke_Flow_2 = { emission = { source = { __type = "local__parentArea" } } } }\n'
STARTS = ('prop_blueprints = { blueprints = { SFX = { nodes = { A = { vfxUidRef = { def = "part_exhaust_small_cars" '
          '__type = "SfxStringRefParam" } __type = "BlueprintNodeVfxRestart" } } } } }\n'
          'sfx = { list = { part_exhaust_small_cars = { } } }')


class ValidateWiringTests(Base):
    """``roadcraft validate`` runs the checks on compiled classes (installed paks carry no BROs)."""

    def truck(self, extra_nodes):
        slots, nodes = four_wheels()
        nodes.update(extra_nodes)
        return {"ssl/truck.cls": truck_cls(slots, blueprints=STARTS), "ssl/sfx/part_exhaust_small_cars.sfx": SFX,
                "models/mods/t.tpl.asset/tpl/t.tpl": tpl_bytes(nodes)}

    def test_compiled_truck_class_effect_without_node(self):
        found = [f for f in self.fixture(self.truck({})).run(rules=["bro-lint"]) if f.code == "RC025"]
        self.assertEqual([(f.severity, f.key) for f in found], [("error", "properties.sfx.list.part_exhaust_small_cars")])
        self.assertTrue(found[0].evidence.startswith("lint-bro RC025"))

    def test_compiled_truck_class_with_the_node_is_clean(self):
        found = self.fixture(self.truck({"sfx_exhaust_01": matrix()})).run(rules=["bro-lint"])
        self.assertNotIn("RC025", codes(found))

    def wheel(self, rotation):
        rot = f"boneRotation = [ {', '.join(map(str, rotation))} ]" if rotation else ""
        cls = ('properties = {\n prop_truck_wheel = { width = 0.5 }\n geom = { nameTpl = "wm" }\n vfx = { vfxSkeleton = { '
               f'vfxBones = [ {{ name = "wheel" bone = "_wheel" {rot} geom = {{ cylinder = {{ height = 0.7 radius = 0.85 }} '
               '__type = "local__cylinder" } systems = 18 } ] __type = "vfx_skel" } }\n}\n__type = "truck_wheel"\n')
        return {"ssl/auto_wheel_t_w.cls": cls,
                "models/mods/wm.tpl.asset/tpl/wm.tpl": tpl_bytes({"_wheel": matrix(), "rim": matrix()})}

    def test_compiled_wheel_class_cylinder_fore_aft(self):
        found = [f for f in self.fixture(self.wheel(None)).run(rules=["bro-lint"]) if f.code == "RC028"]
        self.assertEqual([(f.severity, f.key) for f in found], [("warning", "properties.vfx.vfxSkeleton.vfxBones[0]")])

    def test_compiled_wheel_class_sdk_pair_is_clean(self):
        self.assertNotIn("RC028", codes(self.fixture(self.wheel([90, 0, 90])).run(rules=["bro-lint"])))


if __name__ == "__main__":
    unittest.main()
