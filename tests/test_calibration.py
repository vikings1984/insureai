#!/usr/bin/env python3
import unittest

from calibration import build_calibration
from decision import build_decisions


class TestCalibration(unittest.TestCase):
    def test_neutral_without_enough_feedback(self):
        result = build_calibration({"reviews": []}, {"items": []})
        self.assertEqual(result["status"], "neutral")
        self.assertEqual(result["overrides"], {})

    def test_repeated_false_positive_caps_urgency(self):
        labels = {
            "reviews": [
                {"review_id": "e1", "expected": {"type": "decision", "event_type": "regulatory", "urgency": "watch"}},
                {"review_id": "e2", "expected": {"type": "decision", "event_type": "regulatory", "urgency": "watch"}},
                {"review_id": "e3", "expected": {"type": "decision", "event_type": "regulatory", "urgency": "watch"}},
            ]
        }
        queue = {"items": [
            {"event_id": "e1", "event_type": "regulatory", "decision": {"urgency": "now"}},
            {"event_id": "e2", "event_type": "regulatory", "decision": {"urgency": "soon"}},
            {"event_id": "e3", "event_type": "regulatory", "decision": {"urgency": "now"}},
        ]}
        result = build_calibration(labels, queue)
        self.assertEqual(result["status"], "active")
        self.assertEqual(result["overrides"]["regulatory"]["max_urgency"], "watch")

    def test_decision_applies_cap_without_changing_scores(self):
        # The calibration test must satisfy the same evidence boundary as
        # production: high urgency is only eligible when evidence is
        # independently cross-checked and trust is high. Calibration then
        # applies its own cap without changing the intelligence score.
        events = [{
            "event_id": "e1",
            "event_type": "regulatory",
            "topic": "regulatory_change",
            "scores": {"intelligence_score": 92},
            "evidence_coverage": 100,
            "evidence_status": "cross_checked",
            "review_required": False,
            "trust": {"level": "high", "conflict": False},
        }]
        temporal = {"topic_signals": [{"topic": "regulatory_change", "phase": "accelerating", "signal_strength": 90}]}
        calibration = {"status": "active", "overrides": {"regulatory": {"max_urgency": "watch"}}}
        out = build_decisions(events, temporal, "executive", calibration)
        self.assertEqual(out[0]["urgency"], "watch")
        self.assertEqual(out[0]["basis"]["pre_calibration_urgency"], "now")
        self.assertTrue(out[0]["basis"]["calibration_applied"])
        self.assertEqual(out[0]["basis"]["intelligence_score"], 92)


if __name__ == "__main__":
    unittest.main()
