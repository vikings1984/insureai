#!/usr/bin/python3
"""P0-1 Canonical Resolution 精度基准单元测试。

验证：
- build_gold 把同域实体线程组分为正例、跨域组分为负例（正例 domains 恒单域）；
- run_benchmark 在真实数据上量化 recall：修复 P0-1 后同域组应全部被提议（recall=1.0）。
本测试只读，不执行任何合并（不触碰 false_merge 硬约束）。
"""
from __future__ import annotations

import json
import os
import unittest

import identity_resolver as ir
import resolution_benchmark as rb

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SECOND_BRAIN = os.path.join(ROOT, "second_brain.json")


def _threads():
    with open(SECOND_BRAIN, "r", encoding="utf-8") as f:
        return (json.load(f).get("entity_threads") or [])


class TestResolutionBenchmark(unittest.TestCase):
    def test_gold_positives_single_domain(self):
        registry = ir.load_registry()
        gold = rb.build_gold(_threads(), registry)
        # 正例（同域，应被提议）每个组只含一个 domain
        for g in gold["positives"]:
            self.assertEqual(len(g["domains"]), 1, f"正例应同域：{g}")
        # 负例（跨域）应含多个 domain
        for g in gold["negatives"]:
            self.assertGreater(len(g["domains"]), 1, f"负例应跨域：{g}")

    def test_gold_has_same_domain_groups(self):
        registry = ir.load_registry()
        gold = rb.build_gold(_threads(), registry)
        # 真实数据应存在同域可合并组（否则 recall 分母为 0，基准无意义）
        self.assertGreater(len(gold["positives"]), 0)

    def test_real_state_recall_fixed(self):
        """P0-1 修复后：同域实体线程组应全部被提议为候选（recall>0，precision 保持 1.0）。

        修复前因 propose_merges 只读 event_id（second_brain 只有 canonical_event_id）
        导致候选恒 0、recall=0；现已兼容两种schema。
        """
        out = rb.run_benchmark()
        self.assertTrue(out["available"])
        m = out["metrics"]
        c = out["counts"]
        # 存在应被提议的同域组
        self.assertGreater(c["gold_same_domain_groups"], 0)
        # 修复后 resolver 必须真的提出候选
        self.assertGreater(c["resolver_proposals"], 0)
        # recall 应为满分（同域组全部被提议），precision 保持 1.0（不伪造跨域合并）
        self.assertEqual(m["recall"], 1.0)
        self.assertEqual(m["precision"], 1.0)
        self.assertIsNone(out["diagnosis"])


if __name__ == "__main__":
    unittest.main()
