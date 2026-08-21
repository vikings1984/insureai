#!/usr/bin/env python3
import unittest
from unittest.mock import patch

import decision_credibility


class TestDecisionCredibility(unittest.TestCase):
    def test_jitter_requires_review(self):
        payloads = {
            "release_manifest.json": {"quality_status": "passed", "deployment_status": "pending", "deployment_verified": False},
            "decision_stability.json": {"results": [{"status": "jitter"}]},
            "evidence_availability.json": {"results": []},
            "evaluation_metrics.json": {"macro_quality": 1.0},
        }
        with patch.object(decision_credibility, "_load", side_effect=lambda name, default: payloads.get(name, default)):
            result = decision_credibility.build_credibility()
        self.assertEqual(result["status"], "review")
        jitter = next(row for row in result["signal_details"] if row["signal"] == "decision_jitter_events")
        self.assertEqual(jitter["actual"], 1)
        self.assertFalse(jitter["result"])

    def test_clean_quality_is_ready_when_deployment_is_pending(self):
        payloads = {
            "release_manifest.json": {"quality_status": "passed", "deployment_status": "pending", "deployment_verified": False},
            "decision_stability.json": {"results": [{"status": "stable"}]},
            "evidence_availability.json": {"results": []},
            "evaluation_metrics.json": {"macro_quality": 1.0},
        }
        with patch.object(decision_credibility, "_load", side_effect=lambda name, default: payloads.get(name, default)):
            result = decision_credibility.build_credibility()
        self.assertEqual(result["status"], "ready")
        self.assertFalse(result["deployment"]["verified"])
        self.assertEqual(result["version"], 3)
        self.assertEqual(len(result["signal_details"]), 5)

    def test_failed_quality_blocks(self):
        payloads = {
            "release_manifest.json": {"quality_status": "failed", "deployment_status": "pending", "deployment_verified": False},
            "decision_stability.json": {"results": []},
            "evidence_availability.json": {"results": []},
            "evaluation_metrics.json": {"macro_quality": 0.5},
        }
        with patch.object(decision_credibility, "_load", side_effect=lambda name, default: payloads.get(name, default)):
            result = decision_credibility.build_credibility()
        self.assertEqual(result["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
