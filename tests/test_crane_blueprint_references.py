import unittest
from roadcraft import bro_lint, ps_format

class CraneReferencesTests(unittest.TestCase):
    def graph(self, **kw):
        return {"nodes":{"Crane":{"__type":"BlueprintNodeOnCraneArrowPositionChanged", **kw}}}
    def findings(self, graph, model=("Turret", "Tip"), compiled=False, markup=None):
        doc={"blueprint":graph} if not compiled else {}
        text=ps_format.dumps({"properties":{"prop_blueprints":graph},"__type":"truck_view"}) if compiled else None
        return [f for f in bro_lint.lint_truck(doc, model=model, compiled_class=text, markup=markup) if f["code"]=="RC045"]
    def test_stale_donor_bodies_in_source_and_compiled(self):
        for compiled in (False,True):
            with self.subTest(compiled=compiled):
                f=self.findings(self.graph(rootBodyName="BoneCabin_cdt",hookBodyName="BoneCraneSeg2_cdt"),compiled=compiled)
                self.assertEqual(2,len(f));self.assertTrue(all(x["severity"]=="error" for x in f))
    def test_correct_names(self):
        self.assertEqual([],self.findings(self.graph(rootBodyName="Turret",hookBodyName="Tip")))
    def test_model_unknown_defers(self):
        self.assertEqual([],self.findings(self.graph(rootBodyName="Missing"),model=None))
    def test_omitted_empty_and_other_node_fields_do_not_fail(self):
        self.assertEqual([],self.findings(self.graph(rootBodyName="",hookBodyName="")))
        self.assertEqual([],self.findings({"nodes":{"Other":{"__type":"BlueprintNodeCloneSoundEmitter","rootBodyName":"Other"}}}))
    def test_explicit_stale_joint_only_when_markup_available(self):
        g=self.graph(rootBodyName="Turret",hookBodyName="Tip",xConstraintName="cabin")
        self.assertEqual([],self.findings(g))
        m={"objectInfos":[{"entities":[{"name":"Slew","__type":"tpl_markup_constraint_hinge"}]}]}
        self.assertEqual(1,len(self.findings(g,markup=m)))
        g["nodes"]["Crane"]["xConstraintName"]="Slew"
        self.assertEqual([],self.findings(g,markup=m))
