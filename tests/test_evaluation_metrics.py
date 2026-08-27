#!/usr/bin/env python3
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from evaluation_metrics import build_metrics, production_claim_metrics


class TestEvaluationMetrics(unittest.TestCase):
    def test_metrics_are_bounded(self):
        result = build_metrics()
        for section in ("event_clustering", "claim_evidence", "temporal", "decision", "source_authority"):
            for key, value in result[section].items():
                if isinstance(value, float):
                    self.assertGreaterEqual(value, 0)
                    self.assertLessEqual(value, 1)
        self.assertGreaterEqual(result["macro_quality"], 0)
        self.assertLessEqual(result["macro_quality"], 1)

    def test_regression_metrics(self):
        result = build_metrics()
        self.assertEqual(result["event_clustering"]["precision"], 1.0)
        self.assertEqual(result["event_clustering"]["recall"], 1.0)
        self.assertEqual(result["event_clustering"]["false_merge_rate"], 0.0)
        self.assertEqual(result["claim_evidence"]["single_source_false_cross_check_rate"], 0.0)
        self.assertEqual(result["temporal"]["false_trend_rate_no_date"], 0.0)
        self.assertEqual(result["decision"]["unsafe_now_rate"], 0.0)
        self.assertEqual(result["decision"]["guardrail_coverage"], 1.0)
        self.assertEqual(result["source_authority"]["tier1_single_source_trust"], 1.0)
        self.assertEqual(result["source_authority"]["tier3_pair_not_high"], 1.0)

    def test_build_metrics_includes_production_section(self):
        result = build_metrics()
        production = result["production"]
        self.assertIn("claim_evidence_match_rate", production)
        self.assertGreaterEqual(production["claim_evidence_match_rate"], 0)
        self.assertLessEqual(production["claim_evidence_match_rate"], 1)


class TestProductionClaimMetrics(unittest.TestCase):
    def _write(self, payload):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        self.addCleanup(os.unlink, path)
        return Path(path)

    def test_match_rate_computed_from_claim_counts(self):
        artifact = self._write({"claim_count": 100, "unverified_claim_count": 30, "conflicted_claim_count": 2})
        result = production_claim_metrics(artifact)
        self.assertEqual(result["claim_evidence_match_rate"], 0.7)
        self.assertEqual(result["claim_count"], 100)
        self.assertEqual(result["unverified_claim_count"], 30)

    def test_missing_artifact_fails_closed_to_zero(self):
        result = production_claim_metrics(Path("/nonexistent/claims.json"))
        self.assertEqual(result["claim_evidence_match_rate"], 0.0)
        self.assertIn("reason", result)

    def test_empty_claims_fail_closed_to_zero(self):
        artifact = self._write({"claim_count": 0, "unverified_claim_count": 0})
        result = production_claim_metrics(artifact)
        self.assertEqual(result["claim_evidence_match_rate"], 0.0)

    def test_fully_verified_artifact_scores_one(self):
        artifact = self._write({"claim_count": 50, "unverified_claim_count": 0})
        result = production_claim_metrics(artifact)
        self.assertEqual(result["claim_evidence_match_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
