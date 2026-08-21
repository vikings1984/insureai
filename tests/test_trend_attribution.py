import unittest
from trend_attribution import build_attribution


class TrendAttributionTests(unittest.TestCase):
    def test_persistent_worsening(self):
        history = {"snapshots": [{"modules": {"trust": {"error_rate": 0.10}}}, {"modules": {"trust": {"error_rate": 0.15}}}, {"modules": {"trust": {"error_rate": 0.20}}}]}
        trend = {"modules": {"trust": {"direction": "worsening"}}}
        result = build_attribution(trend, history)
        self.assertEqual(result["modules"]["trust"]["classification"], "persistent_worsening")

    def test_single_spike(self):
        history = {"snapshots": [{"modules": {"trust": {"error_rate": 0.10}}}]}
        trend = {"modules": {"trust": {"direction": "worsening"}}}
        result = build_attribution(trend, history)
        self.assertEqual(result["modules"]["trust"]["classification"], "single_spike")

    def test_recovery_classification(self):
        history = {"snapshots": [{"modules": {"trust": {"error_rate": 0.30}}}, {"modules": {"trust": {"error_rate": 0.20}}}]}
        trend = {"modules": {"trust": {"direction": "improving"}}}
        result = build_attribution(trend, history)
        self.assertEqual(result["modules"]["trust"]["classification"], "recovering")


if __name__ == "__main__":
    unittest.main()
