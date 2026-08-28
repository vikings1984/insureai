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

    def test_kg_empty_graph_is_critical(self):
        out = build_health({'modules': []}, kg_stats={'node_count': 0, 'edge_count': 0})
        kg = next(x for x in out['modules'] if x['module'] == 'knowledge_graph')
        self.assertEqual(kg['health'], 'critical')
        self.assertEqual(kg['optimization_priority'], 100)
        self.assertEqual(out['priority_order'][0], 'knowledge_graph')

    def test_kg_healthy_graph_from_stats(self):
        out = build_health({'modules': []}, kg_stats={'node_count': 9251, 'edge_count': 12318, 'event_count': 1492, 'latest_event_at': '2026-08-27T06:00:34Z'})
        kg = next(x for x in out['modules'] if x['module'] == 'knowledge_graph')
        self.assertEqual(kg['health'], 'healthy')
        self.assertEqual(kg['node_count'], 9251)
        self.assertEqual(kg['edge_count'], 12318)
        self.assertEqual(kg['latest_event_at'], '2026-08-27T06:00:34Z')

    def test_kg_absent_stats_stays_no_signal(self):
        out = build_health({'modules': []})
        kg = next(x for x in out['modules'] if x['module'] == 'knowledge_graph')
        self.assertEqual(kg['health'], 'no_signal')
        self.assertEqual(kg['optimization_priority'], 0)

if __name__ == '__main__':
    unittest.main()
