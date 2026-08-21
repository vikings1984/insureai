import unittest

from optimization_backlog import build_backlog


class OptimizationBacklogTests(unittest.TestCase):
    def test_worsening_module_gets_actionable_item(self):
        trend = {
            "baseline_available": True,
            "modules": {
                "trust": {
                    "direction": "worsening",
                    "health": "critical",
                    "error_rate": 0.6,
                    "error_rate_delta": 0.1,
                    "priority": 40,
                }
            },
        }
        result = build_backlog(trend)
        self.assertEqual(len(result["items"]), 1)
        item = result["items"][0]
        self.assertEqual(item["module"], "trust")
        self.assertEqual(item["automation"], "advisory_only")
        self.assertIn("source independence", item["optimization_action"])

    def test_improving_module_does_not_create_noise(self):
        trend = {
            "baseline_available": True,
            "modules": {
                "event": {
                    "direction": "improving",
                    "health": "healthy",
                    "error_rate": 0.05,
                    "error_rate_delta": -0.1,
                    "priority": 5,
                }
            },
        }
        result = build_backlog(trend)
        self.assertEqual(result["items"], [])

    def test_dedupe_key_is_stable(self):
        trend = {
            "baseline_available": True,
            "modules": {
                "claims": {
                    "direction": "worsening",
                    "health": "watch",
                    "error_rate": 0.3,
                    "error_rate_delta": 0.08,
                    "priority": 20,
                }
            },
        }
        a = build_backlog(trend)["items"][0]
        b = build_backlog(trend)["items"][0]
        self.assertEqual(a["backlog_id"], b["backlog_id"])
        self.assertEqual(a["dedupe_key"], "claims:worsening")


if __name__ == "__main__":
    unittest.main()
