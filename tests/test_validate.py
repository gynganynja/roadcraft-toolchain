"""roadcraft.validate: one synthetic fixture per rule (positive and negative), pak reading, the CLI contract,
and SDK-gated integration tests on the SDK's own TUZ sample (skipped, with the reason, without an install)."""

import contextlib
import dataclasses
import io
import json
import struct
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path

from roadcraft import schema, validate

META_DESC = """
iactor = { __family = ".cls" __type = "section"
   __members = { properties = { __type = "exclusiveCollection" __ptr = "prop_base" __family = ".prop" } } }
prop_base = { __family = ".prop" __type = "section" }
geom = { __family = ".prop" __type = "prop_base" __members = { nameTpl = { __type = "string" } } }
tpl_markup = { __family = ".tpl_markup" __type = "section"
   __members = { version = { __type = "int" } materials = { __type = "collection" } objectInfos = { __type = "array" } } }
"""
META_DESC_SSL = """
PropTruckWheel = { __type = "section"
   __extraData = { __sslBrandName = "prop_truck_wheel" __sslBrandFamily = ".prop" }
   __members = {
      width = { __type = "float" __defaultValue = 1 __viewType = { __min = 0 __max = 5 __units = "m" } }
      torqueType = { __type = "TorqueType" }
      rimObjName = { __type = "string" __defaultValue = "rim" }
   } }
TorqueType = { __type = "enum" __items = [ "none", "defaults", "full" ] __defaultValue = "none" }
WheelParticleMaterialSettings = { __type = "section"
   __members = { spreadAngleProb = { __type = "float" } baseDepth = { __type = "float" } } }
TrackParticleMaterialSettings = { __type = "section"
   __members = { spreadAngle = { __type = "float" } bottomSpreadAngle = { __type = "float" } } }
PropWheelParticlesBase = { __type = "section"
   __extraData = { __sslBrandName = "prop_wheel_particles_base" __sslBrandFamily = ".prop" }
   __members = {
      wheelSettings = { __type = "WheelParticleMaterialSettings" }
      trackSettings = { __type = "TrackParticleMaterialSettings" }
   } }
"""


def make_sdk(root: Path) -> Path:
    meta = root / "root" / "prebuild" / "meta_descs"
    meta.mkdir(parents=True)
    (meta / "meta_desc.ps").write_text(META_DESC, encoding="utf-8")
    (meta / "meta_desc_ssl.ps").write_text(META_DESC_SSL, encoding="utf-8")
    (meta / "meta_desc_bro.ps").write_text("", encoding="utf-8")
    return root


def matrix(x=0.0, y=0.0, z=0.0, mirror=False):
    return (-1.0 if mirror else 1.0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, x, y, z, 1)


def tpl_bytes(nodes):
    """A compiled-model node table (tpl_reader layout): names, indices, world matrices."""
    names = list(nodes)
    table = struct.pack("<IB", len(names), 1)
    for name in names:
        table += struct.pack("<I", len(name)) + name.encode()
    table += struct.pack("<I", len(names)) + struct.pack(f"<{len(names)}H", *range(len(names)))
    table += struct.pack("<I", len(names))
    for name in names:
        table += struct.pack("<16f", *nodes[name])
    return b"\x07" * 16 + table + b"\x00" * 8


SLOT = '{{ geomName = "{g}" {right} editableWheel = "W" suspensionCollectionAxleIndex = {i} {extra} }}'


def truck_cls(slots, *, collection=True, lights="", blueprints="", tpl="t", extra_rb=""):
    coll = "suspensionAxleCollection = [ { min = -0.1 max = 0.2 strength = 0.02 } ]" if collection else ""
    return (f'properties = {{\n geom = {{ nameTpl = "{tpl}" }}\n prop_truck_rb = {{\n  {coll}\n'
            f'  wheelSlotWithDescs = [ {" ".join(slots)} ]\n  wheelPool = {{ W = {{ __value = "w" }} }}\n {extra_rb} }}\n'
            f' {lights}\n {blueprints}\n}}\n__type = "truck_view"\n')


WHEEL_CLS = 'properties = {\n prop_truck_wheel = { deformEnable = True }\n geom = { nameTpl = "wm" }\n}\n'


class Fixture:
    """A mod source tree in a temporary folder."""

    def __init__(self, files: dict[str, str | bytes]) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "p"
        for name, data in files.items():
            path = self.root / "mods_source" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
        self.game = Path(self.tmp.name) / "game"
        self.game.mkdir()

    def run(self, rules=None, sdk=False, **kwargs):
        if sdk and not (self.game / "root").exists():
            make_sdk(self.game)
        kwargs.setdefault("read_fields", validate.ReadFields())    # built-in RC072 cases only: no data-file drift
        return validate.validate(self.root, rules=rules, game_root=self.game, **kwargs)

    def close(self):
        self.tmp.cleanup()


def codes(findings):
    return sorted(f.code for f in findings)


def four_wheels(right_flags=(False, True, False, True), xs=(0.8, -0.8, 0.8, -0.8), extra=("", "", "", "")):
    names = ["FL", "FR", "RL", "RR"]
    slots = [SLOT.format(g=n, right="isRightSided = True" if r else "", i=0, extra=e)
             for n, r, e in zip(names, right_flags, extra)]
    nodes = {"BoneChassis_cdt": matrix()}
    nodes.update({n: matrix(x, 0.4, 1.0) for n, x in zip(names, xs)})
    return slots, nodes


class Base(unittest.TestCase):
    def fixture(self, files):
        fx = Fixture(files)
        self.addCleanup(fx.close)
        return fx


class PsNumberTests(Base):
    def test_exponent_leading_dot_bare_word_and_parse_error(self) -> None:
        fx = self.fixture({"ssl/a.cls": "a = [1e-05]\nb = .5\nc = no\n", "ssl/b.cls": "x = 1e-05\n",
                           "ssl/ok.cls": "a = 0.5\nb = True\nc = \"no\"\n"})
        found = fx.run(rules=["ps-numbers", "ps-parse"])
        self.assertEqual(codes(found), ["RC049", "RC050", "RC050", "RC051", "RC052"])
        by = {f.code: f for f in found if f.path.endswith("a.cls")}
        self.assertEqual((by["RC050"].line, by["RC051"].line, by["RC052"].line), (1, 2, 3))
        self.assertIn("0.0", by["RC051"].message)
        self.assertFalse([f for f in found if f.path.endswith("ok.cls")])


