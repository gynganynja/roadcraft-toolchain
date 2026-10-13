"""roadcraft.validate: one synthetic fixture per rule (positive and negative), pak reading, the CLI contract,
and SDK-gated integration tests on the SDK's own TUZ sample (skipped, with the reason, without an install)."""

import contextlib
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


if __name__ == "__main__":
    unittest.main()
