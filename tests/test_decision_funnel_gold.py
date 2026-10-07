#!/usr/bin/python3
"""P0-3 Decision Ready 人工 gold 回填单元测试。

验证 gold_precision_metrics()：只统计有标注的 decision_ready，按 should_decide=false
计 human_override_rate；无 gold / 无标注时保持 "n/a"（绝不伪造精度）。
使用临时 gold（monkeypatch decision_funnel.GOLD），含 should_decide=false 以确保
override 计算真的生效（生产 seed 全为 true，不作为负例）。
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

import decision_funnel


def _write_gold(obj) -> Path:
    d = tempfile.mkdtemp()
    p = Path(d) / "decision_ready_gold.json"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    return p


def _dr(*ceids):
    return [{"canonical_event_id": c} for c in ceids]


class TestGoldPrecision(unittest.TestCase):
    def setUp(self):
        self._orig = decision_funnel.GOLD

    def tearDown(self):
        decision_funnel.GOLD = self._orig

    def test_no_gold_is_na(self):
        decision_funnel.GOLD = Path(tempfile.mkdtemp()) / "missing.json"
        m = decision_funnel.gold_precision_metrics(_dr("cev_a"))
        self.assertEqual(m["human_override_rate"], "n/a")
        self.assertEqual(m["gold_precision"], "n/a")
        self.assertEqual(m["gold_labeled"], 0)

    def test_empty_decision_ready_is_na(self):
        decision_funnel.GOLD = _write_gold({"labels": {"cev_a": {"should_decide": True}}})
        m = decision_funnel.gold_precision_metrics([])
        self.assertEqual(m["human_override_rate"], "n/a")

    def test_all_true_zero_override(self):
        decision_funnel.GOLD = _write_gold({
            "status": "human_confirmed", "source": "human",
            "labels": {"cev_a": {"should_decide": True}, "cev_b": {"should_decide": True}},
        })
        m = decision_funnel.gold_precision_metrics(_dr("cev_a", "cev_b"))
        self.assertEqual(m["human_override_rate"], 0.0)
        self.assertEqual(m["gold_precision"], 1.0)
        self.assertEqual(m["gold_labeled"], 2)
        self.assertEqual(m["gold_status"], "human_confirmed")
        self.assertEqual(m["gold_source"], "human")

    def test_false_label_counted_as_override(self):
        # 2 条已标注，1 条 should_decide=false → override 0.5 / gold_precision 0.5
        decision_funnel.GOLD = _write_gold({
            "status": "human_confirmed", "source": "human",
            "labels": {"cev_a": {"should_decide": True},
                       "cev_b": {"should_decide": False}},
        })
        m = decision_funnel.gold_precision_metrics(_dr("cev_a", "cev_b"))
        self.assertEqual(m["human_override_rate"], 0.5)
        self.assertEqual(m["gold_precision"], 0.5)

    def test_unlabeled_items_ignored(self):
        # cev_c 无 gold 标注，不计入分母
        decision_funnel.GOLD = _write_gold({
            "labels": {"cev_a": {"should_decide": True}},
        })
        m = decision_funnel.gold_precision_metrics(_dr("cev_a", "cev_c"))
        self.assertEqual(m["gold_labeled"], 1)
        self.assertEqual(m["human_override_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()
