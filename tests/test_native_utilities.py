import copy
import unittest
from roadcraft.native_utilities import utility_action_report

class UtilityContractTests(unittest.TestCase):
    def setUp(self):
        self.props = {
            'prop_truck_view_actions_mapper': {
                'firstAction': {'namedActionType': 'ACTIVATE_OBJECTIVE_SCANNER'},
                'truckInputConfiguration': {k: True for k in ['isMainActionsMapped', 'isSecondaryActionsMapped', 'isFirstActionModeNeeded', 'isSecondActionModeNeeded']}},
            'prop_objective_scanner': {'objectiveScanner': {'radius': 45}}}
    def test_complete_objective(self):
        self.assertTrue(utility_action_report(self.props, ('objective',))['passed'])
    def test_component_without_control_fails(self):
        self.props['prop_truck_view_actions_mapper']['firstAction'] = {}
        self.assertFalse(utility_action_report(self.props, ('objective',))['passed'])
    def test_control_without_component_fails(self):
        del self.props['prop_objective_scanner']
        self.assertFalse(utility_action_report(self.props, ('objective',))['passed'])
    def test_zero_radius_default_fails(self):
        self.props['prop_objective_scanner'] = {'objectiveScanner': {}}
        self.assertFalse(utility_action_report(self.props, ('objective',))['passed'])
    def test_unrequested_capabilities_not_required(self):
        self.assertTrue(utility_action_report({}, ())['passed'])
    def test_ui_section_disabled_fails(self):
        self.props['prop_truck_view_actions_mapper']['truckInputConfiguration']['isFirstActionModeNeeded'] = False
        self.assertFalse(utility_action_report(self.props, ('objective',))['passed'])
    def test_typo_rejected(self):
        with self.assertRaises(ValueError): utility_action_report(self.props, ('radarr',))

if __name__ == '__main__': unittest.main()
