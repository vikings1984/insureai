#!/usr/bin/python3
"""P0-3b Gold 增量追加单元测试（复用 promote 范式，绝不自动验证）。"""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
_spec = importlib.util.spec_from_file_location(
    "gold_incremental", os.path.join(ROOT, "scripts", "gold_incremental.py"))
gi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gi)


def _candidates(n=3):
    return {"candidates": [
        {"id": f"c{i}", "dimension": "same_company_diff_event",
         "proposed_relation": "different_event", "primary_entity": f"E{i}",
         "rationale": "r"} for i in range(n)]}


class TestGoldIncremental(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.gold = os.path.join(self.dir, "g.json")
        self.cand = os.path.join(self.dir, "c.json")
        with open(self.cand, "w", encoding="utf-8") as f:
            json.dump(_candidates(), f)

    def test_prepare_all_pending(self):
        out = gi.prepare(self.gold, self.cand, "b1")
        self.assertEqual(out["added"], 3)
        self.assertEqual(out["total_pending"], 3)
        with open(out["bundle"], encoding="utf-8") as f:
            b = json.load(f)
        self.assertEqual(b["gold_status"], "pending_human")
        for e in b["entries"]:
            self.assertEqual(e["decision"], "pending")   # 绝不自动验证

    def test_apply_refused_while_pending(self):
        gi.prepare(self.gold, self.cand, "b1")
        out = gi.apply(self.gold)
        self.assertFalse(out["applied"])
        self.assertIn("拒绝", out["reason"])

    def test_incremental_no_duplicate(self):
        gi.prepare(self.gold, self.cand, "b1")
        out2 = gi.prepare(self.gold, self.cand, "b1")   # 再次 prepare
        self.assertEqual(out2["added"], 0, "已存在的 id 不应重复追加")

    def test_apply_after_all_labeled(self):
        gi.prepare(self.gold, self.cand, "b1")
        bundle = self.gold.replace(".json", ".review_bundle.json")
        with open(bundle, encoding="utf-8") as f:
            b = json.load(f)
        for e in b["entries"]:
            e["decision"] = "approve"
        with open(bundle, "w", encoding="utf-8") as f:
            json.dump(b, f, ensure_ascii=False)
        out = gi.apply(self.gold)
        self.assertTrue(out["applied"])
        with open(self.gold, encoding="utf-8") as f:
            g = json.load(f)
        self.assertEqual(g["gold_status"], "human_confirmed")
        self.assertIn("applied_at", g)

    def test_dry_run_does_not_write(self):
        gi.prepare(self.gold, self.cand, "b1")
        bundle = self.gold.replace(".json", ".review_bundle.json")
        with open(bundle, encoding="utf-8") as f:
            b = json.load(f)
        for e in b["entries"]:
            e["decision"] = "reject"
        with open(bundle, "w", encoding="utf-8") as f:
            json.dump(b, f, ensure_ascii=False)
        out = gi.apply(self.gold, dry_run=True)
        self.assertTrue(out["applied"])
        self.assertFalse(os.path.exists(self.gold), "dry-run 不应写 gold 文件")

    def test_status_reports_counts(self):
        gi.prepare(self.gold, self.cand, "b1")
        st = gi.status(self.gold)
        self.assertTrue(st["exists"])
        self.assertEqual(st["pending"], 3)
        self.assertEqual(st["approved"], 0)


if __name__ == "__main__":
    unittest.main()