class UnknownKeyTests(Base):
    def test_unknown_key_enum_and_type_errors_show_defaults(self) -> None:
        fx = self.fixture({"ssl/w.cls": 'properties = {\n prop_truck_wheel = {\n  widht = 2\n  torqueType = "default"\n'
                                        '  rimObjName = yes\n  width = 9\n }\n prop_missing = { }\n}\n'})
        found = {f.code: f for f in fx.run(rules=["unknown-keys"], sdk=True)}
        self.assertEqual(sorted(found), ["RC053", "RC054", "RC055", "RC056", "RC057"])
        self.assertIn("did you mean 'width'", found["RC053"].message)
        self.assertEqual(found["RC053"].key, "properties.prop_truck_wheel.widht")
        self.assertEqual(found["RC053"].line, 3)
        self.assertIn("schema default 'none'", found["RC055"].message)
        self.assertIn("did you mean 'defaults'", found["RC055"].message)
        self.assertIn("schema default 'rim'", found["RC056"].message)
        self.assertEqual(found["RC057"].severity, "info")
        self.assertEqual(found["RC054"].key, "properties.prop_missing")

    def test_clean_class(self) -> None:
        fx = self.fixture({"ssl/w.cls": 'properties = {\n prop_truck_wheel = { width = 2 torqueType = "full" }\n'
                                        ' geom = { nameTpl = "x" }\n}\n'})
        self.assertEqual(fx.run(rules=["unknown-keys"], sdk=True), [])

    def test_read_fields_hook(self) -> None:
        fx = self.fixture({"ssl/w.cls": 'properties = { prop_truck_wheel = { width = 2 rimObjName = "rim" } }\n'})
        found = fx.run(rules=["ignored-fields"], sdk=True, read_fields={".prop::prop_truck_wheel": ["width"]})
        self.assertEqual([(f.code, f.key) for f in found], [("RC072", "properties.prop_truck_wheel.rimObjName")])


class WheelFrameTests(Base):
    def files(self, slots, nodes, wheel_nodes=None, **kw):
        return {"ssl/truck.cls": truck_cls(slots, **kw), "ssl/w.cls": WHEEL_CLS,
                "models/mods/t.tpl.asset/tpl/t.tpl": tpl_bytes(nodes),
                "models/mods/wm.tpl.asset/tpl/wm.tpl": tpl_bytes(wheel_nodes or {"rim": matrix(), "tire_vis": matrix()})}

    def test_consistent_retail_shaped_truck_is_clean(self) -> None:
        slots, nodes = four_wheels()
        self.assertEqual(self.fixture(self.files(slots, nodes)).run(rules=["wheel-frames", "suspension"]), [])

    def test_mixed_sides_mirror_missing_node_and_knuckle(self) -> None:
        slots, nodes = four_wheels(right_flags=(False, True, True, True),
                                   extra=('customSteeringJointObjName = "KFL"', "", "", 'parentFrame = "Nope"'))
        nodes["RL"] = matrix(0.8, 0.4, -1.0, mirror=True)
        nodes["KFL"] = matrix(1.1, 0.4, 1.0)
        found = self.fixture(self.files(slots, nodes)).run(rules=["wheel-frames"])
        self.assertEqual(codes(found), ["RC058", "RC059", "RC060", "RC061"])
        self.assertIn("'RL'", next(f.message for f in found if f.code == "RC060"))

    def test_deformable_tyre_needs_a_tire_object(self) -> None:
        slots, nodes = four_wheels()
        found = self.fixture(self.files(slots, nodes, wheel_nodes={"rim": matrix(), "tyre": matrix()})).run(
            rules=["wheel-frames"])
        self.assertEqual(set(codes(found)), {"RC062"})


class SuspensionTests(Base):
    def test_missing_collection_and_bad_index(self) -> None:
        slots, nodes = four_wheels()
        fx = self.fixture({"ssl/a.cls": truck_cls(slots, collection=False)})
        self.assertEqual(codes(fx.run(rules=["suspension"])), ["RC063"])
        bad = [s.replace("suspensionCollectionAxleIndex = 0", "suspensionCollectionAxleIndex = 3") for s in slots]
        fx = self.fixture({"ssl/a.cls": truck_cls(bad)})
        self.assertEqual(len(fx.run(rules=["suspension"])), 4)
        fx = self.fixture({"ssl/a.cls": truck_cls(slots, collection=False, extra_rb="suspensionSet = { a = 1 }")})
        self.assertEqual(fx.run(rules=["suspension"]), [])

    def test_bro_without_use_suspension_collection(self) -> None:
        bro = ('tpl = "t"\ntruckSettings = {\n suspensionCollection = { Front = { strength = 0.02 height = 0.1 } }\n'
               ' maxSteerSpeed = 0.03\n backSteerSpeed = 0.06\n pedalsResponsiveness = 0.35\n}\n')
        found = self.fixture({"bro/trucks/t.bro": bro}).run(rules=["bro-lint"])
        self.assertIn("RC001", codes(found))
        fixed = bro.replace("truckSettings = {", "truckSettings = {\n useSuspensionCollection = True")
        self.assertNotIn("RC001", codes(self.fixture({"bro/trucks/t.bro": fixed}).run(rules=["bro-lint"])))


MARKUP_JOINTS = """version = 1
objectInfos = [
 { objectId = { name = "Arm_cdt" } entities = [ { __type = "tpl_markup_constraint_prismatic" isMinLimit = True minLimit = 0.2 } ] }
 { objectId = { name = "Boom_cdt" } entities = [ { __type = "tpl_markup_constraint_hinge" target = "Ghost" limited = True angleStart = -10 angleEnd = 40 } ] }
 { objectId = { name = "Cab_cdt" } entities = [ { __type = "tpl_markup_constraint_six_dof" angularX = { mode = "FIXED" } } ] }
 { objectId = { name = "Lid_cdt" } entities = [ { __type = "tpl_markup_constraint_hinge" limited = True angleStart = 0 angleEnd = 90 } ] }
]
"""


class JointTests(Base):
    def test_unreachable_limits_missing_target_combo_and_mirrored_frame(self) -> None:
        nodes = {"BoneChassis_cdt": matrix(), "Arm_cdt": matrix(), "Boom_cdt": matrix(), "Cab_cdt": matrix(),
                 "Lid_cdt": matrix(mirror=True)}
        fx = self.fixture({"models/mods/m.tpl.asset/m.tpl_markup": MARKUP_JOINTS,
                           "models/mods/m.tpl.asset/tpl/m.tpl": tpl_bytes(nodes)})
        found = fx.run(rules=["joints"])
        self.assertEqual(codes(found), ["RC064", "RC064", "RC065", "RC065"])
        self.assertTrue(all(f.line for f in found))

    def test_clean_markup(self) -> None:
        clean = MARKUP_JOINTS.replace("minLimit = 0.2", "minLimit = -0.2").replace('target = "Ghost"', "") \
            .replace('angularX = { mode = "FIXED" }', 'angularX = { mode = "FIXED" } angularY = { mode = "FIXED" }')
        nodes = {n: matrix() for n in ("BoneChassis_cdt", "Arm_cdt", "Boom_cdt", "Cab_cdt", "Lid_cdt")}
        fx = self.fixture({"models/mods/m.tpl.asset/m.tpl_markup": clean,
                           "models/mods/m.tpl.asset/tpl/m.tpl": tpl_bytes(nodes)})
        self.assertEqual(fx.run(rules=["joints"]), [])


