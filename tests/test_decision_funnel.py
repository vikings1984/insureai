#!/usr/bin/env python3
"""S5 Decision Funnel 的纪律测试。

重点：漏斗计数自洽、承接 E2 账本、待决分桶为可观测代理（不伪造业务紧急度）、
样本<30 不结论、validate fail-closed。
"""
from __future__ import annotations

import unittest

from decision_funnel import (
    TIER_RANK,
    VERSION,
    build,
    validate,
)


def _item(event_id, status="pending", priority=50, reasons=None, decision=None,
          title="t", topic="ai_intelligent", trust="medium") -> dict:
    return {
        "event_id": event_id,
        "status": status,
        "priority": priority,
        "title": title,
        "topic": topic,
        "trust_level": trust,
        "reasons": reasons or [{"type": "event_cluster", "reason": "r"}],
        "decision": decision,
    }


def _ledger(event_id, urgency="watch", decided_at="2026-09-02T00:00:00Z") -> dict:
    return {"event_id": event_id, "role": "executive", "urgency": urgency, "action": "a", "decided_at": decided_at}


def _intel(event_id, urgency="watch", decided_at="2026-09-02T00:00:00Z") -> dict:
    return {"event_id": event_id, "urgency": urgency, "decided_at": decided_at}


def _ceid(ids):
    return {i: i for i in ids}


class TestFunnelConsistency(unittest.TestCase):
    def test_required_equals_decided_plus_pending(self):
        items = [
            _item("e1", reasons=[{"type": "conflict"}]),
            _item("e2", priority=80),
            _item("e3", priority=30),
            _item("d1", decision={"urgency": "watch", "action": "a", "decided_at": "2026-09-02T00:00:00Z"}),
        ]
        ledger = [_ledger("d1")]
        doc = build(items, ledger, [], _ceid(["e1", "e2", "e3", "d1"]))
        m = doc["meta"]
        self.assertEqual(m["decision_required"], 4)
        self.assertEqual(m["decided"], 1)
        self.assertEqual(m["pending"], 3)
        self.assertEqual(m["decision_required"], m["decided"] + m["pending"])
        validate(doc)  # 不抛即通过

    def test_bucket_counts_sum_to_pending(self):
        items = [
            _item("e1", reasons=[{"type": "conflict"}]),
            _item("e2", priority=80),
            _item("e3", priority=30),
        ]
        doc = build(items, [], [], _ceid(["e1", "e2", "e3"]))
        m = doc["meta"]
        self.assertEqual(sum(m["pending_by_tier"].values()), m["pending"])
        self.assertEqual(m["pending_by_tier"]["now"], 1)
        self.assertEqual(m["pending_by_tier"]["soon"], 1)
        self.assertEqual(m["pending_by_tier"]["watch"], 1)


class TestTierAssignment(unittest.TestCase):
    def test_conflict_reason_is_now(self):
        doc = build([_item("e1", reasons=[{"type": "conflict"}])], [], [], _ceid(["e1"]))
        self.assertEqual(doc["funnel"]["now"][0]["tier"], "now")

    def test_claim_conflict_reason_is_now(self):
        doc = build([_item("e1", reasons=[{"type": "claim_conflict"}])], [], [], _ceid(["e1"]))
        self.assertEqual(doc["funnel"]["now"][0]["tier"], "now")

    def test_high_priority_is_soon(self):
        doc = build([_item("e1", priority=80)], [], [], _ceid(["e1"]))
        self.assertEqual(doc["funnel"]["soon"][0]["tier"], "soon")

    def test_low_priority_event_cluster_is_watch(self):
        doc = build([_item("e1", priority=30)], [], [], _ceid(["e1"]))
        self.assertEqual(doc["funnel"]["watch"][0]["tier"], "watch")

    def test_change_impact_reason_is_soon(self):
        doc = build([_item("e1", reasons=[{"type": "change_impact"}])], [], [], _ceid(["e1"]))
        self.assertEqual(doc["funnel"]["soon"][0]["tier"], "soon")


