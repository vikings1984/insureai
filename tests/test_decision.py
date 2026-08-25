import unittest
from decision import build_decisions


class DecisionTests(unittest.TestCase):
    def setUp(self):
        self.event = {
            'event_id': 'evt_1',
            'event_type': 'regulatory',
            'topic': 'regulatory_change',
            'scores': {'intelligence_score': 86},
            'trust': {'level': 'high', 'conflict': False},
            'evidence_coverage': 100,
            'evidence_status': 'cross_checked',
        }

    def test_accelerating_high_trust_can_be_now(self):
        out = build_decisions([self.event], {'topic_signals': [{'topic': 'regulatory_change', 'phase': 'accelerating', 'signal_strength': 90}]})
        self.assertEqual(out[0]['urgency'], 'now')
        self.assertEqual(out[0]['urgency_label'], '高')
        self.assertFalse(out[0]['human_review_required'])

    def test_conflict_downgrades_to_watch(self):
        event = dict(self.event, trust={'level': 'high', 'conflict': True})
        out = build_decisions([event], {'topic_signals': [{'topic': 'regulatory_change', 'phase': 'accelerating', 'signal_strength': 90}]})
        self.assertEqual(out[0]['urgency'], 'watch')
        self.assertTrue(out[0]['human_review_required'])

    def test_low_evidence_never_reaches_now(self):
        event = dict(self.event, evidence_coverage=50, evidence_status='single_source')
        out = build_decisions([event], {'topic_signals': [{'topic': 'regulatory_change', 'phase': 'accelerating', 'signal_strength': 90}]})
        self.assertEqual(out[0]['urgency'], 'watch')
        self.assertTrue(out[0]['human_review_required'])

    def test_guardrail_is_present(self):
        out = build_decisions([self.event])
        self.assertIn('不替代承保', out[0]['guardrail'])


if __name__ == '__main__':
    unittest.main()
