import copy,unittest
from roadcraft.native_trails import custom_trail_report

class NativeTrailTests(unittest.TestCase):
    def setUp(self):
        effect={'visuals':{'texture':{'nameTex':'height'}},'trailParams':{'width':[0,.28],
                'typeParams':{'projection':{'normalMap':'normal','heightMap':'height','maskTex':'mask'}}}}
        desc={'type':{'properties':{'sfx':{'list':{'wheel_trail':effect}}}}}
        self.prop={'trailSfxDesc':desc,'defaultTrailSfxDesc':copy.deepcopy(desc)}
        self.sizes={k:(256,2048) for k in ['height','normal','mask']}
    def report(self,**kwargs):
        return custom_trail_report(self.prop,self.sizes,width_metres=.28,repeat_metres=2.24,**kwargs)
    def test_native_repeat_and_matching_reset(self):
        result=self.report();self.assertEqual(result['status'],'PASS');self.assertAlmostEqual(result['repeatMetres'],2.24)
    def test_missing_default_loses_mod_artwork(self):
        del self.prop['defaultTrailSfxDesc'];self.assertEqual(self.report()['status'],'FAIL')
        self.assertEqual(self.report(require_mod_reset=False)['status'],'PASS')
    def test_default_with_correct_maps_but_wrong_width_still_fails(self):
        self.prop['defaultTrailSfxDesc']['type']['properties']['sfx']['list']['wheel_trail']['trailParams']['width']=[0,.5]
        self.assertEqual(self.report()['status'],'FAIL')
    def test_wrong_diffuse_aspect_is_not_fixed_by_projection_height(self):
        for desc in self.prop.values():
            effect=desc['type']['properties']['sfx']['list']['wheel_trail']
            del effect['visuals'];effect['trailParams']['typeParams']['projection']['height']=2.24
        self.assertEqual(self.report()['status'],'FAIL')
    def test_dimension_mismatch_and_wrong_aspect(self):
        self.sizes['mask']=(128,1024);self.assertEqual(self.report()['status'],'FAIL')
        self.sizes={k:(256,256) for k in self.sizes};self.assertEqual(self.report()['status'],'FAIL')
    def test_invalid_numbers_and_incomplete_data(self):
        for bad in [0,-1,float('nan'),float('inf'),True]:
            with self.assertRaises(ValueError):custom_trail_report({}, {},width_metres=bad,repeat_metres=1)
        self.assertEqual(custom_trail_report({}, {},width_metres=1,repeat_metres=1)['status'],'FAIL')

if __name__=='__main__':unittest.main()
