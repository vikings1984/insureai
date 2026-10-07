#!/usr/bin/python3
"""P1-B Review Queue 账龄分桶单元测试（只读指标，不自动 defer）。

直接驱动 observability.compute_review_aging（纯函数，注入 now 以确定性地跨桶）。
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

import observability


NOW = datetime(2026, 10, 7, 12, 0, 0, tzinfo=timezone.utc)


def _item(age_days: int, status: str = "pending") -> dict:
    created = NOW - timedelta(days=age_days)
    return {"status": status, "created_at": created.isoformat()}


class TestReviewAging(unittest.TestCase):
    def test_buckets_boundary(self):
        state = {
            "a": _item(0), "b": _item(1),        # 0_1
            "c": _item(2), "d": _item(3),        # 1_3
            "e": _item(5), "f": _item(7),        # 3_7
            "g": _item(8), "h": _item(30),       # 7_plus
        }
        buckets, max_age, stale = observability.compute_review_aging(state, now=NOW)
        self.assertEqual(buckets, {"0_1": 2, "1_3": 2, "3_7": 2, "7_plus": 2})
        self.assertEqual(max_age, 30)
        self.assertEqual(stale, 2)

    def test_non_pending_excluded(self):
        state = {
            "a": _item(30, status="decided"),
            "b": _item(30, status="pending"),
        }
        buckets, max_age, stale = observability.compute_review_aging(state, now=NOW)
        self.assertEqual(buckets["7_plus"], 1)
        self.assertEqual(max_age, 30)

    def test_missing_created_at_skipped(self):
        state = {"a": {"status": "pending"}, "b": _item(0)}
        buckets, _, _ = observability.compute_review_aging(state, now=NOW)
        self.assertEqual(buckets["0_1"], 1)

    def test_empty(self):
        buckets, max_age, stale = observability.compute_review_aging({}, now=NOW)
        self.assertEqual(buckets, {"0_1": 0, "1_3": 0, "3_7": 0, "7_plus": 0})
        self.assertEqual(max_age, 0)
        self.assertEqual(stale, 0)


if __name__ == "__main__":
    unittest.main()
