#!/usr/bin/env python3
import unittest
from scenario_evidence import build_scenario_evidence


class TestScenarioEvidence(unittest.TestCase):
    def test_unavailable_blocks_execution_without_changing_support(self):
        scenario = {"scenarios": [{"event_id": "e1", "support_level": 82, "scenario": "trend_accelerates"}]}
        result = build_scenario_evidence(scenario, {"level": "unavailable"})
        row = result["scenarios"][0]
        self.assertEqual(row["support_level_original"], 82)
        self.assertEqual(row["support_level"], 82)
        self.assertEqual(row["vulnerability"], "critical")
        self.assertEqual(row["execution_readiness"], "blocked")

    def test_high_availability_is_ready(self):
        scenario = {"scenarios": [{"event_id": "e2", "support_level": 70, "scenario": "trend_cools"}]}
        result = build_scenario_evidence(scenario, {"level": "high"})
        row = result["scenarios"][0]
        self.assertEqual(row["vulnerability"], "low")
        self.assertEqual(row["execution_readiness"], "ready")


if __name__ == "__main__":
    unittest.main()
