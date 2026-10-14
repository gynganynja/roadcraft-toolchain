import unittest
from roadcraft.bro_lint import wheel_model_references

class WheelModelReferenceTests(unittest.TestCase):
    def test_enabled_missing_tyre_is_startup_error(self):
        result = wheel_model_references({"deformEnable": True}, ["rim", "jimny_tire"])
        self.assertEqual([(x["code"], x["severity"]) for x in result], [("RC049", "error")])
    def test_default_native_tyre_is_present(self):
        self.assertEqual(wheel_model_references({"deformEnable": True}, ["rim", "tire"]), [])
    def test_disabled_deformation_does_not_require_tyre(self):
        self.assertEqual(wheel_model_references({"deformEnable": False}, ["rim"]), [])
    def test_explicit_supported_custom_name(self):
        self.assertEqual(wheel_model_references({"deformEnable": True}, ["my_tyre"], tire_name="my_tyre"), [])
