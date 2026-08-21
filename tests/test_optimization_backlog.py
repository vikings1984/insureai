import unittest
from optimization_backlog import build_backlog

class OptimizationBacklogTests(unittest.TestCase):
    def test_worsening_module_generates_deduped_item(self):
        out = build_backlog({'baseline_available': True, 'modules': {'trust': {'direction':'worsening','health':'watch','error_rate':0.3,'error_rate_delta':0.08,'priority':40}}})
        self.assertEqual(len(out['items']), 1)
        item = out['items'][0]
        self.assertEqual(item['module'], 'trust')
        self.assertEqual(item['automation'], 'advisory_only')
        self.assertEqual(item['dedupe_key'], 'quality:trust')
        self.assertTrue(item['backlog_id'] == 'quality-trust')

    def test_stable_healthy_module_does_not_create_noise(self):
        out = build_backlog({'baseline_available': True, 'modules': {'trust': {'direction':'stable','health':'healthy','error_rate':0.1,'priority':5}}})
        self.assertEqual(out['items'], [])

if __name__ == '__main__':
    unittest.main()
