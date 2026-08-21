#!/usr/bin/env python3
import unittest
from action_triggers import build_triggers


class TestActionTriggers(unittest.TestCase):
    def test_multiscenario_matrix_creates_advisory_triggers(self):
        matrix = {
            "results": [{
                "event_id": "e1",
                "scenario_count": 2,
                "scenarios": ["trend_accelerates", "trend_cools"],
                "robust_actions": [
                    {"action_id": "evidence_refresh", "label": "持续刷新证据", "robust": True},
                    {"action_id": "exposure_mapping", "label": "做影响暴露映射", "robust": True},
                ],
            }]
        }
        result = build_triggers(matrix)
        self.assertEqual(result["trigger_count"], 2)
        for row in result["results"]:
            self.assertEqual(row["automation"], "advisory_only")
            self.assertEqual(row["status"], "monitor")
            self.assertIn("escalate", row["trigger"])
            self.assertIn("deescalate", row["trigger"])
            self.assertIn("stop", row["trigger"])

    def test_single_scenario_never_creates_trigger(self):
        matrix = {
            "results": [{
                "event_id": "e2",
                "scenario_count": 1,
                "scenarios": ["trend_accelerates"],
                "robust_actions": [{"action_id": "evidence_refresh", "robust": True}],
            }]
        }
        result = build_triggers(matrix)
        self.assertEqual(result["trigger_count"], 0)


if __name__ == "__main__":
    unittest.main()
