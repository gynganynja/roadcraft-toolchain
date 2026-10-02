import unittest
from roadcraft.native_visibility import markup_visibility_report

class VisibilityTests(unittest.TestCase):
    def test_nested_unresolved_hidden_alias(self):
        markup = {'objectInfos': {'emitter': {'flags': [{'visibility': {'__type': 'invisible'}}]}}}
        result = markup_visibility_report(markup)
        self.assertFalse(result['passed'])
        self.assertIn('/objectInfos/emitter/flags/0/visibility', result['issues'][0])

    def test_concrete_hidden_and_visible_defaults(self):
        for visible in (False, True):
            self.assertTrue(markup_visibility_report({'visibility': {
                '__type': 'tpl_markup_visibility_flags', 'visibleDefault': visible,
                'visibleInReflectionCubemap': False}})['passed'])

    def test_invalid_boolean(self):
        self.assertFalse(markup_visibility_report({'visibility': {
            '__type': 'tpl_markup_visibility_flags', 'visibleDefault': 'false'}})['passed'])

    def test_resolved_custom_alias_is_allowed(self):
        self.assertTrue(markup_visibility_report({'visibility': {'__type': 'invisible'}},
            resolved_visibility_brands=('invisible',))['passed'])

    def test_unrelated_type_is_not_visibility(self):
        self.assertTrue(markup_visibility_report({'other': {'__type': 'invisible'}})['passed'])

if __name__ == '__main__':
    unittest.main()
