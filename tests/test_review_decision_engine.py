#!/usr/bin/python3
"""P0-2 Review Decision Engine 单元测试。

核心纪律：**建议不等于执行**。
- 任何 item 的 auto_executable 必须为 False；
- 分层计数与 items 数量自洽；
- 本模块**不得修改**任何 review item 的 status（只读聚合）。
"""
from __future__ import annotations

import unittest

import review_decision_engine as rde


def _item(eid, reason_types, priority=30, change_impact=None, status="pending"):
    return {"event_id": eid, "title": f"t-{eid}", "status": status, "priority": priority,
            "trust_level": "medium", "reasons": [{"type": t} for t in reason_types],
            "change_impact": change_impact}


def _queue(items):
    return {"items": items}


class TestReviewDecisionEngine(unittest.TestCase):
    def test_tiers_and_human_load(self):
        q = _queue([
            _item("a", ["conflict"]),                    # decision
            _item("b", ["change_impact"]),               # material
            _item("c", ["event_cluster"], priority=60), # relevant
            _item("d", ["event_cluster"]),              # noise
        ])
        doc = rde.build(q)
        self.assertEqual(doc["meta"]["pending"], 4)
        self.assertEqual(doc["meta"]["human_load"], 2)   # decision + material
        tiers = {g["tier"]: g["count"] for g in doc["presentation"]}
        self.assertEqual(tiers["decision_required"], 1)
        self.assertEqual(tiers["material_change"], 1)
        self.assertEqual(tiers["relevant"], 1)
        self.assertEqual(tiers["noise"], 1)

    def test_nothing_is_auto_executable(self):
        q = _queue([_item("a", ["conflict"]), _item("d", ["event_cluster"])])
        doc = rde.build(q)
        for g in doc["presentation"]:
            for it in g["items"]:
                self.assertFalse(it["auto_executable"])
        self.assertFalse(doc["meta"]["auto_resolve_enabled"])

    def test_does_not_mutate_input_status(self):
        item = _item("a", ["conflict"])
        before = item["status"]
        rde.build(_queue([item]))
        self.assertEqual(item["status"], before, "本模块绝不可改变 review item 状态")

    def test_noise_default_collapsed(self):
        q = _queue([_item("d", ["event_cluster"])])
        doc = rde.build(q)
        g = {x["tier"]: x for x in doc["presentation"]}
        self.assertTrue(g["noise"]["default_collapsed"])
        self.assertFalse(g["decision_required"]["default_collapsed"])

    def test_every_item_has_reason(self):
        q = _queue([_item("a", ["conflict"]), _item("d", ["event_cluster"])])
        doc = rde.build(q)
        for g in doc["presentation"]:
            for it in g["items"]:
                self.assertTrue(it["reason"], "每条建议必须附触发理由")

    def test_non_pending_excluded(self):
        q = _queue([_item("a", ["conflict"], status="approved")])
        doc = rde.build(q)
        self.assertEqual(doc["meta"]["pending"], 0)


class TestValidate(unittest.TestCase):
    def test_validate_rejects_auto_executable(self):
        q = _queue([_item("a", ["conflict"])])
        doc = rde.build(q)
        rde.validate(doc)  # 不抛
        # 人为把某条改成可自动执行→ 应拒绝
        doc["presentation"][0]["items"][0]["auto_executable"] = True
        with self.assertRaises(ValueError):
            rde.validate(doc)

    def test_validate_rejects_count_mismatch(self):
        q = _queue([_item("a", ["conflict"])])
        doc = rde.build(q)
        doc["presentation"][0]["count"] = 99
        with self.assertRaises(ValueError):
            rde.validate(doc)


if __name__ == "__main__":
    unittest.main()