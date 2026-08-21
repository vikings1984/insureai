#!/usr/bin/env python3
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from evaluation import run_evaluation, summary


class TestEvaluation(unittest.TestCase):
    def test_all_benchmark_cases_pass(self):
        result = summary(run_evaluation())
        self.assertEqual(result["passed"], result["total"])
        self.assertEqual(result["pass_rate"], 1.0)

    def test_benchmark_has_multiple_layers(self):
        names = {item.name for item in run_evaluation()}
        self.assertTrue({"event_clustering", "claim_evidence", "temporal_signal", "decision_guardrail"}.issubset(names))


if __name__ == "__main__":
    unittest.main()
