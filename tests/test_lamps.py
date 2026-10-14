import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from roadcraft import bro_lint, cli, lamps, ps_format


def _refs(nodes):
    """Every Node/port reference in a node table."""
    out = []
    for node in nodes.values():
        for value in node.values():
            if isinstance(value, list):
                out += [v for v in value if isinstance(v, str) and "/" in v]
    return out


def _dump_twuck_v4_graph():
    """The Dump Twuck v4 beacon: a double flash that swaps the unlit lens and its lit copy."""
    nodes = {}
    for label, on, off in (("BeaconLit", "blue_beacons_on", "blue_beacons"), ("BeaconDark", "blue_beacons", "blue_beacons_on")):
        nodes[label] = dict(lamps.show([on], True), OnExit=[label + "Hide/Input"])
        nodes[label + "Hide"] = lamps.show([off], False)
    steps = [("BeaconFlashOne", .08, "BeaconDark", "BeaconGap"), ("BeaconGap", .10, "BeaconLit", "BeaconFlashTwo"),
             ("BeaconFlashTwo", .08, "BeaconDark", "BeaconRest"), ("BeaconRest", .55, "BeaconLit", "BeaconFlashOne")]
    for name, seconds, state, nxt in steps:
        nodes[name] = lamps.tick_timer(seconds, [state + "/Input", nxt + "/Restart"])
    nodes["Init"] = {"OnExit": ["BeaconFlashOne/Stop", "BeaconDark/Input"], "__type": "BlueprintCommonLibraryOninit"}
    return {"blueprints": {"Lights": {"nodes": nodes, "__type": lamps.BLUEPRINT_TYPE}}}


class LampGraphTests(unittest.TestCase):
    def test_lada_states_resolve_and_init_hides_every_lit_copy(self):
        nodes = lamps.lamp_states(driving=["head_fx", "tail_fx"], reversing=["rev_fx"])
        self.assertTrue(all(ref.split("/")[0] in nodes for ref in _refs(nodes)))
        after = lamps.simulate(nodes, nodes["Init"]["OnExit"])
        self.assertEqual(after, {"head_lights": True, "head_lights_on": False, "tail_lights": True,
                                 "tail_lights_on": False, "brake_lights_on": False,
                                 "reverse_lights": True, "reverse_lights_on": False})

    def test_engine_brake_and_reverse_states(self):
        nodes = lamps.lamp_states()
        after = lamps.simulate(nodes, nodes["Init"]["OnExit"])
        running = lamps.simulate(nodes, ["HeadsOn/Input", "TailDim/Input"], after)
        self.assertTrue(running["head_lights_on"] and running["tail_lights_on"])
        self.assertFalse(running["head_lights"] or running["tail_lights"])
        braking = lamps.simulate(nodes, ["TailBright/Input"], running)
        self.assertTrue(braking["brake_lights_on"])
        self.assertFalse(braking["tail_lights_on"] or braking["tail_lights"])
        reversing = lamps.simulate(nodes, ["ReverseOn/Input"], braking)
        self.assertTrue(reversing["reverse_lights_on"])
        self.assertFalse(reversing["reverse_lights"])

    def test_missing_lens_keeps_its_effects_without_empty_show_nodes(self):
        nodes = lamps.lamp_states(reverse=None, reversing=["rev_fx"])
        empty = [n for n, node in nodes.items() if node["__type"] == "BlueprintNodeShowHideGeomObjects"
                 and not node["objNameRef"]["def"]]
        self.assertEqual(empty, [])
        self.assertIn("ReverseOnFx/Input", nodes["ReverseSelect"]["OnTrue"])
        self.assertIn("ReverseOffStop/Input", nodes["Init"]["OnExit"])