def spring_markup(child_mass, k, c, *, parent_mass=44000, target='target = "BoneChassis_cdt"',
                  joint="tpl_markup_constraint_prismatic", density=""):
    return (f'version = 1\nobjectInfos = [\n'
            f' {{ objectId = {{ name = "BoneChassis_cdt" }} properties = [ {{ mass = {parent_mass} '
            f'__type = "tpl_markup_object_property_physics" }} ] }}\n'
            f' {{ objectId = {{ name = "BoneSuspRear_cdt" }} properties = [ {{ mass = {child_mass} {density} '
            f'__type = "tpl_markup_object_property_physics" }} ]\n'
            f'   entities = [ {{ __type = "{joint}" {target} isMinLimit = True minLimit = -0.27 isMaxLimit = True '
            f'maxLimit = 0.22 motor = {{ spring = {k} damping = {c} __type = "tpl_markup_spring_motor" }} }} ] }}\n]\n')


class SpringMotorTests(Base):
    """RC076: per-step solver numbers k*dt^2/m_eff and c*dt/m_eff of load-bearing prismatic spring motors."""

    def run_markup(self, markup, tpl=None):
        nodes = {"BoneChassis_cdt": matrix(), "BoneSuspRear_cdt": matrix(0, 1, -2)}
        fx = self.fixture({"models/mods/m.tpl.asset/m.tpl_markup": markup,
                           "models/mods/m.tpl.asset/tpl/m.tpl": tpl or tpl_bytes(nodes)})
        return fx.run(rules=["spring-motors"])

    def test_mammoth_rc62_rear_heave_is_clamped(self) -> None:
        found = self.run_markup(spring_markup(4000, 11300000, 880000))
        self.assertEqual(codes(found), ["RC076"])
        self.assertEqual(found[0].severity, "warning")
        self.assertIn("damping is clamped to 1", found[0].message)
        self.assertIn("2.2e+05", found[0].message)            # m_eff/dt = 3667 kg x 60
        self.assertTrue(found[0].line)
        self.assertIn("damping <=", found[0].fixHint)

    def test_mammoth_rc62_front_is_beyond_retail_but_not_clamped(self) -> None:
        found = self.run_markup(spring_markup(6000, 3510000, 271000))
        self.assertEqual(codes(found), ["RC076"])
        self.assertIn("not clamped", found[0].message)

    def test_retail_lynx_frame_and_light_props_are_clean(self) -> None:
        self.assertEqual(self.run_markup(spring_markup(500, 300000, 12000, parent_mass=1700)), [])
        self.assertEqual(self.run_markup(spring_markup(30, 5000, 2500, parent_mass=1700)), [])     # Lynx balloon
        self.assertEqual(self.run_markup(spring_markup(4000, 11300000, 880000, density="massFromDensity = True")), [])

    def test_hinge_springs_are_not_checked(self) -> None:
        self.assertEqual(self.run_markup(spring_markup(4000, 11300000, 880000, joint="tpl_markup_constraint_hinge")),
                         [])

    def test_parent_target_resolved_through_the_model_tree(self) -> None:
        nodes = {"BoneChassis_cdt": matrix(), "BoneSuspRear_cdt": matrix(0, 1, -2), "cdt_rear": matrix(0, 1, -2)}
        data = tpl_bytes(nodes)
        tree = struct.pack("<3h", -1, 0, 1) + data[6:]        # parent array in the padding: root, chassis, susp
        self.assertEqual(codes(self.run_markup(spring_markup(4000, 11300000, 880000, target=""), tree)), ["RC076"])
        self.assertEqual(self.run_markup(spring_markup(4000, 11300000, 880000, target=""), data), [])  # no tree: skip


LIGHTS = ('prop_vehicle_lights_material = { lights = { "0" = { defaultName = "default" lightName = "lights_emissive" '
          'geomNames = [ "marker_lights" ] __type = "Headlights" } } }')


def lamp_markup(state="lights_emissive", lit="lamp_on", hidden=""):
    return (f'version = 1\nmaterials = {{\n body = {{ materialName = "body" dynamicMaterials = {{ default = {{ materialName '
            f'= "body" }} {state} = {{ materialName = "{lit}" }} }} }}\n}}\n'
            + (f'objSettings = {{ settings = {{ {hidden} = {{ visibility = {{ visibleDefault = False }} }} }} }}\n'
               if hidden else ""))


class LampTests(Base):
    def files(self, markup, extra=None):
        slots, nodes = four_wheels()
        nodes["marker_lights"] = matrix()
        files = {"ssl/truck.cls": truck_cls(slots, lights=LIGHTS), "ssl/w.cls": WHEEL_CLS,
                 "models/mods/t.tpl.asset/t.tpl_markup": markup,
                 "models/mods/t.tpl.asset/tpl/t.tpl": tpl_bytes(nodes)}
        files.update(extra or {})
        return files

    def test_misspelt_state_identical_materials_and_markup_hidden_lamp(self) -> None:
        found = self.fixture(self.files(lamp_markup(state="lights_emmissive"))).run(rules=["lamps"])
        self.assertEqual(codes(found), ["RC066", "RC066"])     # the lamp's missing state, and the misspelt slot state
        self.assertEqual(sorted(f.key for f in found), ["materials.body.dynamicMaterials.lights_emmissive",
                                                        "properties.prop_vehicle_lights_material.lights.0.lightName"])
        found = self.fixture(self.files(lamp_markup(lit="body"))).run(rules=["lamps"])
        self.assertEqual(codes(found), ["RC067"])
        found = self.fixture(self.files(lamp_markup(hidden="marker_lights"))).run(rules=["lamps"])
        self.assertEqual(codes(found), ["RC068"])

    def test_identical_beacon_states_and_clean_lamp(self) -> None:
        beacon = lamp_markup().replace("default = {", 'd11_beacon_on = { materialName = "x" } '
                                                     'd11_beacon_off = { materialName = "x" } default = {')
        found = self.fixture(self.files(beacon)).run(rules=["lamps"])
        self.assertEqual([(f.code, f.severity) for f in found], [("RC067", "warning")])
        self.assertEqual(self.fixture(self.files(lamp_markup())).run(rules=["lamps"]), [])


class StatePairTests(Base):
    def markup(self, real_slot: bool) -> str:
        noop = ('{n} = {{ materialName = "{n}" dynamicMaterials = {{ d11_beacon_on = {{ materialName = "{n}" }} '
                'd11_beacon_off = {{ materialName = "{n}" }} }} }}')
        slots = [noop.format(n=f"body{i}") for i in range(3)]
        if real_slot:
            slots.append('beacon = { materialName = "beacon_off" dynamicMaterials = { d11_beacon_on = { materialName '
                         '= "beacon_on" } d11_beacon_off = { materialName = "beacon_off" } } }')
        return "version = 1\nmaterials = {\n " + "\n ".join(slots) + "\n}\n"

    def test_no_op_slots_are_ignored_when_one_slot_differs(self) -> None:
        fx = self.fixture({"models/mods/m.tpl.asset/m.tpl_markup": self.markup(real_slot=True)})
        self.assertEqual(fx.run(rules=["lamps"]), [])

    def test_fires_when_no_slot_of_the_pair_differs(self) -> None:
        found = self.fixture({"models/mods/m.tpl.asset/m.tpl_markup": self.markup(real_slot=False)}).run(rules=["lamps"])
        self.assertEqual([(f.code, f.severity) for f in found], [("RC067", "warning")])
        self.assertIn("can never be seen", found[0].message)


