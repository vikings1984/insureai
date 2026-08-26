#!/usr/bin/env python3
import unittest

import benchmark


class BenchmarkRegressionTests(unittest.TestCase):
    def test_event_benchmark_has_zero_false_merge(self):
        import json
        data = json.loads(benchmark.FIXTURE.read_text(encoding="utf-8"))
        result = benchmark.event_benchmark(data["event_cases"])
        self.assertEqual(result["false_merge_rate"], 0.0)
        self.assertEqual(result["precision"], 1.0)
        self.assertEqual(result["recall"], 1.0)

    def test_claim_benchmark_blocks_single_source_cross_check(self):
        import json
        data = json.loads(benchmark.FIXTURE.read_text(encoding="utf-8"))
        result = benchmark.claim_benchmark(data["claim_cases"])
        self.assertEqual(result["single_source_false_cross_check_rate"], 0.0)
        self.assertEqual(result["cross_check_accuracy"], 1.0)

    def test_decision_benchmark_zero_unsafe_now_and_reviews_conflicts(self):
        import json
        data = json.loads(benchmark.FIXTURE.read_text(encoding="utf-8"))
        result = benchmark.decision_benchmark(data["decision_cases"])
        self.assertEqual(result["unsafe_now_rate"], 0.0)
        self.assertEqual(result["human_review_recall"], 1.0)

    def test_end_to_end_benchmark_meets_gate(self):
        import json
        data = json.loads(benchmark.FIXTURE.read_text(encoding="utf-8"))
        event = benchmark.event_benchmark(data["event_cases"])
        claim = benchmark.claim_benchmark(data["claim_cases"])
        decision = benchmark.decision_benchmark(data["decision_cases"])
        macro = (event["precision"] + event["recall"] + (1 - event["false_merge_rate"]) + claim["cross_check_accuracy"] + claim["single_source_state_accuracy"] + (1 - claim["single_source_false_cross_check_rate"]) + (1 - decision["unsafe_now_rate"]) + decision["human_review_recall"]) / 8
        self.assertGreaterEqual(macro, 0.95)


if __name__ == "__main__":
    unittest.main()
