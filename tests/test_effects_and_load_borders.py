import unittest

from roadcraft import bro_lint
from roadcraft.tpl_reader import TplNodes


def model(rows):
    """rows: (name, parent name or None, native position)."""
    names = [r[0] for r in rows]
    index = {n: i for i, n in enumerate(names)}
    matrices = [(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, *pos, 1) for _, _, pos in rows]
    parents = [index[p] if p else -1 for _, p, _ in rows]
    return TplNodes(names=names, index=index, matrices=matrices, parents=parents)


def dump_truck(back_parent, side_parent="BoneDump_cdt"):
    # Dump Twuck: bed pivot native (0, 4.2, -3.677), tail lid under the bed.
    return model([("RoadCraftRig", None, (0, 0, 0)), ("BoneChassis_cdt", "RoadCraftRig", (0, 0, 0)),
                  ("BoneDump_cdt", "BoneChassis_cdt", (0, 4.2, -3.677)),
                  ("BoneSandCap_cdt", "BoneDump_cdt", (0, 4.5, -6.58)),
                  ("hidden__load_volume", "BoneDump_cdt", (0, 0, 0)),
                  ("hidden__load_border_left", side_parent, (0, 0, 0)),
                  ("hidden__load_border_right", "BoneDump_cdt", (0, 0, 0)),
                  ("hidden__load_border_front", "BoneDump_cdt", (0, 0, 0)),
                  ("hidden__load_border_back", back_parent, (0, 0, 0)),
                  ("ls_tail_l", "BoneChassis_cdt", (0.55, 2.53, -4.31)),
                  ("sfx_exhaust_01", "BoneChassis_cdt", (0, 0, 0))])


LOAD = {"loadVolumeSettings": {"isEnabled": True, "volumeMesh": "hidden__load_volume",
        "bodySettings": {"parentBody": "BoneDump_cdt", "leftWall": "hidden__load_border_left",
                         "rightWall": "hidden__load_border_right", "frontWall": "hidden__load_border_front",
                         "backWall": "hidden__load_border_back"}}}


def started(*names):
    return {"blueprint": {"blueprints": {"SFX": {"nodes": {
        f"N{i}": {"vfxUidRef": {"def": n, "__type": "SfxStringRefParam"}, "__type": "BlueprintNodeVfxRestart"}
        for i, n in enumerate(names)}}}}}


class LoadBorderTests(unittest.TestCase):
    def findings(self, nodes, code="RC036"):
        return [f for f in bro_lint.lint_truck(LOAD, model=nodes) if f["code"] == code]

    def test_back_border_under_the_load_body_is_an_error(self):
        # Revision 3: the grid ran 3.7 m past the tail.
        rows = self.findings(dump_truck("BoneDump_cdt"))
        self.assertEqual([f["severity"] for f in rows], ["error"])

    def test_back_border_under_the_lid_body_is_accepted(self):
        self.assertEqual(self.findings(dump_truck("BoneSandCap_cdt")), [])

    def test_side_border_under_another_body_is_a_warning(self):
        rows = self.findings(dump_truck("BoneSandCap_cdt", side_parent="BoneSandCap_cdt"))
        self.assertEqual([f["severity"] for f in rows], ["warning"])


class EffectTests(unittest.TestCase):
    def codes(self, doc, **kw):
        return {(f["code"], f["severity"]) for f in bro_lint.lint_truck(doc, **kw)}

    def test_donor_sfx_graph_without_effects_is_flagged(self):
        # Dump Twuck v1-v3 copied the Lynx SFX graph without the Lynx effects block.
        self.assertIn(("RC026", "warning"), self.codes(started("part_exhaust_small_cars")))

    def test_declared_effects_are_accepted(self):
        doc = started("part_exhaust_small_cars")
        doc["effects"] = {"propSfx": {"list": {"part_exhaust_small_cars": {}}, "__type": "sfx"}, "__type": "EffectsSettings"}
        self.assertNotIn("RC026", {c for c, _ in self.codes(doc)})

    def test_module_names_are_only_info(self):
        doc = started("part_radiator_haze")
        doc["effects"] = {"propSfx": {"list": {}, "__type": "sfx"}, "__type": "WheelExtraBigVfx01"}
        self.assertEqual({s for c, s in self.codes(doc) if c == "RC026"}, {"info"})

    def test_compiled_class_missing_started_effect_is_an_error(self):
        text = ('properties = { prop_blueprints = { blueprints = { SFX = { nodes = { A = { vfxUidRef = { def = "part_radiator_haze" '
                '__type = "SfxStringRefParam" } __type = "BlueprintNodeVfxRestart" } } } } } }')
        self.assertIn(("RC026", "error"), self.codes({}, compiled_class=text))

    def test_effects_on_missing_nodes_are_flagged_and_wildcards_match(self):
        doc = {"effects": {"propSfx": {"list": {
            "ls_tail_l_fx": {"nameParent": "ls_tail_l", "list": {"light": {"nameParent": "ls_tail_l"}}, "__type": "sfx_group"},
            "exhaust": {"emitters2": {"Smoke": {"nameParent": "sfx_exhaust_*"}}},
            "lost": {"nameParent": "ls_reverse_l", "__type": "sfx_group"}}}, "__type": "EffectsSettings"}}
        rows = [f for f in bro_lint.lint_truck(doc, model=dump_truck("BoneSandCap_cdt")) if f["code"] == "RC025"]
        self.assertEqual(len(rows), 1)
        self.assertIn("ls_reverse_l", rows[0]["message"])
        self.assertNotIn("sfx_exhaust", rows[0]["message"])


if __name__ == "__main__":
    unittest.main()