class MaterialAndReferenceTests(Base):
    def test_merge_materials_and_one_material_per_texture(self) -> None:
        markup = ('version = 1\nmaterials = {\n glass = { materialName = "glass" }\n lamps = { materialName = "lamps" }\n}\n')
        obj_list = json.dumps({"engine_objects": {"name": "root", "material_info": [], "children": [
            {"name": "Glass", "material_info": [{"maya_name": "lamps"}], "children": []}]}})
        fx = self.fixture({
            "models/mods/m.tpl.asset/m.tpl_markup": markup,
            "models/mods/m.tpl.asset/tpl/obj_list.json": obj_list,
            "models/mods/m.tpl.asset/export_options.ps": "options = { advanced = { merge_materials = True } }\n",
            "material_instances/glass.mi": 'shaders = { glt_shader = { base = { params = { texDiff = "atlas" } } } }\n'
                                           '__type = "vehicle_glass_outer"\n',
            "material_instances/lamps.mi": 'shaders = { glt_shader = { base = { params = { texDiff = "atlas" } } } }\n'
                                           '__type = "vehicle_body"\n'})
        found = fx.run(rules=["materials"])
        self.assertEqual(codes(found), ["RC069", "RC069"])
        self.assertTrue(any("'glass'" in f.message and "'lamps'" in f.message for f in found))

    def test_missing_material_texture_and_link(self) -> None:
        fx = self.fixture({
            "models/mods/m.tpl.asset/m.tpl_markup": 'materials = { a = { materialName = "gone" } b = { materialName = "here" } }\n',
            "material_instances/here.mi": 'shaders = { glt_shader = { base = { params = { texDiff = "tex_here" texNM = "tex_gone" } } } }\n',
            "material_instances/here.mi.resource": "__type: res_desc_mtl\nfile: here.mi\nlinks:\n- res://pct/tex_here.pct.resource\n"
                                                   "- res://pct/nowhere.pct.resource\n",
            "pct/tex_here.pct.resource": "__type: res_desc_pct\n",
            "m.mod": "title: m\nassets:\n- ssl/missing.cls.resource\n"})
        found = fx.run(rules=["references"])
        self.assertEqual(codes(found), ["RC070"] * 4)
        keys = sorted(f.key for f in found)
        self.assertEqual(keys, ["assets[0]", "links[1]", "materials.a.materialName", "texNM"])


MI_BODY = 'shaders = { glt_shader = { base = { params = { texDiff = "t" } } } }\n'


class MaterialTypeTests(Base):
    """RC078: a .mi without a known __type crashes retail at the main menu (retail_crash_0x214f223.md)."""

    def run_mi(self, files, retail_presets=("vehicle_body", "vehicle_lights")):
        fx = self.fixture(files)
        if retail_presets is not None:
            pak = fx.game / "root" / "paks" / "client" / "default" / "default_materials.pak"
            pak.parent.mkdir(parents=True)
            with zipfile.ZipFile(pak, "w") as archive:
                archive.writestr("master_materials/glt_extended_material.mm", "")
                for name in retail_presets:
                    archive.writestr(f"material_presets/{name}.mp", '__type = "glt_extended_material"\n')
        notes = []
        return fx.run(rules=["material-type"], notes=notes), notes

    def test_missing_empty_unknown_and_valid(self) -> None:
        found, _ = self.run_mi({
            "material_instances/none.mi": MI_BODY,
            "material_instances/none.mi.resource": "__type: res_desc_mtl\nfile: none.mi\nparents:\n"
                                                   "- res://material_presets/vehicle_lights.mp.resource\n",
            "material_instances/empty.mi": MI_BODY + '__type = ""\n',
            "material_instances/unknown.mi": MI_BODY + '__type = "vehicle_bodyy"\n',
            "material_instances/ok.mi": MI_BODY + '__type = "vehicle_body"\n',
            "material_instances/master.mi": MI_BODY + '__type = "glt_extended_material"\n',
            "material_instances/own.mi": MI_BODY + '__type = "my_preset"\n',
            "material_presets/my_preset.mp": '__type = "glt_extended_material"\n'})
        by_file = {f.member.rsplit("/", 1)[-1]: f for f in found}
        self.assertEqual(sorted(by_file), ["empty.mi", "none.mi", "unknown.mi"])
        self.assertTrue(all(f.code == "RC078" and f.severity == "error" for f in found))
        self.assertIn("no message", by_file["none.mi"].message)
        self.assertIn('__type = "vehicle_lights"', by_file["none.mi"].fixHint)
        self.assertIn('"vehicle_body"', by_file["unknown.mi"].fixHint)
        self.assertEqual(by_file["empty.mi"].line, 2)

    def test_unparsable_mi_falls_back_to_the_raw_line(self) -> None:
        found, _ = self.run_mi({"material_instances/bad.mi": "shaders = {\n__type = \"vehicle_body\"\n",
                                "material_instances/bad2.mi": "shaders = {\n"})
        self.assertEqual([f.member.rsplit("/", 1)[-1] for f in found], ["bad2.mi"])

    def test_without_retail_only_missing_type_is_checked(self) -> None:
        found, notes = self.run_mi({"material_instances/a.mi": MI_BODY + '__type = "anything"\n',
                                    "material_instances/b.mi": MI_BODY}, retail_presets=None)
        self.assertEqual([f.member for f in found], ["material_instances/b.mi"])
        self.assertTrue(any("RC078" in n for n in notes))

    def test_pak_members(self) -> None:
        fx = self.fixture({})
        fx.game.joinpath("root", "paks", "client").mkdir(parents=True)
        with zipfile.ZipFile(fx.game / "root" / "paks" / "client" / "m.pak", "w") as archive:
            archive.writestr("material_presets/vehicle_body.mp", "")
        pak = Path(fx.tmp.name) / "mod.pak"
        with zipfile.ZipFile(pak, "w") as archive:
            archive.writestr("material_instances/beacon.mi", MI_BODY)
            archive.writestr("material_instances/body.mi", MI_BODY + '__type = "vehicle_body"\n')
        found = validate.validate(pak, rules=["material-type"], game_root=fx.game)
        self.assertEqual([(f.code, f.path) for f in found], [("RC078", "mod.pak!material_instances/beacon.mi")])


