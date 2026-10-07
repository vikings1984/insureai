#!/usr/bin/python3
"""P0-3a 人工 gold→CE 解耦桥单元测试。

第八阶段方案 §3-P0-3 的解耦要求：`resolution_benchmark` 不得继续用
`derived_from_entity_threads`（与 resolver 同源= 自证），需改用人工标注 event pair。

守卫要点：
- article→CE 映射**只收录可追溯**的；一文章对多事件（歧义）**不映射**（宁可漏评不猜测）；
- 桥接后不得出现自反对（a==b）；
- skipped 必须**计数并暴露**，不得静默丢样本；
- `wrong_merge_rate`（误合并）必须恒为 0 —— 误合并是安全事故。
"""
from __future__ import annotations

import unittest

import gold_ce_bridge as gb


class TestArticleToCeMapping(unittest.TestCase):
    def test_only_traceable_mappings(self):
        intel = {"events": [
            {"event_id": "e1", "canonical_event_id": "cev_1", "article_ids": [10, 11]},
        ]}
        canon = {"canonical_events": {"cev_1": {}},
                 "by_event_id": {"e1": "cev_1"}}
        a2c = gb.build_article_to_ce(intel, canon)
        self.assertEqual(a2c, {"10": "cev_1", "11": "cev_1"})

    def test_ambiguous_article_excluded(self):
        """一篇文章支撑两个不同 CE → 歧义，不映射（宁可漏评不猜测）。"""
        intel = {"events": [
            {"event_id": "e1", "canonical_event_id": "cev_1", "article_ids": [10]},
            {"event_id": "e2", "canonical_event_id": "cev_2", "article_ids": [10]},
        ]}
        canon = {"canonical_events": {"cev_1": {}, "cev_2": {}},
                 "by_event_id": {"e1": "cev_1", "e2": "cev_2"}}
        a2c = gb.build_article_to_ce(intel, canon)
        self.assertNotIn("10", a2c, "歧义 article 不应被映射")

    def test_ce_not_in_pool_excluded(self):
        intel = {"events": [
            {"event_id": "e1", "canonical_event_id": "cev_x", "article_ids": [1]},
        ]}
        canon = {"canonical_events": {}, "by_event_id": {}}
        a2c = gb.build_article_to_ce(intel, canon)
        self.assertEqual(a2c, {})


class TestBridge(unittest.TestCase):
    def test_converts_pairs_and_counts_skips(self):
        gold = {
            "review_status": "validated",
            "same_event_pairs": [["1", "2"]],
            "different_event_pairs": [["3", "4"], ["5", "99"]],
        }
        a2c = {"1": "cev_a", "2": "cev_a", "3": "cev_b", "4": "cev_c", "5": "cev_d"}
        out = gb.bridge(gold, a2c)
        # same对["1","2"] 同映射到 cev_a → 自反，剔除
        self.assertEqual(out["meta"]["same_pairs_ce_level"], 0)
        # different：["3","4"] 可转；["5","99"] 因 99 映射不到而跳过
        self.assertEqual(out["meta"]["different_pairs_ce_level"], 1)
        self.assertEqual(out["meta"]["skipped_different"], 1)

    def test_no_self_pairs(self):
        gold = {"same_event_pairs": [["1", "1"]],
                "different_event_pairs": []}
        out = gb.bridge(gold, {"1": "cev_a"})
        self.assertEqual(out["same_event_pairs_ce"], [])

    def test_missing_mapping_counted_not_guessed(self):
        gold = {"same_event_pairs": [["1", "2"]], "different_event_pairs": []}
        out = gb.bridge(gold, {})          # 空映射 → 全部跳过
        self.assertEqual(out["meta"]["skipped_same"], 1)
        self.assertEqual(out["meta"]["same_pairs_ce_level"], 0)

    def test_real_gold_bridges_with_full_coverage(self):
        """真实仓库数据：real_v2 人工 gold 应能桥接出 CE 对且零跳过。"""
        out = gb.bridge()
        m = out["meta"]
        self.assertEqual(m["gold_source"], "validated")
        self.assertGreater(m["article_map_size"], 0)
        self.assertGreater(m["same_pairs_ce_level"], 0)
        self.assertGreater(m["different_pairs_ce_level"], 0)
        self.assertEqual(m["skipped_same"], 0)
        self.assertEqual(m["skipped_different"], 0)


class TestHumanGoldEvaluation(unittest.TestCase):
    def test_human_gold_present_and_safe(self):
        import resolution_benchmark as rb
        out = rb.run_benchmark()
        h = out["human_gold"]
        self.assertTrue(h["available"], "人工 gold 维度应可用")
        self.assertEqual(h["gold_status"], "human_validated")
        # 安全不变量：任何误合并都是安全事故，必须为 0
        self.assertEqual(h["wrong_merge_rate"], 0.0)
        # 样本不足必须诚实标注，不得包装成高精度
        self.assertFalse(h["sample_sufficient"])

    def test_derived_and_human_are_separate(self):
        """derived 与 human 指标必须并存且各自独立（不再自证）。"""
        import resolution_benchmark as rb
        out = rb.run_benchmark()
        self.assertIn("metrics", out)          # derived
        self.assertIn("human_gold", out)       # human
        self.assertNotEqual(out["human_gold"], None)


if __name__ == "__main__":
    unittest.main()