#!/usr/bin/env python3
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from evaluation_metrics import build_metrics


class TestEvaluationMetrics(unittest.TestCase):
    def test_metrics_are_bounded(self):
        result = build_metrics()
        for section in ("event_clustering", "claim_evidence", "temporal", "decision"):
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


if __name__ == "__main__":
    unittest.main()
