import unittest
from roadcraft.vehicle import wheel_contact_metrics


class WheelContactMetricsTests(unittest.TestCase):
    def test_compiled_apoc_dimensions_keep_absolute_offset(self):
        result = wheel_contact_metrics({'radius': .3977, 'mass': 35, 'radiusOffset': .085}, body_mass=1250)
        self.assertAlmostEqual(result['radiusOffsetFraction'], .2137289414)
        self.assertAlmostEqual(result['wheelBodyMassRatio'], .028)
        self.assertFalse(result['visualStabilization']['enabled'])

    def test_compiled_stock_reference(self):
        result = wheel_contact_metrics({'radius': .448, 'mass': 125, 'radiusOffset': .045}, body_mass=1974)
        self.assertAlmostEqual(result['radiusOffsetFraction'], .1004464286)
        self.assertAlmostEqual(result['wheelBodyMassRatio'], .0633232016)

    def test_visual_stabilization_uses_native_sdk_defaults(self):
        r = wheel_contact_metrics({'radius': .4, 'mass': 80, 'isWheelStabilizationEnabled': True})
        self.assertEqual(r['visualStabilization'], {'enabled': True, 'physicalThroughKmh': 15., 'stabilizedFromKmh': 30.})
        self.assertNotIn('wheelBodyMassRatio', r)

    def test_invalid_enabled_transition_rejected(self):
        for low,high in ((30,15),(15,15),(-1,30)):
            with self.subTest(low=low,high=high), self.assertRaises(ValueError):
                wheel_contact_metrics({'radius': .4,'mass':80,'isWheelStabilizationEnabled':True,
                                       'maxSpeedFullPhysWheel':low,'maxSpeedFullFakeWheel':high})

    def test_disabled_transition_does_not_claim_a_physics_fault(self):
        r=wheel_contact_metrics({'radius': .4,'mass':35,'maxSpeedFullPhysWheel':30,'maxSpeedFullFakeWheel':15})
        self.assertFalse(r['visualStabilization']['enabled'])

    def test_invalid_physical_inputs_rejected(self):
        for update in ({'radius':0},{'mass':-1},{'mass':True},{'radiusOffset':float('nan')},
                       {'maxSpeedFullPhysWheel':float('inf')},{'isWheelStabilizationEnabled':1}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                wheel_contact_metrics({'radius':.4,'mass':80,**update})

    def test_invalid_body_mass_rejected(self):
        for mass in (0,-1,True,float('inf')):
            with self.subTest(mass=mass), self.assertRaises(ValueError):
                wheel_contact_metrics({'radius':.4,'mass':80},body_mass=mass)