class FlasherTests(unittest.TestCase):
    def test_double_flash_switches_only_the_overlay(self):
        nodes, start, stop = lamps.flasher("Beacon", ["beacon_lit"], effects=["beacon_fx"], pattern=lamps.DOUBLE_FLASH)
        switched = {o for node in nodes.values() if node["__type"] == "BlueprintNodeShowHideGeomObjects"
                    for o in node["objNameRef"]["def"]}
        self.assertEqual(switched, {"beacon_lit"})
        timers = [n for n, node in nodes.items() if node["__type"] == "BlueprintNodeTickTimer"]
        self.assertEqual(len(timers), 4)
        self.assertAlmostEqual(sum(nodes[t]["timeRef"]["def"] for t in timers), .81)
        for i, name in enumerate(timers):
            self.assertEqual(nodes[name]["OnFinish"][-1], timers[(i + 1) % 4] + "/Restart")
        self.assertEqual(start[-1], "BeaconStep0/Restart")
        self.assertIn("BeaconShow/Input", start)
        self.assertTrue({t + "/Stop" for t in timers} <= set(stop) and "BeaconHide/Input" in stop)

    def test_patterns_must_alternate_and_start_lit(self):
        for pattern in (((False, .4), (True, .4)), ((True, .4),), ((True, .2), (True, .2)), ((True, .1), (False, .1), (True, .1))):
            with self.assertRaises(ValueError):
                lamps.flasher("B", ["lit"], pattern=pattern)
        with self.assertRaises(ValueError):
            lamps.flasher("B", [])

    def test_generated_block_is_clean(self):
        built = lamps.exterior_lights({"head_l": "head", "tail_l": "tail", "rev_l": "reverse", "beacon": "beacon_amber"},
                                      flashers=[{"prefix": "Beacon", "lit": ["beacon_lit"], "roles": ["beacon_amber"]}])
        graph = {"blueprints": {"Lights": built["blueprint"]}}
        self.assertEqual(lamps.lamp_findings(graph, set()), [])
        nodes = built["blueprint"]["nodes"]
        self.assertIn("beacon_fx", nodes["BeaconGlow"]["vfxList"])
        self.assertNotIn("beacon_fx", nodes["HeadsOnFx"]["vfxList"])
        self.assertIn("BeaconStep0/Restart", nodes["Apply"]["OnTrue"])
        self.assertIn("BeaconHide/Input", nodes["Init"]["OnExit"])
        self.assertEqual(lamps.simulate(nodes, nodes["Init"]["OnExit"])["beacon_lit"], False)
        self.assertEqual(built["markupHidden"], [])
        with self.assertRaises(ValueError):
            lamps.exterior_lights({"x": "searchlight"})


class NativeGroupTests(unittest.TestCase):
    def test_alces_shaped_block(self):
        block = lamps.vehicle_light_materials({"head": ["reflector_headlights"], "brake": ["stop_lights"],
                                               "reverse": ["reverse_lights"], "marker": ["marker_lights"],
                                               "cockpit": ["_hp_cab_interior_gauges"]})
        lights = block["lights"]
        self.assertTrue(block["isEnabled"])
        self.assertEqual(list(lights), ["Headlights", "Brake", "Reverse", "Marker", "Cockpit"])
        self.assertEqual(lights["Brake"], {"lightData": {"defaultName": "default", "geomNames": ["stop_lights"],
                                                         "__type": "BrakeHeadlights"},
                                           "__type": "VehicleLightMaterialDatas"})
        self.assertEqual(lights["Marker"]["lightData"]["lightName"], "lights_emissive")
        self.assertEqual(lights["Marker"]["lightData"]["__type"], "Headlights")
        self.assertEqual(lights["Cockpit"]["lightData"]["__type"], "CockpitLights")
        self.assertNotIn("lightName", lights["Headlights"]["lightData"])
        from roadcraft import validate
        self.assertEqual(set(validate.bro_lights({"vehicleLightMaterials": block})),
                         {f"{k}.lightData" for k in lights})

    def test_states_override_and_empty_groups(self):
        block = lamps.vehicle_light_materials({"brake": ["stop_lights"], "reverse": []},
                                              states={"brake": "lights_emissive"})
        self.assertEqual(list(block["lights"]), ["Brake"])
        self.assertEqual(block["lights"]["Brake"]["lightData"]["lightName"], "lights_emissive")

    def test_retail_has_no_indicator_or_hazard_group(self):
        for role in ("indicator", "hazard", "turn_left"):
            with self.assertRaises(ValueError):
                lamps.vehicle_light_materials({role: ["turn_lights"]})

    def test_dynamic_material_slot(self):
        slot = lamps.dynamic_material("mod_x_body", "mod_x_stop_lit")
        self.assertEqual(slot, {"materialName": "mod_x_body", "dynamicMaterials": {
            "default": {"materialName": "mod_x_body"}, "lights": {"materialName": "mod_x_stop_lit"}}})
        self.assertIn("lights_emissive", lamps.dynamic_material("a", "b", "lights_emissive")["dynamicMaterials"])
        with self.assertRaises(ValueError):
            lamps.dynamic_material("same", "same")


