import unittest,math
from roadcraft.bench_stability import phase_stability

PLAN={'duration':10,'steps':[(0,(0,0,'On','AUTO')),(2,(.35,0,'Off','AUTO')),(8,(0,0,'On','AUTO'))],'names':['rest','forward','final']}
def row(t,pedal,brake,x=0,z=0,yaw=0):
 a=math.radians(yaw)
 return {'t':t,'pedal':pedal,'steer':0,'engine':{'handbrake':brake},'bodies':{'hull':{'pos':[x,0,z],'fwd':[math.sin(a),0,math.cos(a)]}},'wheels':[]}
def measure(rows,plan=PLAN,**extra):
 return phase_stability(rows,plan,'hull',observed_windows=True,include_pedal_ramp=True,settle_seconds=0,end_margin_seconds=0,**extra)
class BrakeBoundedTests(unittest.TestCase):
 def test_ramp_launch_is_included(self):
  rows=[row(0,0,True),row(1.8,.01,False),row(3,.15,False,x=.5,z=1,yaw=20),row(4,.35,False,x=1,z=2,yaw=20),row(7,.35,False,x=2,z=5,yaw=20),row(8,.2,True,x=2,z=5,yaw=20),row(9,0,True)]
  r=measure(rows)['forward']
  self.assertEqual(r['windowSeconds'],[1.8,7])
  self.assertEqual(r['windowBasis'],'observed-handbrake-bounded')
  self.assertEqual(r['lateralMaxM'],2)
  self.assertAlmostEqual(r['yawRangeDeg'],20)
  old=phase_stability(rows,PLAN,'hull',observed_windows=True,settle_seconds=0,end_margin_seconds=0)['forward']
  self.assertAlmostEqual(old['yawRangeDeg'],0)
 def test_constant_input_preserves_previous_measurement(self):
  rows=[row(0,0,True),row(2,.35,False),row(7,.35,False,1,6,10),row(8,0,True),row(9,0,True)]
  new=measure(rows)['forward'];old=phase_stability(rows,PLAN,'hull',observed_windows=True,settle_seconds=0,end_margin_seconds=0)['forward']
  for key in ('windowSeconds','distanceM','lateralMaxM','yawRangeDeg'):self.assertEqual(new[key],old[key])
 def test_target_pedal_must_be_observed(self):
  rows=[row(0,0,True),row(2,.1,False),row(7,.2,False,1,6,10),row(8,0,True)]
  self.assertEqual(measure(rows)['forward']['status'],'insufficient_samples')
 def test_full_pedal_requires_its_own_seed(self):
  plan=dict(PLAN,steps=[(0,(0,0,'On','AUTO')),(2,(1,0,'Off','AUTO')),(8,(0,0,'On','AUTO'))])
  rows=[row(2,.35,False),row(7,.35,False,1,6,10)]
  self.assertEqual(measure(rows,plan)['forward']['status'],'insufficient_samples')
 def test_non_bracketed_or_turning_protocol_rejected(self):
  for plan in ({'duration':10,'steps':[(0,(.35,0,'Off','AUTO')),(4,(0,0,'Off','AUTO'))],'names':['forward','coast']},
               {'duration':10,'steps':[(0,(.35,.5,'Off','AUTO'))],'names':['turn']}):
   with self.assertRaises(ValueError):measure([],plan)
 def test_missing_brake_telemetry_cannot_bridge_window(self):
  rows=[row(2,.35,False),row(4,.35,False,1,3),row(7,.35,False,2,6)]
  rows[1]['engine']={}
  self.assertEqual(measure(rows)['forward']['status'],'ambiguous_observed_phase')
if __name__=='__main__':unittest.main()
