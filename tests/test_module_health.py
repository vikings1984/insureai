import unittest
from module_health import build_health

class ModuleHealthTests(unittest.TestCase):
    def test_high_error_rate_has_high_priority(self):
        doc = {'modules': [{'module': 'trust', 'review_count': 8, 'error_count': 5, 'error_rate': 0.625, 'confidence': 0.9}]}
        out = build_health(doc)
        trust = next(x for x in out['modules'] if x['module'] == 'trust')
        self.assertEqual(trust['health'], 'critical')
        self.assertGreaterEqual(trust['optimization_priority'], 60)
        self.assertEqual(out['priority_order'][0], 'trust')

    def test_no_feedback_does_not_claim_health(self):
        out = build_health({'modules': []})
        row = next(x for x in out['modules'] if x['module'] == 'event')
        self.assertEqual(row['health'], 'no_signal')
        self.assertEqual(row['optimization_priority'], 0)

    def test_unknown_module_is_ignored(self):
        out = build_health({'modules': [{'module': 'new_module', 'error_count': 3, 'error_rate': 1.0, 'confidence': 1.0}]})
        self.assertNotIn('new_module', [x['module'] for x in out['modules']])

if __name__ == '__main__':
    unittest.main()