class PakTests(Base):
    def make_pak(self, members):
        path = Path(tempfile.mkdtemp()) / "mod.pak"
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with zipfile.ZipFile(path, "w") as archive:
                for name, data in members:
                    archive.writestr(name, data)
        return path

    def test_duplicates_and_in_memory_rules(self) -> None:
        same = "version = 1\n"
        pak = self.make_pak([("models/mods/m.tpl.asset/m.tpl_markup", same), ("models/mods/m.tpl.asset/m.tpl_markup", same),
                             ("ssl/a.cls", "x = .5\n"), ("ssl/a.cls", "x = 0.5\n")])
        found = validate.validate(pak, rules=["duplicates", "ps-numbers"], game_root=Path(tempfile.gettempdir()) / "none")
        self.assertEqual(codes(found), ["RC051", "RC071"])
        self.assertTrue(found[0].path.startswith("mod.pak!"))

    def test_cli_json_and_exit_codes(self) -> None:
        pak = self.make_pak([("ssl/a.cls", "x = .5\n")])
        none = str(Path(tempfile.gettempdir()) / "no_game_here")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(validate.main([str(pak), "--json", "--game-root", none]), 1)
        report = json.loads(out.getvalue())
        self.assertEqual(report["counts"]["error"], 1)
        self.assertEqual(report["findings"][0]["code"], "RC051")
        self.assertTrue(report["notes"])
        clean = self.make_pak([("ssl/a.cls", "x = 0.5\n")])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(validate.main([str(clean), "--game-root", none]), 0)
            self.assertEqual(validate.main([str(pak), "--fail-on", "error", "--rules", "duplicates",
                                            "--game-root", none]), 0)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(validate.main([str(pak), "--rules", "nope", "--game-root", none]), 2)
            self.assertEqual(validate.main([str(Path(none) / "missing.pak"), "--game-root", none]), 2)


PARTICLES_CLS = ('properties = {\n prop_wheel_particles_base = {\n  wheelSettings = { spreadAngle = 3 spreadAngleProb = 1 }\n'
                 '  trackSettings = { spreadAngle = 2 }\n }\n}\n')
NO_GAME = str(Path(tempfile.gettempdir()) / "no_game_here")


class PakBase(Base):
    def make_pak(self, members, name="mod.pak"):
        folder = Path(tempfile.mkdtemp())
        path = folder / name
        self.addCleanup(lambda: (path.unlink(missing_ok=True), folder.rmdir()))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with zipfile.ZipFile(path, "w") as archive:
                for member, data in members:
                    archive.writestr(member, data)
        return path

    def cli(self, argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = validate.main(argv)
        return code, out.getvalue()


class FindingIdTests(PakBase):
    def test_id_ignores_line_shifts_and_the_pak_or_tree_prefix(self) -> None:
        text = 'properties = {\n prop_truck_wheel = {\n  widht = 2\n }\n}\n'
        first = self.fixture({"ssl/w.cls": text}).run(rules=["unknown-keys"], sdk=True)
        shifted = self.fixture({"ssl/w.cls": "\n\n\n" + text}).run(rules=["unknown-keys"], sdk=True)
        self.assertEqual(len(first), 1)
        self.assertNotEqual(first[0].line, shifted[0].line)
        self.assertEqual(first[0].id, shifted[0].id)
        self.assertEqual(first[0].id, validate.finding_id("RC053", "ssl/w.cls", "properties.prop_truck_wheel.widht"))
        self.assertEqual(first[0].member, "ssl/w.cls")
        pak = self.make_pak([("ssl/w.cls", text)], name="other_name.pak")
        fx = self.fixture({})
        make_sdk(fx.game)
        from_pak = validate.validate(pak, rules=["unknown-keys"], game_root=fx.game)
        self.assertEqual([f.id for f in from_pak], [first[0].id])

    def test_same_code_and_key_get_ordinal_suffixes_that_survive_shifts(self) -> None:
        a = self.fixture({"ssl/a.cls": "x = .5\ny = .25\n"}).run(rules=["ps-numbers"])
        b = self.fixture({"ssl/a.cls": "\n\nx = .5\n\ny = .25\n"}).run(rules=["ps-numbers"])
        self.assertEqual(len({f.id for f in a}), 2)
        self.assertEqual(sorted(f.id for f in a), sorted(f.id for f in b))


class BaselineTests(PakBase):
    def test_new_fixed_unchanged_and_exit_on_new_only(self) -> None:
        old = self.make_pak([("ssl/a.cls", "x = .5\n"), ("ssl/b.cls", "y = .5\n")], name="old.pak")
        new = self.make_pak([("ssl/a.cls", "\nx = .5\n"), ("ssl/c.cls", "z = .5\n")], name="new.pak")
        code, out = self.cli([str(new), "--baseline", str(old), "--json", "--game-root", NO_GAME,
                              "--rules", "ps-numbers"])
        self.assertEqual(code, 1)                                   # c.cls is a new error
        report = json.loads(out)
        self.assertEqual(report["baseline"]["counts"], {"new": 1, "unchanged": 1, "fixed": 1})
        status = {f["member"]: f["status"] for f in report["findings"]}
        self.assertEqual(status, {"ssl/a.cls": "unchanged", "ssl/c.cls": "new"})
        self.assertEqual([f["member"] for f in report["baseline"]["fixed"]], ["ssl/b.cls"])
        # the same errors with nothing new: exit 0 although errors remain
        code, out = self.cli([str(old), "--baseline", str(old), "--json", "--game-root", NO_GAME])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["baseline"]["counts"], {"new": 0, "unchanged": 2, "fixed": 0})
        code, out = self.cli([str(new), "--baseline", str(old), "--game-root", NO_GAME])
        self.assertIn("1 new, 1 fixed, 1 unchanged", out)


class GroupingAndExitTests(PakBase):
    def test_groups_normalise_indices_and_cap_locations(self) -> None:
        fx = self.fixture({"ssl/w.cls": f"properties = {{\n prop_truck_wheel = {{ widht = 1 }}\n}}\n",
                           "ssl/v.cls": f"properties = {{\n prop_truck_wheel = {{ widht = 1 }}\n}}\n"})
        found = fx.run(rules=["unknown-keys"], sdk=True)
        findings = [dataclasses.replace(found[0], key=f"list[{i}].widht", id=str(i)) for i in range(5)] + found
        groups = validate.group_findings(findings)
        by_key = {g["keyPattern"]: g for g in groups}
        self.assertEqual(by_key["list[].widht"]["count"], 5)
        self.assertEqual(len(by_key["list[].widht"]["locations"]), 3)
        self.assertEqual(by_key["list[].widht"]["more"], 2)
        self.assertEqual(by_key["properties.prop_truck_wheel.widht"]["members"], 2)
        expanded = {g["keyPattern"]: g for g in validate.group_findings(findings, expand=True)}
        self.assertEqual(len(expanded["list[].widht"]["locations"]), 5)

    def test_json_has_flat_findings_and_groups(self) -> None:
        pak = self.make_pak([("ssl/a.cls", "x = .5\n"), ("ssl/b.cls", "x = .5\n")])
        code, out = self.cli([str(pak), "--json", "--game-root", NO_GAME])
        report = json.loads(out)
        self.assertEqual(code, 1)
        self.assertEqual(len(report["findings"]), 2)
        self.assertEqual([(g["code"], g["count"]) for g in report["groups"]], [("RC051", 2)])
        self.assertTrue(all(f["id"] and f["keyPath"] == f["key"] for f in report["findings"]))

    def test_fail_on_defaults_to_error(self) -> None:
        pak = self.make_pak([("ssl/a.cls", "c = no\n")])           # RC052 warning only
        self.assertEqual(self.cli([str(pak), "--game-root", NO_GAME])[0], 0)
        self.assertEqual(self.cli([str(pak), "--fail-on", "warning", "--game-root", NO_GAME])[0], 1)
        self.assertEqual(self.cli([str(pak), "--baseline", str(Path(NO_GAME) / "nope.pak"),
                                   "--game-root", NO_GAME])[0], 2)


