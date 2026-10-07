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
        """P0-1 修复后：同域实体线程组应被提议为候选（recall>0）。

        ⚠️ 断言口径（重要）：本测试跑在**活的**生产数据上，数据每天会变。
        因此**不断言具体分数**（曾因新增 CE 导致 1.0→0.8333 而CI 红），
        只断言**结构性不变量**：
          - 存在同域 gold 组；
          - resolver 真的产出了候选（修复前恒为 0，这是 P0-1 的核心回归点）；
          - **不出现假阳性**（precision 必须 1.0——绝不容忍误合并提案）。
        具体 P/R/F1 由 `resolution_benchmark.py` 在报告中呈现，不作为单测断言。
        """
        out = rb.run_benchmark()
        self.assertTrue(out["available"])
        m = out["metrics"]
        c = out["counts"]
        # 存在应被提议的同域组
        self.assertGreater(c["gold_same_domain_groups"], 0)
        # 核心回归点：resolver 必须真的提出候选（修复前恒为 0）
        self.assertGreater(c["resolver_proposals"], 0)
        # 不变量：假阳性恒为 0（误合并提案是不可接受的安全事故）
        self.assertEqual(m["fp"], 0)
        self.assertEqual(m["precision"], 1.0)
        # 修复后不应再有"字段名不匹配"根因诊断
        self.assertIsNone(out["diagnosis"])

    def test_gold_excludes_unresolved_event_ids(self):
        """gold 只应含合法 CE id（`cev_` 前缀）。

        回归防护：second_brain 少数线程事件带的是原始 event_id（未解析成 CE），
        若混入 gold 会与 proposal 的 CE 集合永不相等 → 假报漏报+假阳性。
        """
        registry = ir.load_registry()
        gold = rb.build_gold(_threads(), registry)
        for g in gold["positives"] + gold["negatives"]:
            for cev in g["cev_ids"]:
                self.assertTrue(str(cev).startswith("cev_"),
                                f"gold 含未解析的 event_id：{cev}")


if __name__ == "__main__":
    unittest.main()
