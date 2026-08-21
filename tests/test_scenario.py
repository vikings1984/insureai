#!/usr/bin/env python3
import unittest

from scenario import build_scenarios


class TestScenarioIntelligence(unittest.TestCase):
    def test_regulatory_event_gets_regulation_scenario(self):
        data = {
            "events": [{
                "event_id": "e1",
                "topic": "regulatory_change",
                "event_type": "regulatory",
                "scores": {"intelligence_score": 85},
                "trust": {"level": "high", "conflict": False},
            }],
            "temporal": {"topic_signals": [{"topic": "regulatory_change", "phase": "accelerating", "signal_strength": 80}]},
        }
        result = build_scenarios(data)
        names = {x["scenario"] for x in result["scenarios"]}
        self.assertIn("regulation_leads", names)
        self.assertTrue(all("not a forecast" in x["disclaimer"] for x in result["scenarios"]))

    def test_low_signal_is_not_promoted(self):
        data = {
            "events": [{
                "event_id": "e2",
                "topic": "ai_intelligent",
                "event_type": "industry_update",
                "scores": {"intelligence_score": 40},
                "trust": {"level": "low"},
            }],
            "temporal": {"topic_signals": []},
        }
        result = build_scenarios(data)
        self.assertEqual(result["scenario_count"], 0)


if __name__ == "__main__":
    unittest.main()
