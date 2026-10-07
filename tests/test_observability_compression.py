#!/usr/bin/python3
"""P1-2 Review Queue 压缩分级单元测试（只读，不 auto-defer）。

驱动 observability.compute_review_compression，验证分档优先命中
决策级 > 实质变化级 > 相关 > 噪声，以及非 pending 项被排除、daily_human_load 计算。
"""
from __future__ import annotations

import unittest

import observability


def _item(reason_types, priority=30, status="pending", change_impact=None, trust=None):
    return {
        "event_id": "e", "status": status, "priority": priority,
        "reasons": [{"type": t} for t in reason_types],
        "change_impact": change_impact, "trust_level": trust,
    }


class TestReviewCompression(unittest.TestCase):
    def test_decision_reason_tier(self):
        c = observability.compute_review_compression([_item(["conflict"])])
        self.assertEqual(c["tiers"]["decision_required"], 1)

    def test_claim_conflict_is_decision_tier(self):
        c = observability.compute_review_compression([_item(["claim_conflict"])])
        self.assertEqual(c["tiers"]["decision_required"], 1)

    def test_change_impact_reason_material_tier(self):
        c = observability.compute_review_compression([_item(["change_impact"])])
        self.assertEqual(c["tiers"]["material_change"], 1)

    def test_change_impact_field_material_tier(self):
        c = observability.compute_review_compression([_item(["event_cluster"], change_impact={"a": 1})])
        self.assertEqual(c["tiers"]["material_change"], 1)

    def test_high_priority_relevant_tier(self):
        c = observability.compute_review_compression([_item(["event_cluster"], priority=60)])
        self.assertEqual(c["tiers"]["relevant"], 1)

    def test_low_priority_noise_tier(self):
        c = observability.compute_review_compression([_item(["event_cluster"], priority=30)])
        self.assertEqual(c["tiers"]["noise"], 1)

    def test_first_match_wins_decision_over_material(self):
        # 同时有 conflict 与 change_impact → 只计 decision_required，不重复计数
        c = observability.compute_review_compression([_item(["conflict", "change_impact"])])
        self.assertEqual(c["tiers"]["decision_required"], 1)
        self.assertEqual(c["tiers"]["material_change"], 0)
        self.assertEqual(c["total_pending"], 1)

    def test_non_pending_excluded(self):
        c = observability.compute_review_compression([_item(["conflict"], status="approved")])
        self.assertEqual(c["total_pending"], 0)

    def test_daily_human_load_and_ratio(self):
        items = [
            _item(["conflict"]),                       # decision
            _item(["claim_conflict"]),                 # decision
            _item(["change_impact"]),                  # material
            _item(["event_cluster"], priority=30),     # noise
            _item(["event_cluster"], priority=30),     # noise
        ]
        c = observability.compute_review_compression(items)
        self.assertEqual(c["total_pending"], 5)
        self.assertEqual(c["daily_human_load"], 3)  # 2 decision + 1 material
        self.assertEqual(c["compression_ratio"], 0.4)  # 1 - 3/5

    def test_empty(self):
        c = observability.compute_review_compression([])
        self.assertEqual(c["total_pending"], 0)
        self.assertEqual(c["daily_human_load"], 0)
        self.assertEqual(c["compression_ratio"], 0.0)


if __name__ == "__main__":
    unittest.main()
