#!/usr/bin/env python3
"""P1-2 Executive Decision Card 契约测试。

DEC-1：决策卡六要素（business_impact / affected_functions / potential_opportunity /
potential_risk / what_to_monitor / recommended_next_step）全部为 event 已有信号的映射。
DEC-2：8 角色分发，同一事件不同视角（数据同源、视角不同）。
"""
import unittest

from decision import (
    CONTEXT_FIELDS,
    IMPACT_FACETS,
    ROLE_ACTIONS,
    build_decisions,
    context_coverage,
)


def event(**overrides):
    row = {
        "event_id": "evt_1",
        "event_type": "claims_loss",
        "topic": "climate_catastrophe",
        "scores": {"intelligence_score": 80},
        "trust": {"level": "high", "conflict": False},
        "evidence_coverage": 90,
        "evidence_status": "cross_checked",
        "insight": {
            "what_to_watch": "跟踪巨灾赔付与再保市场报价",
            "signals": {"scores": {"financial_impact": 70, "strategic_change": 14}},
        },
    }
    row.update(overrides)
    return row


TEMPORAL = {"topic_signals": [{"topic": "climate_catastrophe", "phase": "accelerating", "signal_strength": 90}]}


class DecisionContextTests(unittest.TestCase):
    def test_six_context_fields_present_and_non_empty(self):
        rows = build_decisions([event()], TEMPORAL, "executive")
        self.assertEqual(len(rows), 1)
        context = rows[0]["context"]
        for field in CONTEXT_FIELDS:
            self.assertTrue(context[field], f"context.{field} 不应为空")
        self.assertEqual(context_coverage(rows), 1.0)

    def test_business_impact_facets_follow_type_and_signals(self):
        rows = build_decisions([event()], TEMPORAL, "executive")
        impact = rows[0]["context"]["business_impact"]
        # claims_loss 类型直接命中核保分面 → 影响强度 = 情报分。
        self.assertEqual(impact["underwriting"], 80)
        # 信号激活但类型未命中的分面按 45% 折算：strategic_change=14 → 6。
        self.assertEqual(impact["strategic"], 6)
        self.assertEqual(set(impact), set(IMPACT_FACETS))

    def test_regulatory_type_drives_compliance_facet(self):
        rows = build_decisions([event(event_type="regulatory")], TEMPORAL, "executive")
        impact = rows[0]["context"]["business_impact"]
        self.assertEqual(impact["compliance"], 80)

    def test_affected_functions_sorted_and_labeled(self):
        rows = build_decisions([event()], TEMPORAL, "executive")
        functions = rows[0]["context"]["affected_functions"]
        self.assertEqual(functions[0]["function"], "underwriting")
        self.assertEqual(functions[0]["label"], "核保")
        self.assertEqual(functions[0]["impact"], 80)
        values = [f["impact"] for f in functions]
        self.assertEqual(values, sorted(values, reverse=True))

    def test_what_to_monitor_inherits_insight_watch(self):
        rows = build_decisions([event()], TEMPORAL, "executive")
        self.assertEqual(rows[0]["context"]["what_to_monitor"], "跟踪巨灾赔付与再保市场报价")

    def test_risk_qualifiers_follow_evidence_signals(self):
        base = build_decisions([event()], TEMPORAL, "executive")[0]["context"]["potential_risk"]
        self.assertIn("赔付恶化与准备金不足", base)
        single = build_decisions([event(evidence_status="single_source", evidence_coverage=25)], TEMPORAL, "executive")[0]["context"]["potential_risk"]
        self.assertTrue(any("单一来源" in x for x in single))
        conflicted = build_decisions([event(trust={"level": "medium", "conflict": True})], TEMPORAL, "executive")[0]["context"]["potential_risk"]
        self.assertTrue(any("冲突" in x for x in conflicted))

    def test_next_step_carries_review_qualifier(self):
        reviewed = build_decisions([event(trust={"level": "medium", "conflict": False})], TEMPORAL, "executive")[0]
        self.assertIn("人工复核", reviewed["context"]["recommended_next_step"])
        clean = build_decisions([event()], TEMPORAL, "executive")[0]
        self.assertNotIn("人工复核", clean["context"]["recommended_next_step"])
        self.assertIn(clean["action"], clean["context"]["recommended_next_step"])

    def test_opportunity_mapped_from_event_type(self):
        rows = build_decisions([event(event_type="market_entry")], TEMPORAL, "executive")
        self.assertEqual(rows[0]["context"]["potential_opportunity"], ["新市场/新渠道的先发布局机会"])


