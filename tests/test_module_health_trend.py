import unittest
from module_health_trend import build_trend, append_snapshot


class ModuleHealthTrendTests(unittest.TestCase):
    def test_no_baseline_is_explicit(self):
        current = {"modules": [{"module": "trust", "error_rate": 0.1, "health": "healthy", "optimization_priority": 10}]}
        result = build_trend(current, {"snapshots": []})
        self.assertFalse(result["baseline_available"])
        self.assertEqual(result["modules"]["trust"]["direction"], "baseline")

    def test_worsening_and_improving(self):
        current = {"modules": [
            {"module": "trust", "error_rate": 0.4, "health": "watch", "optimization_priority": 40},
            {"module": "claims", "error_rate": 0.1, "health": "healthy", "optimization_priority": 10},
        ]}
        history = {"snapshots": [{"modules": {
            "trust": {"error_rate": 0.2, "health": "healthy", "priority": 20},
            "claims": {"error_rate": 0.2, "health": "healthy", "priority": 20},
        }}]}
        result = build_trend(current, history)
        self.assertEqual(result["modules"]["trust"]["direction"], "worsening")
        self.assertEqual(result["modules"]["claims"]["direction"], "improving")

    def test_history_is_bounded(self):
        current = {"modules": [{"module": "trust", "error_rate": 0.1}]}
        history = {"snapshots": [{} for _ in range(100)]}
        result = append_snapshot(current, history)
        self.assertEqual(len(result["snapshots"]), 90)


if __name__ == "__main__":
    unittest.main()
