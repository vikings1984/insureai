#!/usr/bin/env python3
import unittest
from decision_stability import build_stability

class TestDecisionStability(unittest.TestCase):
    def test_baseline_has_no_false_jitter(self):
        result = build_stability({"snapshots": []}, [{"event_id": "e1", "urgency": "now", "basis": {"trust_level": "high", "temporal_phase": "accelerating", "intelligence_score": 90}}])
        self.assertEqual(result["results"][0]["status"], "baseline")

    def test_oscillation_without_material_input_change_is_jitter(self):
        def snap(u):
            return {"created_at": "2026-01-01T00:00:00Z", "decisions": [{"event_id": "e1", "urgency": u, "trust_level": "high", "temporal_phase": "forming", "intelligence_score": 80}]}
        history = {"snapshots": [snap("watch"), snap("now"), snap("watch"), snap("now")]}
        current = [{"event_id": "e1", "urgency": "watch", "basis": {"trust_level": "high", "temporal_phase": "forming", "intelligence_score": 80}}]
        row = build_stability(history, current)["results"][0]
        self.assertEqual(row["status"], "jitter")
        self.assertTrue(row["oscillating"])

    def test_material_change_is_responsive_not_jitter(self):
        def snap(u, phase="forming", score=80):
            return {"created_at": "2026-01-01T00:00:00Z", "decisions": [{"event_id": "e1", "urgency": u, "trust_level": "high", "temporal_phase": phase, "intelligence_score": score}]}
        history = {"snapshots": [snap("watch"), snap("soon"), snap("now", "accelerating", 90), snap("soon", "forming", 80)]}
        current = [{"event_id": "e1", "urgency": "now", "basis": {"trust_level": "high", "temporal_phase": "accelerating", "intelligence_score": 90}}]
        row = build_stability(history, current)["results"][0]
        self.assertEqual(row["status"], "responsive")

if __name__ == "__main__":
    unittest.main()
