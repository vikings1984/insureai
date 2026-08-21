import unittest

from feedback_attribution import attribute_case, build_attribution


class FeedbackAttributionTests(unittest.TestCase):
    def test_conflict_maps_to_trust(self):
        out = attribute_case({'reasons': [{'type': 'conflict'}]})
        self.assertEqual(out['module'], 'trust')
        self.assertGreaterEqual(out['confidence'], 0.6)

    def test_evidence_maps_to_claims(self):
        out = attribute_case({'reasons': [{'type': 'evidence'}]})
        self.assertEqual(out['module'], 'claims')

    def test_unknown_does_not_fabricate_root_cause(self):
        out = attribute_case({'reasons': []})
        self.assertEqual(out['module'], 'unknown')
        self.assertEqual(out['confidence'], 0.0)

    def test_empty_feedback_has_zero_module_rates(self):
        out = build_attribution({'labels': []}, {'items': []})
        self.assertEqual(out['reviewed_count'], 0)
        self.assertEqual(out['modules']['trust']['error_rate'], 0.0)


if __name__ == '__main__':
    unittest.main()