class FixHintTests(Base):
    def test_mechanical_fix_hints(self) -> None:
        fx = self.fixture({"ssl/w.cls": 'properties = {\n prop_truck_wheel = {\n  widht = 2\n  torqueType = "default"\n'
                                        ' }\n}\n', "ssl/n.cls": "a = .5\nb = [1e-05]\n"})
        hints = {f.code: f.fixHint for f in fx.run(rules=["unknown-keys", "ps-numbers"], sdk=True)}
        self.assertEqual(hints["RC053"], "rename 'widht' to 'width'")
        self.assertEqual(hints["RC055"], 'set torqueType = "defaults"')
        self.assertEqual(hints["RC051"], "write 0.5 instead of .5")
        self.assertEqual(hints["RC050"], "write 0.00001 instead of 1e-05")


class IgnoredFieldTests(Base):
    def test_builtin_cases_fire_even_though_retail_ships_the_keys(self) -> None:
        saved = validate._retail_ignored
        validate._retail_ignored = {}                     # severity downgrade is tested separately
        self.addCleanup(setattr, validate, "_retail_ignored", saved)
        self.assertIn("spreadAngle", validate.RETAIL_KEYS[".ssl::WheelParticleMaterialSettings"])
        cls = PARTICLES_CLS.replace("}\n}\n", "}\n prop_truck_rb = { gearbox = { params = { lowRangeMultiplier = 0.5 } } }\n}\n")
        found = self.fixture({"ssl/w.cls": cls}).run(rules=["ignored-fields", "unknown-keys"], sdk=True)
        rc072 = {f.key: f for f in found if f.code == "RC072"}
        self.assertEqual(sorted(rc072), ["properties.prop_truck_rb.gearbox.params.lowRangeMultiplier",
                                         "properties.prop_wheel_particles_base.wheelSettings.spreadAngle"])
        spread = rc072["properties.prop_wheel_particles_base.wheelSettings.spreadAngle"]
        self.assertEqual(spread.severity, "warning")
        self.assertIn("code analysis, static", spread.evidence)
        self.assertIn("FUN_140cbbfe0", spread.evidence)
        self.assertIn("spreadAngleProb", spread.fixHint)
        self.assertIn("lowRangeGear", rc072["properties.prop_truck_rb.gearbox.params.lowRangeMultiplier"].fixHint)
        self.assertFalse([f for f in found if f.code == "RC053" and "spreadAngle" in f.key])

    def test_retail_carried_dead_keys_drop_to_info_except_keep_warning(self) -> None:
        saved = validate._retail_ignored
        validate._retail_ignored = {".ssl::WheelParticleMaterialSettings|spreadAngle": {"occurrences": 2263},
                                    ".ssl::TruckGearboxParams|lowRangeMultiplier": {"occurrences": 51},
                                    ".tpl_markup::tpl_markup_position_motor|spring": {"occurrences": 92}}
        self.addCleanup(setattr, validate, "_retail_ignored", saved)
        found = self.fixture({"ssl/w.cls": PARTICLES_CLS,
                              "bro/trucks/t.bro": "truckSettings = { gearbox = { lowRangeMultiplier = 0.5 } }\n"}).run(
            rules=["ignored-fields"], sdk=True)
        by_key = {f.key.rsplit(".", 1)[-1]: f for f in found}
        self.assertEqual(by_key["spreadAngle"].severity, "info")
        self.assertIn("retail carries it too (2263 retail occurrences); harmless", by_key["spreadAngle"].message)
        self.assertEqual(by_key["lowRangeMultiplier"].severity, "info")       # untyped scan: any type's count
        self.assertEqual(validate.dead_key_severity(".tpl_markup::tpl_markup_position_motor", "spring", "warning",
                                                    {"keepWarning": True})[0], "warning")
        self.assertEqual(validate.dead_key_severity(".ssl::X", "never", "warning"), ("warning", ""))

    def test_rc072_groups_one_line_per_key(self) -> None:
        cls = ('properties = {\n prop_wheel_particles_base = {\n  wheelSettings = { spreadAngle = 3 }\n }\n'
               ' a = { wheelSettings = { spreadAngle = 1 } }\n}\n')
        found = self.fixture({"ssl/w.cls": PARTICLES_CLS, "ssl/v.cls": cls}).run(rules=["ignored-fields"], sdk=True)
        findings = found + [dataclasses.replace(found[0], key="other.path[3].spreadAngle", id="x")]
        groups = validate.group_findings(findings)
        self.assertEqual([(g["keyPattern"], g["count"]) for g in groups], [("*.spreadAngle", len(findings))])

    def test_global_key_found_without_sdk(self) -> None:
        found = self.fixture({"bro/trucks/t.bro": "truckSettings = { gearbox = { lowRangeMultiplier = 0.5 } }\n"}).run(
            rules=["ignored-fields"])
        self.assertEqual([(f.code, f.key) for f in found], [("RC072", "truckSettings.gearbox.lowRangeMultiplier")])

    def test_position_motor_spring_reader(self) -> None:
        fields = validate.ReadFields()
        reader, spec = fields.ignored(".tpl_markup::tpl_markup_position_motor", "spring", "objectInfos[0].motor")
        self.assertEqual(reader.address, "FUN_141594b60")
        self.assertIn("tpl_markup_spring_motor {spring, damping}", spec["fixHint"])
        self.assertIsNone(fields.ignored(".tpl_markup::tpl_markup_spring_motor", "spring", ""))

    def test_loader_reads_the_research_schema(self) -> None:
        table = {"schemaVersion": 1, "readers": [
            {"context": "prop_truck_wheel", "match": "type", "address": "FUN_1400000a0", "grade": "C",
             "reads": [{"key": "width", "default": 1, "notes": ""}, {"key": "torqueType", "default": "none"}],
             "ignoredKnown": [{"key": "rimObjName", "why": "the wheel reader never looks it up",
                               "evidence": "FUN_1400000a0 +0x40"}]}]}
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "read_fields.json"
        path.write_text(json.dumps(table), encoding="utf-8")
        fields = validate.ReadFields.load(path)
        self.assertTrue(fields.table_loaded)
        fx = self.fixture({"ssl/w.cls": 'properties = { prop_truck_wheel = { width = 2 rimObjName = "rim" } }\n'})
        notes = []
        found = fx.run(rules=["ignored-fields"], sdk=True, read_fields=fields, notes=notes)
        self.assertEqual([(f.code, f.severity, f.key) for f in found],
                         [("RC072", "warning", "properties.prop_truck_wheel.rimObjName")])
        self.assertIn("FUN_1400000a0 +0x40", found[0].evidence)
        self.assertIn("never looks it up", found[0].message)
        self.assertTrue(any("read_fields.json" in n for n in notes))
        # a key the reads list lacks: info for review
        table["readers"][0]["ignoredKnown"] = []
        table["readers"][0]["exhaustive"] = True          # .prop reads lists are partial unless marked
        found = fx.run(rules=["ignored-fields"], sdk=True, read_fields=validate.ReadFields.from_data(table))
        self.assertEqual([(f.code, f.severity) for f in found], [("RC072", "info")])
        with self.assertRaises(ValueError):
            validate.ReadFields.from_data({"schemaVersion": 2, "readers": []})

    RESEARCH = {"schemaVersion": 1, "readers": [
        {"context": "ssl:PropTruckWheel (prop_truck_wheel)", "typeKey": ".prop::prop_truck_wheel",
         "match": "*.cls: properties.prop_truck_wheel (wheel classes)", "address": "0x140dd1ad0",
         "grade": "Confirmed-from-code",
         "reads": [{"key": "width", "default": 1}, {"key": "torqueType", "default": "none"},
                   {"key": "rimObjName"}, {"key": "lighting", "notes": "schema gap: read, not in meta_desc"}],
         "ignoredKnown": [{"key": "rimObjName", "why": "ignored when torqueType is none", "evidence": "0x1"}],
         "conditional": [{"key": "rimObjName", "ignoredWhen": {"torqueType": "none"}}]}],
        "ignoredKeys": {".prop::prop_truck_wheel": {"bodyFriction": "runtime field"}},
        "conditional": {".prop::prop_truck_wheel": [
            {"key": "lighting", "ignoredWhen": {"/gate.version": {"notIn": [3], "default": 0}}, "severity": "info",
             "aggregate": "file", "why": "parsed; may have no effect without gate.version = 3"}]}}

    def wheels(self, body: str, root: str = "") -> list:
        fx = self.fixture({"ssl/w.cls": f"properties = {{\n prop_truck_wheel = {{ {body} }}\n}}\n{root}"})
        return fx.run(rules=["ignored-fields", "unknown-keys"], sdk=True,
                      read_fields=validate.ReadFields.from_data(self.RESEARCH, "read_fields.json"))

    def test_research_shape_conditional_sibling_default(self) -> None:
        found = self.wheels('rimObjName = "rim"')                    # torqueType absent: reader default none
        self.assertEqual([(f.code, f.severity, f.key) for f in found],
                         [("RC072", "warning", "properties.prop_truck_wheel.rimObjName")])
        self.assertIn("torqueType is none", found[0].message)
        self.assertIn("0x140dd1ad0", found[0].evidence)
        self.assertEqual(self.wheels('rimObjName = "rim" torqueType = "full"'), [])
        found = self.wheels("bodyFriction = 0.2")                    # top-level ignoredKeys, not a schema field
        self.assertEqual([(f.code, f.message.endswith("runtime field")) for f in found], [("RC072", True)])

    def test_root_gate_aggregates_and_schema_gap_is_not_unknown(self) -> None:
        found = self.wheels("lighting = { a = 1 }")
        self.assertEqual([(f.code, f.severity, f.key) for f in found],
                         [("RC072", "info", "properties.*.lighting")])
        self.assertFalse([f for f in found if f.code == "RC053"])
        self.assertFalse([f for f in self.wheels("lighting = { a = 1 }", "gate = { version = 3 }") if f.code == "RC072"])

    def test_local_overlay_refines_research_entries(self) -> None:
        local = {"schemaVersion": 1, "ignoredKeys": {".prop::prop_truck_wheel": {"bodyFriction": {"fixHint": "use X"}}},
                 "conditional": {".prop::prop_truck_wheel": [{"key": "rimObjName", "fixHint": "set torqueType"}]}}
        fields = validate.ReadFields(validate.ReadFields.parse(self.RESEARCH) + validate.ReadFields.parse(local))
        fx = self.fixture({"ssl/w.cls": 'properties = { prop_truck_wheel = { bodyFriction = 1 rimObjName = "r" } }\n'})
        hints = {f.key.rsplit(".", 1)[-1]: (f.message, f.fixHint)
                 for f in fx.run(rules=["ignored-fields"], sdk=True, read_fields=fields)}
        self.assertEqual(hints["bodyFriction"][1], "use X")
        self.assertIn("runtime field", hints["bodyFriction"][0])
        self.assertEqual(hints["rimObjName"][1], "set torqueType")

    def test_shipped_tables_load(self) -> None:
        if not validate.READ_FIELDS_FILE.is_file():
            self.skipTest("src/roadcraft/data/read_fields.json not present")
        fields = validate.ReadFields.load()
        self.assertTrue(fields.table_loaded)
        geom = [".obj_settings::TplObjSettingsGeom"]
        self.assertIn("lighting", fields.reads(geom, ""))
        self.assertIsNone(fields.ignored(geom, "visibility", "objSettings.settings.x"))
        self.assertIsNone(fields.condition(geom, "visibility", "objSettings.settings.x"))
        self.assertIsNone(fields.ignored(geom, "collision", "objSettings.settings.x"))
        reader, spec = fields.ignored([".prop::prop_truck_wheel"], "bodyFriction", "properties.prop_truck_wheel")
        self.assertIn("frictionMaterialsList.<material>.frictionValue", spec["fixHint"])

    def test_absent_table_disables_the_table_with_a_note(self) -> None:
        original = validate.READ_FIELDS_FILE
        validate.READ_FIELDS_FILE = Path(tempfile.gettempdir()) / "no_such_read_fields.json"
        self.addCleanup(setattr, validate, "READ_FIELDS_FILE", original)
        fields = validate.ReadFields.load()
        self.assertFalse(fields.table_loaded)
        self.assertIn("disabled", fields.note)
        notes = []
        self.fixture({"ssl/w.cls": PARTICLES_CLS}).run(rules=["ignored-fields"], sdk=True, notes=notes,
                                                       read_fields=validate.ReadFields.load())
        self.assertTrue(any("not present" in n for n in notes))
        with self.assertRaises(FileNotFoundError):
            validate.ReadFields.load(Path(tempfile.gettempdir()) / "explicit_missing.json")

    def test_legacy_mapping_still_accepted(self) -> None:
        fx = self.fixture({"ssl/w.cls": 'properties = { prop_truck_wheel = { width = 2 rimObjName = "rim" } }\n'})
        found = fx.run(rules=["ignored-fields"], sdk=True, read_fields={".prop::prop_truck_wheel": ["width"]})
        self.assertEqual([(f.code, f.key) for f in found], [("RC072", "properties.prop_truck_wheel.rimObjName")])


