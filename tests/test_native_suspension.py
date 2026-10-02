import unittest
from roadcraft.native_suspension import (calibrate_beta, design_axle, native_axle_report, position_from_travel,
                                         rest_report, stop_positions, travel_has_reserve)
from roadcraft.vehicle import axle_report

class NativeSuspensionTests(unittest.TestCase):
    def test_v2_extension_limit_is_exceeded_by_measured_beta_case(self):
        axle=dict(min=-.09,max=.19,height=.18,strength=.03115)
        report=native_axle_report(axle,.28)
        self.assertTrue(report['cases']['measured']['onDroopStop'])
        self.assertFalse(travel_has_reserve(.000564776,.280000001))

    def test_v3_has_predicted_and_measured_reserve(self):
        report=native_axle_report(dict(min=-.22,max=.12,height=.18,strength=.03115),.28)
        self.assertTrue(all(not c['onBumpStop'] and not c['onDroopStop'] for c in report['cases'].values()))
        for travel in [.093343690,.096716046,.141080141,.144484073]:
            self.assertTrue(travel_has_reserve(travel,.340000004))

    def test_invalid_telemetry_cannot_pass(self):
        for value in [float('nan'),float('inf')]:
            with self.assertRaises(ValueError):travel_has_reserve(value,.34)
        self.assertFalse(travel_has_reserve(-.01,.34))
        self.assertFalse(travel_has_reserve(.35,.34))

class StopGeometryTests(unittest.TestCase):
    """Wheel position = height + min + travel below the modelled place (KGS25 bench, Lada trials)."""

    def test_lada_rear_rests_at_one_place_in_both_trials(self):
        trial1 = dict(min=-.09, max=.19, height=.18, strength=.03115)
        trial2 = dict(min=-.22, max=.12, height=.18, strength=.03115)
        rear1 = position_from_travel(trial1, .013078159)
        rear2 = position_from_travel(trial2, .144484073)
        self.assertAlmostEqual(rear1, rear2, delta=.003)
        # front sat on the trial-1 top stop: its trial-2 rest lies above that stop
        self.assertLess(position_from_travel(trial2, .096716046), stop_positions(trial1)['top'])

    def test_kgs25_contacts_and_idlers(self):
        contact = dict(min=0, max=.22, height=.05, strength=.0013)
        self.assertAlmostEqual(position_from_travel(contact, .0597), .1097, places=4)   # probe: 0.1098
        idler = dict(min=-.15, max=0, height=0, strength=.9)
        self.assertAlmostEqual(position_from_travel(idler, .15), 0.0, places=6)        # hangs as modelled
        self.assertAlmostEqual(stop_positions(idler)['top'], -.15)                    # can rise 0.15 m

    def test_defaults_and_invalid(self):
        self.assertEqual(stop_positions({}), {'top': 0.0, 'bottom': 1.0, 'travel': 1.0})
        with self.assertRaises(ValueError):
            stop_positions(dict(min=.2, max=.1))
        with self.assertRaises(ValueError):
            position_from_travel(dict(min=0, max=.22), .3)

class MeasuredDesignTests(unittest.TestCase):
    """Design and calibration with the stops at height + min / height + max (Inferred design rule)."""

    def test_design_rests_as_asked_between_the_stops(self):
        axle = design_axle(.16, .205, lift=.06, bump=.16, droop=.2)
        self.assertEqual((axle['min'], axle['max'], axle['height']), (-.32, .04, .22))
        case = rest_report(axle, .205)['cases']['expected']
        self.assertAlmostEqual(case['rest'], .06, places=3)
        self.assertAlmostEqual(case['bumpRoom'], .16, places=3)
        self.assertAlmostEqual(case['droopRoom'], .2, places=3)
        with self.assertRaises(ValueError):
            design_axle(0, .2)

    def test_retail_scout_rests_off_its_stops_only_with_measured_geometry(self):
        armiger = dict(min=-.42, max=-.05, height=.275, strength=.016)   # front, 1974 kg
        case = rest_report(armiger, .25)['cases']['expected']
        self.assertFalse(case['onBumpStop'] or case['onDroopStop'])
        self.assertLess(abs(case['rest']), .01)
        self.assertTrue(axle_report(armiger, .25)['cases']['expected']['onDroopStop'])

    def test_calibration_refuses_rests_on_measured_stops(self):
        roamer = [{"axle": dict(min=-.4, max=.4, height=.265, strength=.017), "rest": .142, "wheels": 2},
                  {"axle": dict(min=-.4, max=.4, height=.23, strength=.03), "rest": .142, "wheels": 2}]
        self.assertAlmostEqual(calibrate_beta(roamer)['beta'], 105.7, delta=.1)
        on_top_stop = [{"axle": dict(min=-.1, max=.26, height=.22, strength=.0221), "rest": .12, "wheels": 4}]
        with self.assertRaises(ValueError):
            calibrate_beta(on_top_stop)

if __name__=='__main__':unittest.main()
