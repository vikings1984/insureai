#!/usr/bin/env python3
import unittest

from counterfactual import build_counterfactual


class TestCounterfactual(unittest.TestCase):
    def test_conflict_guardrail_is_stable_under_counterfactual(self):
        data = {
            'events': [{
                'event_id': 'e1',
                'topic': 'regulatory_change',
                'event_type': 'regulatory',
                'scores': {'intelligence_score': 90},
                'trust': {'level': 'medium', 'conflict': True},
            }],
            'temporal': {'topic_signals': [{'topic': 'regulatory_change', 'phase': 'accelerating', 'signal_strength': 90}]},
        }
        result = build_counterfactual(data)
        self.assertGreaterEqual(result['total_cases'], 2)
        conflict_case = next(x for x in result['cases'] if x['scenario'] == 'remove_conflict_flag')
        self.assertEqual(conflict_case['baseline_urgency'], 'watch')
        self.assertEqual(conflict_case['counterfactual_urgency'], 'watch')

    def test_empty_input_is_explicit(self):
        result = build_counterfactual({'events': [], 'temporal': {}})
        self.assertEqual(result['total_cases'], 0)
        self.assertEqual(result['fragility_rate'], 0.0)


if __name__ == '__main__':
    unittest.main()