class RoleDistributionTests(unittest.TestCase):
    def test_all_eight_roles_distributed(self):
        self.assertEqual(len(ROLE_ACTIONS), 8)
        events = [event(), event(event_id="evt_2", event_type="regulatory", topic="regulatory_change")]
        temporal = {"topic_signals": [
            {"topic": "climate_catastrophe", "phase": "accelerating", "signal_strength": 90},
            {"topic": "regulatory_change", "phase": "forming", "signal_strength": 60},
        ]}
        by_role = {role: build_decisions(events, temporal, role) for role in ROLE_ACTIONS}
        self.assertEqual(set(by_role), set(ROLE_ACTIONS))
        for role, rows in by_role.items():
            self.assertTrue(rows)
            for row in rows:
                self.assertEqual(row["role"], role)

    def test_same_event_different_lens(self):
        events = [event()]
        executive = build_decisions(events, TEMPORAL, "executive")
        underwriting = build_decisions(events, TEMPORAL, "underwriting")
        actuarial = build_decisions(events, TEMPORAL, "actuarial")
        # claims_loss：核保/精算有专属行动模板，高管回退到默认跟踪动作。
        self.assertIn("风险假设", underwriting[0]["action"])
        self.assertIn("损失趋势", actuarial[0]["action"])
        self.assertNotEqual(executive[0]["action"], underwriting[0]["action"])
        # 数据同源：三视角的 urgency 与依据一致。
        self.assertEqual(executive[0]["urgency"], underwriting[0]["urgency"])
        self.assertEqual(executive[0]["basis"], underwriting[0]["basis"])

    def test_role_cards_keep_full_context(self):
        for role in ROLE_ACTIONS:
            rows = build_decisions([event()], TEMPORAL, role)
            self.assertEqual(context_coverage(rows), 1.0, role)

    def test_context_coverage_zero_on_empty(self):
        self.assertEqual(context_coverage([]), 0.0)
        self.assertEqual(context_coverage([{"event_id": "x"}]), 0.0)


class RoleGroupingIntegrationTests(unittest.TestCase):
    def test_grouped_artifact_coverage_meets_gate(self):
        events = [
            event(),
            event(event_id="evt_2", event_type="regulatory", topic="regulatory_change",
                  insight={"what_to_watch": "跟踪监管落地节奏", "signals": {"scores": {"regulatory_change": 42}}}),
            event(event_id="evt_3", event_type="industry_update", topic=None,
                  insight={"what_to_watch": "关注行业动向", "signals": {"scores": {"market_change": 28}}}),
        ]
        temporal = {"topic_signals": [
            {"topic": "climate_catastrophe", "phase": "accelerating", "signal_strength": 90},
            {"topic": "regulatory_change", "phase": "forming", "signal_strength": 60},
        ]}
        by_role = {role: build_decisions(events, temporal, role)[:12] for role in ROLE_ACTIONS}
        cards = [card for rows in by_role.values() for card in rows]
        self.assertGreaterEqual(context_coverage(cards), 0.9)
        # 弱信号事件也有分面参照，不凭空补职能。
        industry = by_role["executive"][-1]["context"]["affected_functions"]
        self.assertTrue(industry)


if __name__ == "__main__":
    unittest.main()
