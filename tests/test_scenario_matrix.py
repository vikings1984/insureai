#!/usr/bin/env python3
import unittest
from scenario_matrix import build_matrix

class TestScenarioMatrix(unittest.TestCase):
    def test_common_actions_are_robust_across_multiple_scenarios(self):
        result = build_matrix({"scenarios": [
            {"event_id": "e1", "scenario": "trend_accelerates"},
            {"event_id": "e1", "scenario": "trend_cools"},
        ]})
        self.assertEqual(result["event_count"], 1)
        row = result["results"][0]
        self.assertEqual(row["scenario_count"], 2)
        self.assertTrue(all(x["robust"] for x in row["robust_actions"]))

    def test_single_scenario_does_not_claim_robustness(self):
        result = build_matrix({"scenarios": [{"event_id": "e2", "scenario": "trend_accelerates"}]})
        self.assertEqual(result["event_count"], 0)

if __name__ == "__main__":
    unittest.main()
