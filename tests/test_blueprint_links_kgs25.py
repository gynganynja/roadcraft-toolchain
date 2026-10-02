import unittest
from roadcraft.blueprint_links import graph_link_report

class ClosedGraphTests(unittest.TestCase):
    def test_missing_callback_and_input(self):
        graph={'nodes':{'Emitter':{'Output':['Missing/emitterRef/cb','Gone/Input']}}}
        report=graph_link_report(graph)
        self.assertFalse(report['passed'])
        self.assertEqual([r['missingNode'] for r in report['missingDestinations']],['Missing','Gone'])

    def test_closed_graph_with_resource_and_label(self):
        graph={'nodes':{'Emitter':{'Output':['Sound/emitterRef/cb'],'label':'a/b',
            'resources':['res://sounds/a.resource']},'Sound':{'Output':['Emitter/Input']}}}
        self.assertTrue(graph_link_report(graph)['passed'])

    def test_nested_array_path(self):
        report=graph_link_report({'nodes':{'A':{'parameters':[{'links':['B/Play']}]}}})
        self.assertEqual(report['missingDestinations'][0]['path'],'nodes.A.parameters[0].links[0]')

if __name__=='__main__':unittest.main()
