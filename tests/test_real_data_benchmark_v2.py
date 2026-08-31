#!/usr/bin/env python3
"""P1-4.1 (real_v2) 基准测试。

断言纪律（延续 P2.x）：硬安全门与指标必须验证*具体值*，不能只写 >= 0。

边界（人工审阅）：runner 只读 gold.json（validated）；candidates.json（proposed）
不得被当作 gold 使用——测试程序化约束这一边界。
"""
import json
import unittest
from pathlib import Path

import real_data_benchmark as rdb

ROOT = Path(__file__).resolve().parent.parent
V2_ARTICLES = ROOT / "benchmarks" / "real_v2" / "articles.json"
V2_GOLD = ROOT / "benchmarks" / "real_v2" / "gold.json"
V1_ARTICLES = ROOT / "benchmarks" / "real_v1" / "articles.json"
V1_GOLD = ROOT / "benchmarks" / "real_v1" / "gold.json"
CANDIDATES = ROOT / "benchmarks" / "real_v2" / "candidates.json"


class TestV2Benchmark(unittest.TestCase):
    def test_v2_macro_quality_and_hard_safety_gates(self):
        res = rdb.run_benchmark(V2_ARTICLES, V2_GOLD, ROOT / "real_benchmark_v2_test.json")
        self.assertEqual(res["version"], "real-v2.0")
        self.assertEqual(res["macro_quality"], 1.0)
        ev = res["event"]
        self.assertEqual(ev["precision"], 1.0)
        self.assertEqual(ev["recall"], 1.0)
        self.assertEqual(ev["false_merge_rate"], 0.0)   # 显式不同事件对不得合并
        self.assertEqual(ev["false_split_rate"], 0.0)   # 同事件对必须合并
        self.assertEqual(ev["true_positive"], 11)        # berkshire 1 + axa 10
        self.assertEqual(ev["true_negative"], 5)         # zurich + 3 cross + acrisure
        ce = res["claim_evidence"]
        self.assertEqual(ce["accuracy"], 1.0)
        self.assertEqual(ce["single_source_false_cross_check_rate"], 0.0)

    def test_v1_still_frozen_and_green(self):
        # 扩展 runner 不得破坏已冻结的 v1.0
        res = rdb.run_benchmark(V1_ARTICLES, V1_GOLD, ROOT / "real_benchmark_v1_test.json")
        self.assertEqual(res["macro_quality"], 1.0)
        self.assertEqual(res["event"]["false_merge_rate"], 0.0)
        self.assertEqual(res["event"]["false_split_rate"], 0.0)


class TestV2Dimensions(unittest.TestCase):
    def test_all_four_difficult_dimensions_covered(self):
        gold = json.loads(V2_GOLD.read_text(encoding="utf-8"))
        self.assertEqual(
            set(gold["dimension_coverage"]),
            {"rumor_to_confirmed", "same_company_diff_event", "multi_source_3_5", "contradiction"},
        )
        dims_in_meta = {m["dimension"] for m in gold["pair_meta"].values()}
        # 四个维度都应在已验证标注中出现
        self.assertTrue({"rumor_to_confirmed", "same_company_diff_event", "multi_source_3_5", "contradiction"}.issubset(dims_in_meta))

    def test_rumor_to_confirmed_is_same_event(self):
        gold = json.loads(V2_GOLD.read_text(encoding="utf-8"))
        same = {tuple(sorted(x)) for x in gold["same_event_pairs"]}
        self.assertIn(tuple(sorted(["v2_berk_rumor_reuters", "v2_berk_confirmed_ij"])), same)
        self.assertEqual(gold["pair_meta"]["v2_berk_confirmed_ij|v2_berk_rumor_reuters"]["dimension"], "rumor_to_confirmed")

    def test_contradiction_is_must_not_merge(self):
        # 矛盾报道（否认 vs 确认）必须作为显式不同事件对，测试"不可合并"安全属性
        gold = json.loads(V2_GOLD.read_text(encoding="utf-8"))
        diff = {tuple(sorted(x)) for x in gold["different_event_pairs"]}
        self.assertIn(tuple(sorted(["v2_acris_denies", "v2_acris_confirm"])), diff)
        self.assertEqual(gold["pair_meta"]["v2_acris_confirm|v2_acris_denies"]["dimension"], "contradiction")


class TestHumanReviewBoundary(unittest.TestCase):
    def test_gold_is_validated_and_candidates_are_proposed_only(self):
        gold = json.loads(V2_GOLD.read_text(encoding="utf-8"))
        cand = json.loads(CANDIDATES.read_text(encoding="utf-8"))
        self.assertEqual(gold.get("review_status"), "validated")
        self.assertEqual(cand.get("review_status"), "proposed")
        # 候选文件不是可直接当 gold 的标注文件：缺少 same_event_pairs 结构
        self.assertNotIn("same_event_pairs", cand)
        # 候选与生产 id 不与已验证 gold 的 v2_ id 交叉污染
        gold_ids = set()
        for pair in gold["same_event_pairs"] + gold["different_event_pairs"]:
            gold_ids.update(pair)
        cand_ids = {a["id"] for c in cand["candidates"] for a in c["articles"]}
        self.assertFalse(gold_ids & cand_ids)

    def test_runner_only_reads_gold_not_candidates(self):
        # runner 以 candidates.json 当 gold 会因缺字段而报错（证明候选不能静默充当基准）
        with self.assertRaises(Exception):
            rdb.run_benchmark(V2_ARTICLES, CANDIDATES, ROOT / "real_benchmark_should_fail.json")


if __name__ == "__main__":
    unittest.main()