GATED = {"schemaVersion": 1, "readers": [], "gated": {
    "enum": {"OBJ_SETTINGS_EXPORT_VER_NONE": 0, "OBJ_SETTINGS_EXPORT_VER_CDT": 1,
             "OBJ_SETTINGS_EXPORT_VER_VISIBILITY": 2, "OBJ_SETTINGS_EXPORT_VER_MOD_EDITOR": 3},
    "minExportedVersion": {".obj_settings::TplObjSettingsGeom": {"collision": 1, "visibility": 2, "lighting": 3}}}}


class ObjSettingsGateTests(Base):
    def run_markup(self, version=""):
        hidden = "visibility = { visibleDefault = False }"
        markup = ("version = 1\nobjSettings = {\n" + (f" exportedVersion = {version}\n" if version else "")
                  + f" settings = {{\n  Body = {{ {hidden} lighting = {{ smDontCastShadow = True }} }}\n"
                  f"  cdt_frame = {{ {hidden} }}\n  Ghost = {{ {hidden} }}\n }}\n}}\n")
        fx = self.fixture({"models/mods/m.tpl.asset/m.tpl_markup": markup,
                           "models/mods/m.tpl.asset/tpl/m.tpl": tpl_bytes({"Body": matrix(), "cdt_frame": matrix()})})
        return fx.run(rules=["objsettings-gate"], read_fields=validate.ReadFields.from_data(GATED))

    def test_hidden_node_renders_and_stale_entries_without_exported_version(self) -> None:
        found = self.run_markup()
        warnings_ = [f for f in found if f.severity == "warning"]
        self.assertEqual([f.key for f in warnings_], ["objSettings.settings.Body.visibility.visibleDefault"])
        self.assertIn("intended hidden, actually visible: Body", warnings_[0].message)
        self.assertIn("OBJ_SETTINGS_EXPORT_VER_VISIBILITY (2)", warnings_[0].fixHint)
        info = [f for f in found if f.severity == "info"]
        self.assertEqual(len(info), 1)
        self.assertIn("exportedVersion is absent (0)", info[0].message)
        self.assertIn("stale entries, no effect (no such node in the compiled model): Ghost", info[0].message)
        self.assertIn("lighting 1", info[0].message)
        self.assertIn("OBJ_SETTINGS_EXPORT_VER_MOD_EDITOR", info[0].fixHint)

    def test_visibility_version_opens_the_gate(self) -> None:
        found = self.run_markup("OBJ_SETTINGS_EXPORT_VER_VISIBILITY")
        self.assertEqual([f.severity for f in found], ["info"])
        self.assertIn("lighting 1", found[0].message)
        self.assertNotIn("visibility", found[0].message.split("have no effect")[0].split("(")[-1])

    def test_no_gate_table_skips_with_a_note(self) -> None:
        notes = []
        fx = self.fixture({"models/mods/m.tpl.asset/m.tpl_markup": "objSettings = { settings = { A = { } } }\n"})
        self.assertEqual(fx.run(rules=["objsettings-gate"], notes=notes), [])
        self.assertTrue(any("RC074" in n for n in notes))


