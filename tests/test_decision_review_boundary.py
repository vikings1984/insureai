import unittest

from decision import build_decisions


class DecisionReviewBoundaryTests(unittest.TestCase):
    def test_low_coverage_cannot_be_now(self):
        events = [{
            "event_id": "evt_1",
            "event_type": "acquisition",
            "topic": "capital_reinsurance",
            "scores": {"intelligence_score": 95},
            "trust": {"level": "high", "conflict": False},
            "evidence_coverage": 50,
            "evidence_status": "single_source",
            "review_required": True,
        }]
        temporal = {"topic_signals": [{"topic": "capital_reinsurance", "phase": "accelerating", "signal_strength": 95}]}
        result = build_decisions(events, temporal, "executive")
        self.assertEqual(result[0]["urgency"], "watch")
        self.assertTrue(result[0]["human_review_required"])

    def test_high_coverage_can_reach_now_only_with_high_trust(self):
        events = [{
            "event_id": "evt_2",
            "event_type": "acquisition",
            "topic": "capital_reinsurance",
            "scores": {"intelligence_score": 95},
            "trust": {"level": "high", "conflict": False},
            "evidence_coverage": 95,
            "evidence_status": "cross_checked",
            "review_required": False,
        }]
        temporal = {"topic_signals": [{"topic": "capital_reinsurance", "phase": "accelerating", "signal_strength": 95}]}
        result = build_decisions(events, temporal, "executive")
        self.assertEqual(result[0]["urgency"], "now")
        self.assertFalse(result[0]["human_review_required"])
        self.assertIn("人工确认", result[0]["guardrail"])


if __name__ == "__main__":
    unittest.main()
