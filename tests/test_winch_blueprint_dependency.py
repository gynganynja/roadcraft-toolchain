import unittest
from roadcraft import bro_lint, ps_format

class WinchBlueprintDependencyTests(unittest.TestCase):
    def codes(self, props, base="truck_view"):
        return {f["code"] for f in bro_lint.lint_truck({}, compiled_class=ps_format.dumps({"properties": props, "__type": base}))}

    def test_subscriber_without_winch_is_a_native_startup_error(self):
        self.assertIn("RC034", self.codes({"prop_blueprints": {"graph": {"nodes": {"event": {"__type": "BlueprintNodeOnWinchStateChanged"}}}}}))

    def test_explicit_winch_supplies_the_dependency(self):
        self.assertNotIn("RC034", self.codes({"prop_winch": {}, "prop_blueprints": {"event": {"__type": "BlueprintNodeOnWinchStateChanged"}}}))

    def test_string_mentions_are_not_subscribers_or_components(self):
        self.assertNotIn("RC034", self.codes({"prop_blueprints": {"description": "BlueprintNodeOnWinchStateChanged"}}))
        self.assertIn("RC034", self.codes({"prop_blueprints": {"label": "prop_winch", "event": {"__type": "BlueprintNodeOnWinchStateChanged"}}}))

    def test_custom_base_can_inherit_a_winch(self):
        self.assertNotIn("RC034", self.codes({"prop_blueprints": {"event": {"__type": "BlueprintNodeOnWinchStateChanged"}}}, "custom_base"))

    def test_generated_view_winch_controller_supplies_the_dependency(self):
        self.assertNotIn("RC034", self.codes({"prop_truck_view_winch_controller": {"winch": {"__type": "RbTruckWinch"}},
            "prop_blueprints": {"event": {"__type": "BlueprintNodeOnWinchStateChanged"}}}))

    def test_winchable_target_and_text_mention_do_not_supply_a_controller(self):
        for props in [{"prop_winchable": {}}, {"description": "prop_truck_view_winch_controller"}]:
            with self.subTest(props=props):
                props["prop_blueprints"]={"event": {"__type": "BlueprintNodeOnWinchStateChanged"}}
                self.assertIn("RC034", self.codes(props))