BODY = '{{ __type = "tpl_markup_object_property_physics" {fields} }}'


class EngineDefaultTests(Base):
    def markup(self, *bodies):
        infos = " ".join(f'{{ objectId = {{ name = "B{i}" }} properties = [ {BODY.format(fields=b)} ] }}'
                         for i, b in enumerate(bodies))
        return f"version = 1\nobjectInfos = [ {infos} ]\n"

    def test_one_info_per_markup_listing_defaults(self) -> None:
        markup = self.markup("friction = 1 angularDamping = 0.1 density = 700",
                             "massFromDensity = False friction = 1 angularDamping = 0.1")
        found = self.fixture({"models/mods/m.tpl.asset/m.tpl_markup": markup}).run(rules=["engine-defaults"])
        self.assertEqual([(f.code, f.severity, f.key) for f in found],
                         [("RC073", "info", "objectInfos[].physicsBody")])
        self.assertIn("restitution -> 0.4 on 2/2", found[0].message)
        self.assertNotIn("density", found[0].message.split("restitution")[0])
        self.assertNotIn("density -> 600", found[0].message)       # second body uses explicit mass

    def test_complete_bodies_are_clean(self) -> None:
        markup = self.markup("restitution = 0.1 friction = 1 angularDamping = 0.1 density = 700")
        self.assertEqual(self.fixture({"models/mods/m.tpl.asset/m.tpl_markup": markup}).run(
            rules=["engine-defaults"]), [])


SDK_ROOT = schema.default_game_root()
SAMPLE = SDK_ROOT / "root" / "mods_source"


@unittest.skipUnless(schema.sdk_present() and (SAMPLE / "bro" / "trucks" / "tuz_119lynx_mod.bro").is_file(),
                     "RoadCraft SDK (meta descs, retail paks, TUZ sample) not installed")
class SdkSampleIntegrationTests(unittest.TestCase):
    """The SDK's TUZ Lynx sample carries two documented faults: lights_emmissive (cockpit-and-lamps.md) and a
    suspensionCollection without useSuspensionCollection (the Warthog's inherited fault)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.found = validate.validate(SAMPLE)

    def test_documented_faults_are_found(self) -> None:
        got = {(f.code, f.key) for f in self.found}
        self.assertIn(("RC066", "materials.marker_lights_mat.dynamicMaterials.lights_emmissive"), got)
        self.assertIn(("RC001", "truckSettings.useSuspensionCollection"), got)

    def test_no_type_or_reference_errors_on_sdk_content(self) -> None:
        self.assertFalse([f for f in self.found if f.code in ("RC049", "RC054", "RC055", "RC070")])


@unittest.skipUnless((SDK_ROOT / "root" / "paks" / "client").is_dir() and any(SAMPLE.glob("material_instances/*.mi")),
                     "RoadCraft retail paks or the SDK's shipped material instances not installed")
class RetailMaterialTypeTests(unittest.TestCase):
    """Retail ships no .mi in its paks; the SDK's own material instances (root/mods_source, every retail preset)
    must all pass RC078 against the retail material library."""

    def test_sdk_material_instances_pass(self) -> None:
        from roadcraft import retail
        library = retail.material_templates(SDK_ROOT)
        self.assertIn("vehicle_body", library)
        self.assertIn("glt_extended_material", library)
        notes = []
        found = validate.validate(SAMPLE, rules=["material-type"], notes=notes)
        self.assertEqual(found, [])
        self.assertFalse([n for n in notes if "RC078" in n])


if __name__ == "__main__":
    unittest.main()
