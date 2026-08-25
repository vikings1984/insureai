#!/usr/bin/env python3
import unittest

from counterfactual import build_counterfactual


class TestCounterfactual(unittest.TestCase):
    def test_conflict_guardrail_dependency_is_visible(self):
        # Supply otherwise-eligible evidence so the counterfactual isolates the
        # conflict flag rather than being dominated by the evidence boundary.
        data = {
            'events': [{
                'event_id': 'e1',
                'topic': 'regulatory_change',
                'event_type': 'regulatory',
                'scores': {'intelligence_score': 90},
                'evidence_coverage': 100,
                'evidence_status': 'cross_checked',
                'review_required': False,
                'trust': {'level': 'high', 'conflict': True},
            }],
            'temporal': {'topic_signals': [{'topic': 'regulatory_change', 'phase': 'accelerating', 'signal_strength': 90}]},
        }
        result = build_counterfactual(data)
        case = next(x for x in result['cases'] if x['scenario'] == 'remove_conflict_flag')
        self.assertEqual(case['baseline_urgency'], 'watch')
        self.assertEqual(case['counterfactual_urgency'], 'now')
        self.assertTrue(case['changed'])

    def test_empty_input_is_explicit(self):
        result = build_counterfactual({'events': [], 'temporal': {}})
        self.assertEqual(result['total_cases'], 0)
        self.assertEqual(result['fragility_rate'], 0.0)


if __name__ == '__main__':
    unittest.main()
