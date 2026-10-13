"""RC049: a long standstill-to-neutral delay keeps the old direction after a stop."""
import unittest

from roadcraft.bro_lint import lint_truck


def doc(delay):
    return {"truckSettings": {"maxSteerSpeed": .03, "backSteerSpeed": .06, "pedalsResponsiveness": .2,
                              "gearbox": {"params": {"neutralGearSwitchingDelay": delay}}}}


class NeutralDelayTest(unittest.TestCase):
    def codes(self, delay):
        return {f["code"] for f in lint_truck(doc(delay))}

    def test_long_delay_warns(self):
        self.assertIn("RC049", self.codes(60))

    def test_retail_delays_pass(self):
        for delay in (0, .5, 3):
            self.assertNotIn("RC049", self.codes(delay))


if __name__ == "__main__":
    unittest.main()