class LampFindingTests(unittest.TestCase):
    def test_dump_twuck_v4_strobe_and_markup_are_flagged(self):
        markup = {"objSettings": {"settings": {"blue_beacons_on": {"visibility": {
            "visibleDefault": False, "visibleInReflectionCubemap": False, "__type": "tpl_markup_visibility_flags"}}}}}
        found = {code: message for code, _, message, _ in
                 lamps.lamp_findings(_dump_twuck_v4_graph(), lamps.markup_hidden(markup))}
        self.assertIn("blue_beacons_on", found["RC037"])
        self.assertIn("'blue_beacons'", found["RC039"])

    def test_strobe_check_needs_only_the_graph(self):
        codes = [f[0] for f in lamps.lamp_findings(_dump_twuck_v4_graph())]
        self.assertEqual(codes, ["RC039"])

    def test_lit_copy_left_visible_at_init(self):
        nodes = {"On": dict(lamps.show(["x_on"], True)),
                 "Init": {"OnExit": [], "__type": "BlueprintCommonLibraryOninit"}}
        codes = [f[0] for f in lamps.lamp_findings({"blueprints": {"L": {"nodes": nodes}}}, set())]
        self.assertEqual(codes, ["RC038"])

    def test_markup_hidden_reads_flags_and_alias(self):
        markup = {"objSettings": {"settings": {
            "a": {"visibility": {"visibleDefault": False, "__type": "tpl_markup_visibility_flags"}},
            "b": {"visibility": {"__type": "invisible"}},
            "c": {"visibility": {"visibleDefault": True, "__type": "tpl_markup_visibility_flags"}}}}}
        self.assertEqual(lamps.markup_hidden(markup), {"a", "b"})
        self.assertEqual(lamps.markup_hidden(None), set())

    def test_material_conflicts(self):
        rows = {"L275_Glass_LOD0": [("l275_glass", "mod_l275_glass", "vehicle_glass_outer"),
                                    ("l275_lights", "mod_l275_glass", "vehicle_body")],
                "tray_LOD0": [("l275_rubber", "mod_l275_tray_trim", "vehicle_body"),
                              ("l275_red", "mod_l275_tray_trim", "vehicle_body")]}
        found = lamps.material_conflicts(rows)
        self.assertEqual([f["object"] for f in found], ["L275_Glass_LOD0"])

    def test_lamp_materials_and_beams(self):
        lit = lamps.lit_material("mod_x_lights", "tail")["shaders"]["glt_shader"]["base"]["params"]
        self.assertEqual(lit["emissive"]["tint"], [255, 255, 12, 3])
        self.assertEqual(lit["tex"]["emissiveTex"], "mod_x_lights_em")
        self.assertEqual(lamps.unlit_material("mod_x_lights")["__type"], "vehicle_body")
        head = lamps.light_effect("head_l", "head")
        self.assertFalse(head["isAutoStart"])
        self.assertEqual((head["list"]["light"]["lightType"], head["list"]["light"]["enableSM"]), ("spot", True))
        self.assertEqual(lamps.light_effect("t", "tail", fogAmount=0)["list"]["light"]["fogAmount"], 0)


class LintAndCliTests(unittest.TestCase):
    def test_lint_reports_lamp_codes_with_the_markup(self):
        markup = {"objSettings": {"settings": {"blue_beacons_on": {"visibility": {
            "visibleDefault": False, "__type": "tpl_markup_visibility_flags"}}}}}
        doc = {"blueprint": _dump_twuck_v4_graph()}
        codes = {f["code"]: f["library"] for f in bro_lint.lint_truck(doc, markup=markup)}
        self.assertEqual(codes.get("RC037"), "library/cockpit-and-lamps.md")
        self.assertIn("RC039", codes)
        self.assertNotIn("RC037", {f["code"] for f in bro_lint.lint_truck(doc)})

    def test_lint_files_reads_the_markup_beside_the_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            asset = Path(tmp) / "x.tpl.asset"
            (asset / "tpl").mkdir(parents=True)
            (asset / "tpl" / "x.tpl").write_bytes(b"")
            ps_format.dump({"objSettings": {"settings": {"blue_beacons_on": {"visibility": {
                "visibleDefault": False, "__type": "tpl_markup_visibility_flags"}}}}}, asset / "x.tpl_markup")
            self.assertEqual(lamps.markup_beside(asset / "tpl" / "x.tpl"), asset / "x.tpl_markup")
            bro = Path(tmp) / "x.bro"
            ps_format.dump({"blueprint": _dump_twuck_v4_graph()}, bro)
            result = bro_lint.lint_files(bro, markup=asset / "x.tpl_markup")
            self.assertIn("RC037", {f["code"] for f in result["findings"]})
            self.assertEqual(result["markup"], str(asset / "x.tpl_markup"))

    def test_cli_writes_a_parsable_fragment(self):
        spec = {"anchors": {"head_l": "head", "beacon": "beacon_amber"},
                "flashers": [{"prefix": "Beacon", "lit": ["beacon_lit"], "roles": ["beacon_amber"], "pattern": "double"}]}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "lights.bro"
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = cli.main(["lamps", json.dumps(spec), "--output", str(out), "--json"])
            self.assertEqual(code, 0)
            result = json.loads(buffer.getvalue())
            self.assertEqual(result["findings"], [])
            doc = ps_format.load(out)
            nodes = doc["blueprint"]["blueprints"]["ExteriorLights"]["nodes"]
            self.assertEqual(nodes["BeaconStep3"]["timeRef"]["def"], .55)
            self.assertIn("head_l_fx", doc["effects"]["propSfx"]["list"])


if __name__ == "__main__":
    unittest.main()
