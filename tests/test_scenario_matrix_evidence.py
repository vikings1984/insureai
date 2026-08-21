#!/usr/bin/env python3
import unittest
from scenario_matrix import build_matrix


class TestScenarioMatrixEvidence(unittest.TestCase):
    def test_two_ready_scenarios_are_robust(self):
        result = build_matrix({"scenarios": [
            {"event_id": "e1", "scenario": "trend_accelerates", "execution_readiness": "ready"},
            {"event_id": "e1", "scenario": "trend_cools", "execution_readiness": "ready"},
        ]})
        row = result["results"][0]
        self.assertTrue(all(x["robust"] for x in row["robust_actions"]))
        self.assertEqual(row["evidence_ready_scenarios"], ["trend_accelerates", "trend_cools"])

    def test_blocked_scenario_cannot_contribute_to_robustness(self):
        result = build_matrix({"scenarios": [
            {"event_id": "e1", "scenario": "trend_accelerates", "execution_readiness": "blocked", "vulnerability": "blocked"},
            {"event_id": "e1", "scenario": "trend_cools", "execution_readiness": "ready"},
        ]})
        row = result["results"][0]
        self.assertFalse(any(x["robust"] for x in row["robust_actions"]))
        self.assertEqual(row["evidence_ready_scenarios"], ["trend_cools"])

    def test_caution_scenario_is_not_ready_by_default(self):
        result = build_matrix({"scenarios": [
            {"event_id": "e1", "scenario": "trend_accelerates", "execution_readiness": "caution", "vulnerability": "caution"},
            {"event_id": "e1", "scenario": "trend_cools", "execution_readiness": "ready"},
        ]})
        row = result["results"][0]
        self.assertEqual(row["evidence_ready_scenarios"], ["trend_cools"])


if __name__ == "__main__":
    unittest.main()
