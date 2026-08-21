import unittest
from execution_readiness import build_readiness

class ExecutionReadinessTests(unittest.TestCase):
    def test_human_review_gate(self):
        out = build_readiness({'results': [{'event_id': 'e1', 'action_id': 'evidence_refresh', 'action_label': 'refresh', 'scenario_count': 3, 'owner_roles': ['executive'], 'trigger': {'start': 'now'}}]})
        self.assertEqual(out['pack_count'], 1)
        row = out['results'][0]
        self.assertEqual(row['status'], 'ready_for_human_review')
        self.assertEqual(row['readiness_gate'], 'human_confirmation_required')
        self.assertEqual(row['automation'], 'advisory_only')

    def test_preserve_owner_trigger_and_deadline(self):
        out = build_readiness({'results': [{'event_id': 'e1', 'action_id': 'exposure_mapping', 'action_label': 'map', 'scenario_count': 2, 'owner_roles': ['product', 'underwriting'], 'trigger': {'escalate': 'new evidence'}}]})
        row = out['results'][0]
        self.assertEqual(row['scenario_count'], 2)
        self.assertEqual(row['owner_roles'], ['product', 'underwriting'])
        self.assertEqual(row['trigger']['escalate'], 'new evidence')
        self.assertEqual(row['deadline'], 'within_5_business_days')
        self.assertIn('human', row['approval_boundary'])

if __name__ == '__main__':
    unittest.main()
