import unittest
from roadcraft.native_cockpit import cockpit_animation_report
class CockpitContracts(unittest.TestCase):
    def setUp(self):
        self.p={'prop_cockpit_dashboard':{'elements':{'wheel':{'nameBone':'wheel'}}},
                'prop_wipers_controller':{'forwardAnimation':'out','backwardAnimation':'back'}}
    def report(self, nodes=('wheel',), clips=('out','back')):
        return cockpit_animation_report(self.p,nodes,clips)
    def test_complete(self):self.assertTrue(self.report()['passed'])
    def test_missing_bone(self):self.assertIn('Missing cockpit target: wheel',self.report(nodes=())['issues'])
    def test_missing_second_bone(self):
        self.p['prop_cockpit_dashboard']['elements']['wheel']['nameBoneSecond']='other'
        self.assertFalse(self.report()['passed'])
    def test_missing_clip(self):self.assertFalse(self.report(clips=('out',))['passed'])
    def test_duplicate_clip(self):
        self.p['prop_wipers_controller']['backwardAnimation']='out'
        self.assertFalse(self.report()['passed'])
    def test_competing_drivers(self):
        self.p['prop_cockpit_dashboard']['elements']['other']={'nameBone':'wheel'}
        self.assertFalse(self.report()['passed'])
    def test_missing_controller(self):
        del self.p['prop_wipers_controller'];self.assertFalse(self.report()['passed'])
