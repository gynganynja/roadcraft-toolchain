import unittest
from roadcraft import bro_lint, ps_format

class LoadVolumeDependencyTests(unittest.TestCase):
    def codes(self, props, base="truck_view"):
        text = ps_format.dumps({"properties": props, "__type": base})
        return {f["code"] for f in bro_lint.lint_truck({}, compiled_class=text)}

    def test_load_controller_without_route_is_a_startup_error(self):
        self.assertIn("RC033", self.codes({"prop_load_volume_controller": {}}))

    def test_text_mention_does_not_supply_a_property(self):
        self.assertIn("RC033", self.codes({"prop_load_volume_controller": {"label": "prop_route_following"}}))

    def test_explicit_route_satisfies_the_dependency(self):
        self.assertNotIn("RC033", self.codes({"prop_load_volume_controller": {}, "prop_route_following": {}}))

    def test_other_class_base_can_inherit_its_properties(self):
        self.assertNotIn("RC033", self.codes({"prop_load_volume_controller": {}}, "custom_base"))
