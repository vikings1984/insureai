#!/usr/bin/python3
"""P0-2 Semantic Change 精度基准单元测试。

用临时 gold 驱动 semantic_change_benchmark.run_benchmark，验证 P/R/F1 计算：
- seed gold → 全正例检出 + 负例不误报（precision/recall=1.0）；
- 构造「标 expect_change=true 但状态未变」→ 漏报 FN，recall<1.0；
- 构造「标 expect_change=false 但状态变了」→ 误报 FP，precision<1.0。
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest

import semantic_change_benchmark as scb


def _write_gold(scenarios) -> str:
    d = tempfile.mkdtemp()
    p = os.path.join(d, "gold.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"status": "test", "source": "test", "scenarios": scenarios}, f,
                  ensure_ascii=False)
    return p


def _day(n, stage, ev, expect, types=None):
    return {"day": n, "ceid": "cev_A", "eid": "evt_A", "stage": stage, "evidence": ev,
            "trust": 70, "expect_change": expect, "expect_types": types or []}


class TestSemanticChangeBenchmark(unittest.TestCase):
    def test_seed_gold_all_correct(self):
        out = scb.run_benchmark(scb.GOLD_PATH)
        self.assertTrue(out["available"])
        m = out["metrics"]
        self.assertEqual(m["tp"], 3)
        self.assertEqual(m["fp"], 0)
        self.assertEqual(m["fn"], 0)
        self.assertEqual(m["precision"], 1.0)
        self.assertEqual(m["recall"], 1.0)

    def test_missing_gold_unavailable(self):
        out = scb.run_benchmark("/nonexistent/gold.json")
        self.assertFalse(out["available"])

    def test_false_negative_lowers_recall(self):
        # Day2 标 expect_change=true 但状态与 Day1 相同 → 应记为 FN
        scen = [{"name": "s", "days": [
            _day(1, "rumor", 1, False),
            _day(2, "rumor", 1, True, ["EVENT_STAGE_CHANGED"]),  # 实际无变化 → FN
        ]}]
        out = scb.run_benchmark(_write_gold(scen))
        m = out["metrics"]
        self.assertEqual(m["fn"], 1)
        self.assertEqual(m["recall"], 0.0)

    def test_false_positive_lowers_precision(self):
        # Day2 标 expect_change=false 但阶段真的变了 → 应记为 FP
        scen = [{"name": "s", "days": [
            _day(1, "rumor", 1, False),
            _day(2, "negotiation", 1, False),  # 实际有变化 → FP
        ]}]
        out = scb.run_benchmark(_write_gold(scen))
        m = out["metrics"]
        self.assertEqual(m["fp"], 1)
        self.assertEqual(m["precision"], 0.0)

    def test_seed_day_not_counted(self):
        # 只有 seed 日 → 无指标事件，precision/recall 保持 1.0，tn/fp/fn 为 0
        scen = [{"name": "s", "days": [_day(1, "rumor", 1, False)]}]
        out = scb.run_benchmark(_write_gold(scen))
        m = out["metrics"]
        self.assertEqual((m["tp"], m["fp"], m["fn"]), (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
