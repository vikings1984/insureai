import unittest
from change_impact import compare_intelligence

class ChangeImpactTests(unittest.TestCase):
    def test_decision_escalation_is_high_risk(self):
        old = {'events': [{'event_id': 'e1', 'decision': {'urgency': 'watch'}, 'trust': {'level': 'high'}, 'temporal': {'phase': 'forming'}}]}
        new = {'events': [{'event_id': 'e1', 'decision': {'urgency': 'now'}, 'trust': {'level': 'high'}, 'temporal': {'phase': 'accelerating'}}]}
        out = compare_intelligence(old, new)
        self.assertTrue(out['baseline_available'])
        self.assertEqual(out['impacted_count'], 1)
        self.assertEqual(out['impacted_events'][0]['risk'], 'high')

    def test_trust_degradation_is_medium_risk(self):
        old = {'events': [{'event_id': 'e1', 'decision': {'urgency': 'watch'}, 'trust': {'level': 'high'}, 'temporal': {'phase': 'forming'}}]}
        new = {'events': [{'event_id': 'e1', 'decision': {'urgency': 'watch'}, 'trust': {'level': 'low'}, 'temporal': {'phase': 'forming'}}]}
        out = compare_intelligence(old, new)
        self.assertEqual(out['impacted_events'][0]['risk'], 'medium')

    def test_first_build_is_not_fake_impact(self):
        out = compare_intelligence({}, {'events': []})
        self.assertFalse(out['baseline_available'])
        self.assertEqual(out['impacted_count'], 0)

if __name__ == '__main__':
    unittest.main()
