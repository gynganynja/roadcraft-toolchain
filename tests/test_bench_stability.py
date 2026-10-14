import math
import unittest
from roadcraft.bench_stability import phase_stability

PLAN={'duration':10,'steps':[(0,(.35,0,'Off','AUTO'))],'names':['forward']}
def sample(t,x,z,yaw,spin=0,brake=False):
    a=math.radians(yaw)
    return {'t':t,'pedal':.35,'steer':0,'engine':{'handbrake':brake},
            'bodies':{'hull':{'pos':[x,0,z],'fwd':[math.sin(a),0,math.cos(a)]}},
            'wheels':[{'spin':spin,'onTerrain':True}]}
class StabilityTests(unittest.TestCase):
    def test_straight_motion_and_sideways_drift_are_separate(self):
        r=phase_stability([sample(2,0,0,0),sample(5,2,3,12),sample(8,1,6,0)],PLAN,'hull')['forward']
        self.assertEqual(r['lateralMaxM'],2)
        self.assertEqual(r['forwardM'],6)
        self.assertAlmostEqual(r['yawRangeDeg'],12)
        self.assertEqual(r['yawChangeDeg'],0)
    def test_world_heading_does_not_change_lateral_distance(self):
        r=phase_stability([sample(2,0,0,90),sample(8,6,1,90)],PLAN,'hull')['forward']
        self.assertAlmostEqual(r['forwardM'],6)
        self.assertAlmostEqual(r['lateralMaxM'],1)
    def test_yaw_wrap_is_not_a_full_spin(self):
        r=phase_stability([sample(2,0,0,179),sample(8,0,1,-179)],PLAN,'hull')['forward']
        self.assertAlmostEqual(r['yawChangeDeg'],2)
    def test_stationary_hull_does_not_hide_wheel_jitter(self):
        r=phase_stability([sample(2,0,0,0,2),sample(8,0,0,0,-4)],PLAN,'hull')['forward']
        self.assertEqual(r['distanceM'],0)
        self.assertEqual(r['wheelSpinMaxRadS'],4)
    def test_missing_telemetry_is_unavailable(self):
        s=[sample(2,0,0,0),sample(8,0,1,0)]
        s[1]['wheels']=[{}]
        r=phase_stability(s,PLAN,'hull')['forward']
        self.assertIsNone(r['wheelSpinMaxRadS'])
        self.assertIsNone(r['onTerrainFraction'])
    def test_wrong_controls_and_transients_are_excluded(self):
        r=phase_stability([sample(0,0,0,0),sample(2,0,0,0,brake=True),sample(9.5,1,0,0)],PLAN,'hull')['forward']
        self.assertEqual(r['status'],'insufficient_samples')
        self.assertEqual(r['n'],0)

    def test_whole_phase_retains_launch_kick(self):
        # The vehicle turns immediately, then travels straight on the new heading.
        s=[sample(.1,0,0,0), sample(2,0,1,20),
           sample(8,3*math.sin(math.radians(20)),1+3*math.cos(math.radians(20)),20)]
        settled=phase_stability(s,PLAN,'hull')['forward']
        whole=phase_stability(s,PLAN,'hull',settle_seconds=0,end_margin_seconds=0)['forward']
        self.assertAlmostEqual(settled['yawRangeDeg'],0)
        self.assertAlmostEqual(settled['lateralMaxM'],0)
        self.assertAlmostEqual(whole['yawRangeDeg'],20)
        self.assertGreater(whole['lateralMaxM'],1)

    def test_missing_or_partial_wheel_row_is_unavailable(self):
        for missing in ([], [{'spin':0, 'onTerrain':True}, {'spin':2, 'onTerrain':False}]):
            with self.subTest(wheels=missing):
                s=[sample(2,0,0,0),sample(8,0,1,0)]
                s[1]['wheels']=missing
                r=phase_stability(s,PLAN,'hull')['forward']
                self.assertIsNone(r['wheelSpinMaxRadS'])
                self.assertIsNone(r['onTerrainFraction'])

    def test_full_pedal_plan_keeps_its_control_filter_separate(self):
        from roadcraft.physics_bench import SCHEDULES
        rows=[sample(14,0,0,0),sample(20,1,4,10),sample(30,2,8,10)]
        for row in rows: row['pedal']=1
        full=phase_stability(rows,SCHEDULES['straightfull'],'hull')['forward']
        partial=phase_stability(rows,SCHEDULES['straight'],'hull')['forward']
        self.assertEqual(full['status'],'measured')
        self.assertEqual(full['lateralMaxM'],2)
        self.assertEqual(partial['status'],'insufficient_samples')


