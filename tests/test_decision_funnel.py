#!/usr/bin/env python3
"""S5 Decision Funnel 的纪律测试。

重点：漏斗计数自洽、承接 E2 账本、待决分桶为可观测代理（不伪造业务紧急度）、
样本<30 不结论、validate fail-closed；Sprint 3 新增：§9.4 六条件评估 + §9.5 分角色计数。
"""
from __future__ import annotations

import unittest

from decision_funnel import (
    ROLE_FROZEN,
    ROLE_LABEL,
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


def _build(items, ledger=None, intel=None, canonical=None, alert_ceids=None,
           t1_alert_ceids=None, watch_topics=None, watch_kw=None, feedback=None,
           ceid_map=None):
    """用默认空上下文包一层，便于旧用例沿用简洁签名。"""
    return build(
        items,
        ledger or [],
        intel or [],
        canonical or {},
        set(alert_ceids or []),
        set(t1_alert_ceids or []),
        set(watch_topics or []),
        set(watch_kw or []),
        dict(feedback or {}),
        ceid_map or _ceid([i["event_id"] for i in items]),
    )


class TestFunnelConsistency(unittest.TestCase):
    def test_required_equals_decided_plus_pending(self):
        items = [
            _item("e1", reasons=[{"type": "conflict"}]),
            _item("e2", priority=80),
            _item("e3", priority=30),
            _item("d1", decision={"urgency": "watch", "action": "a", "decided_at": "2026-09-02T00:00:00Z"}),
        ]
        ledger = [_ledger("d1")]
        doc = _build(items, ledger=ledger)
        m = doc["meta"]
        self.assertEqual(m["decision_required"], 4)
        self.assertEqual(m["decided"], 1)
        self.assertEqual(m["pending"], 3)
        self.assertEqual(m["decision_required"], m["decided"] + m["pending"])
        self.assertEqual(sum(m["pending_by_role"].values()), m["pending"])
        validate(doc)  # 不抛即通过

    def test_bucket_counts_sum_to_pending(self):
        items = [
            _item("e1", reasons=[{"type": "conflict"}]),
            _item("e2", priority=80),
            _item("e3", priority=30),
        ]
        doc = _build(items)
        m = doc["meta"]
        self.assertEqual(sum(m["pending_by_tier"].values()), m["pending"])
        self.assertEqual(m["pending_by_tier"]["now"], 1)
        self.assertEqual(m["pending_by_tier"]["soon"], 1)
        self.assertEqual(m["pending_by_tier"]["watch"], 1)

    def test_role_counts_sum_to_pending(self):
        items = [_item("e1"), _item("e2"), _item("e3")]
        doc = _build(items)
        m = doc["meta"]
        self.assertEqual(sum(m["pending_by_role"].values()), m["pending"])
        for r in ROLE_FROZEN:
            self.assertIn(r, m["pending_by_role"])


class TestTierAssignment(unittest.TestCase):
    def test_conflict_reason_is_now(self):
        doc = _build([_item("e1", reasons=[{"type": "conflict"}])])
        self.assertEqual(doc["funnel"]["now"][0]["tier"], "now")

    def test_claim_conflict_reason_is_now(self):
        doc = _build([_item("e1", reasons=[{"type": "claim_conflict"}])])
        self.assertEqual(doc["funnel"]["now"][0]["tier"], "now")

    def test_high_priority_is_soon(self):
        doc = _build([_item("e1", priority=80)])
        self.assertEqual(doc["funnel"]["soon"][0]["tier"], "soon")

    def test_low_priority_event_cluster_is_watch(self):
        doc = _build([_item("e1", priority=30)])
        self.assertEqual(doc["funnel"]["watch"][0]["tier"], "watch")

    def test_change_impact_reason_is_soon(self):
        doc = _build([_item("e1", reasons=[{"type": "change_impact"}])])
        self.assertEqual(doc["funnel"]["soon"][0]["tier"], "soon")


class TestDecidedSources(unittest.TestCase):
    def test_decided_from_ledger(self):
        items = [_item("e1")]
        ledger = [_ledger("e1", urgency="now")]
        doc = _build(items, ledger=ledger)
        self.assertEqual(doc["meta"]["decided"], 1)
        self.assertEqual(doc["decided_list"][0]["urgency"], "now")
        self.assertEqual(doc["decided_list"][0]["canonical_event_id"], "e1")
        self.assertEqual(doc["decided_list"][0]["decided_at"], "2026-09-02T00:00:00Z")

    def test_decided_from_review_decision_only(self):
        items = [_item("e1", decision={"urgency": "watch", "action": "a", "decided_at": "2026-09-02T00:00:00Z"})]
        doc = _build(items)  # 无账本
        self.assertEqual(doc["meta"]["decided"], 1)
        self.assertEqual(doc["decided_list"][0]["decided_at"], "2026-09-02T00:00:00Z")

    def test_pending_has_no_fabricated_urgency(self):
        items = [_item("e1", reasons=[{"type": "conflict"}])]
        doc = _build(items)
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
        doc = _build(items)
        top = doc["top_pending"]
        self.assertGreaterEqual(TIER_RANK[top[0]["tier"]], TIER_RANK[top[1]["tier"]])
        now_tiers = [p for p in top if p["tier"] == "now"]
        self.assertEqual([p["priority"] for p in now_tiers], [90, 60])


class TestValidation(unittest.TestCase):
    def test_validate_rejects_inconsistent_counts(self):
        items = [_item("e1"), _item("e2")]
        doc = _build(items)
        doc["meta"]["pending"] += 1  # 破坏自洽
        with self.assertRaises(AssertionError):
            validate(doc)

    def test_validate_rejects_inconsistent_role_counts(self):
        items = [_item("e1")]
        doc = _build(items)
        doc["meta"]["pending_by_role"]["other"] += 1  # 破坏分角色自洽
        with self.assertRaises(AssertionError):
            validate(doc)

    def test_validate_rejects_bad_tier(self):
        items = [_item("e1")]
        doc = _build(items)
        doc["funnel"]["now"].append({"event_id": "x", "canonical_event_id": "x",
                                     "tier": "bogus", "priority": 50, "reason_types": [], "role": "other"})
        with self.assertRaises(AssertionError):
            validate(doc)

    def test_validate_rejects_bad_role(self):
        items = [_item("e1")]
        doc = _build(items)
        doc["funnel"]["watch"][0]["role"] = "bogus"
        with self.assertRaises(AssertionError):
            validate(doc)

    def test_validate_rejects_missing_canonical(self):
        items = [_item("e1")]
        doc = _build(items)
        doc["funnel"]["watch"][0].pop("canonical_event_id")
        with self.assertRaises(AssertionError):
            validate(doc)


class TestHonestyGates(unittest.TestCase):
    def test_open_question_blocks_preference_below_threshold(self):
        items = [_item("e1")]
        ledger = [_ledger("e1")]  # 1 < 30
        doc = _build(items, ledger=ledger)
        self.assertFalse(doc["meta"]["reached_threshold"])
        self.assertTrue(any(o["dimension"] == "决策偏好结论" and o["status"] == "insufficient_sample"
                            for o in doc["open_questions"]))

    def test_open_question_clears_at_threshold(self):
        items = [_item("e1")]
        ledger = [_ledger(f"e{i}") for i in range(30)]  # 30 >= 30
        doc = _build(items, ledger=ledger)
        self.assertTrue(doc["meta"]["reached_threshold"])
        self.assertFalse(any(o["dimension"] == "决策偏好结论" and o["status"] == "insufficient_sample"
                             for o in doc["open_questions"]))


class TestSixConditions(unittest.TestCase):
    """§9.4 六条件硬化：每条待决 CE 显式评估；decision_ready 子集排除单源+监管/评级。"""

    def _ce(self, domain="regulatory", event_type="regulatory", stage="n/a", status="issued",
            topic="", title="", key_entity="") -> dict:
        return {
            "canonical_event_id": "c1", "domain": domain, "event_type": event_type,
            "title": title, "topic": topic, "key_entity": key_entity,
            "lifecycle": {"domain": domain, "stage": stage, "status": status},
        }

    def _intel_ce(self, ceid, evidence=2, trust="medium", source_count=2) -> dict:
        return {"canonical_event_id": ceid, "evidence": [{}] * evidence,
                "trust": {"level": trust}, "source_count": source_count}

    def test_regulatory_issued_watched_meets_six(self):
        """监管 issued + 在监控 + 语义变化 + 决策集 + 证据可信 → 达门。"""
        ce = self._ce(domain="regulatory", status="issued", title="监管批复", topic="regulatory_change")
        items = [_item("c1", title="监管批复", topic="regulatory_change")]
        canonical = {"canonical_events": {"c1": ce}}
        intel = [self._intel_ce("c1", evidence=2, trust="medium", source_count=2)]
        doc = _build(items, intel=intel, canonical=canonical,
                    alert_ceids=["c1"], watch_topics={"regulatory_change"},
                    watch_kw={"监管", "批复"})
        p = doc["top_pending"][0]
        self.assertTrue(p["meets_six"], f"应达门，实际 failed={p['failed_conditions']}")
        self.assertIn("c1", doc["meta"]["decision_ready_ceids"])

    def test_single_source_regulatory_excluded_from_ready(self):
        """单源+监管：按纪律不得进入 decision_ready（条件 4 失败）。"""
        ce = self._ce(domain="regulatory", status="issued")
        items = [_item("c1", title="监管批复", topic="regulatory_change")]
        canonical = {"canonical_events": {"c1": ce}}
        intel = [self._intel_ce("c1", evidence=1, trust="low", source_count=1)]
        doc = _build(items, intel=intel, canonical=canonical,
                    alert_ceids=["c1"], watch_topics={"regulatory_change"},
                    watch_kw={"监管", "批复"})
        p = doc["top_pending"][0]
        self.assertIn(4, p["failed_conditions"], "单源+监管应卡条件 4")
        self.assertNotIn("c1", doc["meta"]["decision_ready_ceids"])

    def test_unmonitored_not_decision_ready(self):
        """不在监控、无 T1、未 acted → 条件 1 失败（留复核页，不进 decision_ready）。"""
        ce = self._ce(domain="other", status=None)
        items = [_item("c1")]
        canonical = {"canonical_events": {"c1": ce}}
        intel = [self._intel_ce("c1", evidence=2, trust="medium", source_count=2)]
        doc = _build(items, intel=intel, canonical=canonical)
        p = doc["top_pending"][0]
        self.assertIn(1, p["failed_conditions"])
        self.assertNotIn("c1", doc["meta"]["decision_ready_ceids"])

    def test_acquisition_agreement_in_decision_set(self):
        """并购 agreement 阶段 + 监控 + 证据可信 → 达门（条件 3 通过）。"""
        ce = self._ce(domain="acquisition", event_type="acquisition", stage="agreement", status=None,
                      title="股权收购", topic="capital_reinsurance")
        items = [_item("c1", title="股权收购", topic="capital_reinsurance")]
        canonical = {"canonical_events": {"c1": ce}}
        intel = [self._intel_ce("c1", evidence=2, trust="high", source_count=3)]
        doc = _build(items, intel=intel, canonical=canonical,
                    alert_ceids=["c1"], watch_kw={"并购", "收购", "股权"})
        p = doc["top_pending"][0]
        self.assertTrue(p["meets_six"], f"应达门，实际 failed={p['failed_conditions']}")

    def test_feedback_snoozed_blocks_condition5(self):
        """反馈 snoozed → 本角色已处理（条件 5 失败）。"""
        ce = self._ce(domain="regulatory", status="issued", title="监管批复", topic="regulatory_change")
        items = [_item("c1", title="监管批复", topic="regulatory_change")]
        canonical = {"canonical_events": {"c1": ce}}
        intel = [self._intel_ce("c1", evidence=2, trust="medium", source_count=2)]
        doc = _build(items, intel=intel, canonical=canonical, alert_ceids=["c1"],
                    watch_topics={"regulatory_change"}, watch_kw={"监管"},
                    feedback={"c1": "snoozed"})
        p = doc["top_pending"][0]
        self.assertIn(5, p["failed_conditions"])


class TestRoleClassification(unittest.TestCase):
    """§9.5 分角色计数：冻结四类（AI/并购/监管/健康险）+ other。"""

    def test_role_ai(self):
        from decision_funnel import _role_of
        self.assertEqual(_role_of({"domain": "other", "event_type": "ai", "topic": "ai_intelligent"}), "ai")

    def test_role_ma(self):
        from decision_funnel import _role_of
        self.assertEqual(_role_of({"domain": "acquisition", "event_type": "acquisition"}), "ma")
        self.assertEqual(_role_of({"domain": "other", "title": "某股权收购案", "key_entity": ""}), "ma")

    def test_role_regulatory(self):
        from decision_funnel import _role_of
        self.assertEqual(_role_of({"domain": "regulatory", "event_type": "regulatory"}), "regulatory")

    def test_role_health(self):
        from decision_funnel import _role_of
        self.assertEqual(_role_of({"domain": "other", "title": "惠民保产品上线", "topic": "product_innovation"}), "health")

    def test_role_other(self):
        from decision_funnel import _role_of
        self.assertEqual(_role_of({"domain": "other", "event_type": "market_entry", "title": "x"}), "other")


if __name__ == "__main__":
    unittest.main()