class TestDecidedSources(unittest.TestCase):
    def test_decided_from_ledger(self):
        items = [_item("e1")]
        ledger = [_ledger("e1", urgency="now")]
        doc = build(items, ledger, [], _ceid(["e1"]))
        self.assertEqual(doc["meta"]["decided"], 1)
        self.assertEqual(doc["decided_list"][0]["urgency"], "now")
        self.assertEqual(doc["decided_list"][0]["canonical_event_id"], "e1")

    def test_decided_from_review_decision_only(self):
        items = [_item("e1", decision={"urgency": "watch", "action": "a", "decided_at": "2026-09-02T00:00:00Z"})]
        doc = build(items, [], [], _ceid(["e1"]))  # 无账本
        self.assertEqual(doc["meta"]["decided"], 1)
        self.assertEqual(doc["decided_list"][0]["decided_at"], "2026-09-02T00:00:00Z")

    def test_pending_has_no_fabricated_urgency(self):
        items = [_item("e1", reasons=[{"type": "conflict"}])]
        doc = build(items, [], [], _ceid(["e1"]))
        for p in doc["top_pending"] + doc["funnel"]["now"] + doc["funnel"]["soon"] + doc["funnel"]["watch"]:
            self.assertIsNone(p.get("urgency"), "待决项不得伪造业务紧急度标签")


class TestTopPendingRanking(unittest.TestCase):
    def test_top_pending_ordered_by_tier_then_priority(self):
        items = [
            _item("e1", priority=30),                     # watch
            _item("e2", priority=90, reasons=[{"type": "conflict"}]),  # now/90
            _item("e3", priority=60, reasons=[{"type": "conflict"}]),  # now/60
            _item("e4", priority=95),                     # soon/95
        ]
        doc = build(items, [], [], _ceid(["e1", "e2", "e3", "e4"]))
        top = doc["top_pending"]
        self.assertGreaterEqual(TIER_RANK[top[0]["tier"]], TIER_RANK[top[1]["tier"]])
        # 同 tier 内优先级降序
        now_tiers = [p for p in top if p["tier"] == "now"]
        self.assertEqual([p["priority"] for p in now_tiers], [90, 60])


class TestValidation(unittest.TestCase):
    def test_validate_rejects_inconsistent_counts(self):
        items = [_item("e1"), _item("e2")]
        doc = build(items, [], [], _ceid(["e1", "e2"]))
        doc["meta"]["pending"] += 1  # 破坏自洽
        with self.assertRaises(AssertionError):
            validate(doc)

    def test_validate_rejects_bad_tier(self):
        items = [_item("e1")]
        doc = build(items, [], [], _ceid(["e1"]))
        doc["funnel"]["now"].append({"event_id": "x", "canonical_event_id": "x",
                                     "tier": "bogus", "priority": 50, "reason_types": []})
        with self.assertRaises(AssertionError):
            validate(doc)

    def test_validate_rejects_missing_canonical(self):
        items = [_item("e1")]
        doc = build(items, [], [], _ceid(["e1"]))
        doc["funnel"]["watch"][0].pop("canonical_event_id")
        with self.assertRaises(AssertionError):
            validate(doc)


class TestHonestyGates(unittest.TestCase):
    def test_open_question_blocks_preference_below_threshold(self):
        items = [_item("e1")]
        ledger = [_ledger("e1")]  # 1 < 30
        doc = build(items, ledger, [], _ceid(["e1"]))
        self.assertFalse(doc["meta"]["reached_threshold"])
        self.assertTrue(any(o["dimension"] == "决策偏好结论" and o["status"] == "insufficient_sample"
                            for o in doc["open_questions"]))

    def test_open_question_clears_at_threshold(self):
        items = [_item("e1")]
        ledger = [_ledger(f"e{i}") for i in range(30)]  # 30 >= 30
        doc = build(items, ledger, [], _ceid(["e1"]))
        self.assertTrue(doc["meta"]["reached_threshold"])
        self.assertFalse(any(o["dimension"] == "决策偏好结论" and o["status"] == "insufficient_sample"
                             for o in doc["open_questions"]))


if __name__ == "__main__":
    unittest.main()