class ObservedWindowTests(unittest.TestCase):
    def test_earlier_launch_is_included_despite_recorder_clock_offset(self):
        plan={'duration':10,'steps':[(2,(.35,0,'Off','AUTO'))],'names':['forward']}
        rows=[sample(1,0,0,0),sample(2,0,1,20),sample(8,2,6,20)]
        nominal=phase_stability(rows,plan,'hull',settle_seconds=0,end_margin_seconds=0)['forward']
        observed=phase_stability(rows,plan,'hull',settle_seconds=0,end_margin_seconds=0,observed_windows=True)['forward']
        self.assertAlmostEqual(nominal['yawRangeDeg'],0)
        self.assertAlmostEqual(observed['yawRangeDeg'],20)
        self.assertEqual(observed['windowSeconds'],[1,8])
        self.assertEqual(observed['lateralMaxM'],2)

    def test_actual_input_end_can_extend_past_scheduled_end(self):
        plan={'duration':5,'steps':[(0,(.35,0,'Off','AUTO'))],'names':['forward']}
        rows=[sample(1,0,0,0),sample(4,0,3,0),sample(6,2,5,15),sample(7,4,8,30,brake=True)]
        r=phase_stability(rows,plan,'hull',settle_seconds=0,end_margin_seconds=0,observed_windows=True)['forward']
        self.assertEqual(r['windowSeconds'],[1,6])
        self.assertEqual(r['lateralMaxM'],2)

    def test_repeated_driving_inputs_stay_separate_across_brake_phase(self):
        plan={'duration':12,'steps':[(0,(.35,0,'Off','AUTO')),(4,(0,0,'On','AUTO')),(8,(.35,0,'Off','REVERSE'))],
              'names':['forward','stop','reverse']}
        a=sample(4,0,2,0,brake=True);a['pedal']=0
        b=sample(7,0,2,0,brake=True);b['pedal']=0
        rows=[sample(.5,0,0,0),sample(3,0,2,0),a,b,sample(7.8,0,2,0),sample(11,1,0,0)]
        r=phase_stability(rows,plan,'hull',settle_seconds=0,end_margin_seconds=0,observed_windows=True)
        self.assertEqual(r['forward']['windowSeconds'],[.5,3])
        self.assertEqual(r['reverse']['windowSeconds'],[7.8,11])

    def test_discontinuous_input_matches_are_not_cherry_picked(self):
        rows=[sample(1,0,0,0),sample(3,1,2,0,brake=True),sample(5,0,4,0)]
        r=phase_stability(rows,PLAN,'hull',observed_windows=True)['forward']
        self.assertEqual(r['status'],'ambiguous_observed_phase')

    def test_settling_is_relative_to_observed_start_and_missing_anchor_fails(self):
        plan={'duration':10,'steps':[(2,(.35,0,'Off','AUTO'))],'names':['forward']}
        rows=[sample(1,0,0,0),sample(3,0,1,20),sample(7,0,5,20),sample(9,0,6,20)]
        r=phase_stability(rows,plan,'hull',observed_windows=True)['forward']
        self.assertEqual(r['windowSeconds'],[3,7])
        absent=phase_stability([sample(11,0,0,0),sample(12,0,1,0)],plan,'hull',observed_windows=True)['forward']
        self.assertEqual(absent['status'],'insufficient_samples')
