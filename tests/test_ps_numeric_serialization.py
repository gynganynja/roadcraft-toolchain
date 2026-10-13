import math
import re
import unittest
from roadcraft import ps_format


class PsNumericSerializationTests(unittest.TestCase):
    def test_native_class_small_motor_value_is_decimal(self):
        doc = {"properties": {"prop_truck_rb": {"engine": {"params": {"maxDeltaAngVel": 0.00002}}}}}
        text = ps_format.dumps(doc)
        self.assertIn("maxDeltaAngVel = 0.00002", text)
        self.assertEqual(ps_format.loads(text), doc)

    def test_exponent_extremes_round_trip_without_exponent_tokens(self):
        values = [1e-8, -2e-5, 1e20, -1.25e30, 5e-324, 1.7976931348623157e308]
        text = ps_format.dumps({"values": values})
        self.assertIsNone(re.search(r"[0-9][eE][+-]?[0-9]", text))
        self.assertEqual(ps_format.loads(text)["values"], values)
        self.assertTrue(all(isinstance(x, float) for x in ps_format.loads(text)["values"]))

    def test_regular_numbers_and_signed_zero_remain_floats(self):
        values = [0.0, -0.0, 1.0, 0.1, -0.125, 1200.0]
        parsed = ps_format.loads(ps_format.dumps({"values": values}))["values"]
        self.assertEqual(parsed, values)
        self.assertEqual(math.copysign(1, parsed[1]), -1)
        self.assertTrue(all(isinstance(x, float) for x in parsed))

    def test_nonfinite_values_are_rejected(self):
        for value in (float("nan"), float("inf"), -float("inf")):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "finite"):
                ps_format.dumps({"value": value})

    def test_reader_retains_historical_exponent_support(self):
        self.assertEqual(ps_format.loads("value = 2e-05"), {"value": 0.00002})
