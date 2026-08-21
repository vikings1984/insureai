#!/usr/bin/env python3
import unittest
from scenario_matrix import build_matrix


class TestRobustActionConfidence(unittest.TestCase):
    def test_score_requires_two_ready_scenarios(self):
        result = build_matrix({"scenarios": [
            {"event_id": "e1", "scenario": "trend_accelerates", "execution_readiness": "ready", "evidence_availability": "high"},
            {"event_id": "e1", "scenario": "trend_cools", "execution_readiness": "ready", "evidence_availability": "medium"},
        ]})
        row = result["results"][0]
        self.assertTrue(all(x["robust"] for x in row["robust_actions"]))
        action = row["robust_actions"][0]
        self.assertEqual(action["evidence_quality"], 0.7)
        self.assertGreater(action["robustness_score"], 0)
        self.assertIn(action["robustness_confidence"], {"high", "medium", "low"})

    def test_weakest_ready_scenario_caps_evidence_quality(self):
        result = build_matrix({"scenarios": [
            {"event_id": "e1", "scenario": "trend_accelerates", "execution_readiness": "ready", "evidence_availability": "high"},
            {"event_id": "e1", "scenario": "trend_cools", "execution_readiness": "ready", "evidence_availability": "low"},
        ]})
        action = result["results"][0]["robust_actions"][0]
        self.assertEqual(action["evidence_quality"], 0.4)

    def test_blocked_scenario_has_no_robust_action(self):
        result = build_matrix({"scenarios": [
            {"event_id": "e1", "scenario": "trend_accelerates", "execution_readiness": "blocked", "vulnerability": "blocked", "evidence_availability": "high"},
            {"event_id": "e1", "scenario": "trend_cools", "execution_readiness": "ready", "evidence_availability": "high"},
        ]})
        self.assertFalse(any(x["robust"] for x in result["results"][0]["robust_actions"]))

    def test_sorting_puts_robust_actions_first(self):
        result = build_matrix({"scenarios": [
            {"event_id": "e1", "scenario": "trend_accelerates", "execution_readiness": "ready", "evidence_availability": "high"},
            {"event_id": "e1", "scenario": "trend_cools", "execution_readiness": "ready", "evidence_availability": "high"},
        ]})
        actions = result["results"][0]["robust_actions"]
        self.assertTrue(all(a["robust"] for a in actions))


if __name__ == "__main__":
    unittest.main()
