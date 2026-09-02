#!/usr/bin/env python3
"""S4 Semantic Alert 的纪律测试。

重点：两层收敛（Internal Diff → Semantic Alert）是否真把变化收敛为 ≤8 条、
delta 不伪造、首跑仅种子、validate fail-closed。
"""
from __future__ import annotations

import unittest

from semantic_alert import (
    ALERT_TYPES,
    MAX_ALERTS,
    VERSION,
    build,
    validate,
)


def _ev(event_id: str, trust: int = 60, evidence: int = 1, props: int = 0,
        review: bool = False, title: str = "t", topic: str = "ai_intelligent") -> dict:
    return {
        "event_id": event_id,
        "title": title,
        "topic": topic,
        "trust": {"level": "medium", "score": trust},
        "evidence": [{"x": i} for i in range(evidence)],
        "claims": {"proposition_count": props},
        "review_required": review,
    }


def _brief(event_id: str, priority: int = 50) -> dict:
    return {"event_id": event_id, "daily_priority": priority}


def _ceid(ids):
    return {i: i for i in ids}


class TestSeedFirstRun(unittest.TestCase):
    def test_seed_without_baseline_emits_current_attention(self):
        events = [_ev("e1", review=True), _ev("e2", review=True), _ev("e3")]
        brief = [_brief("e1", 90), _brief("e2", 80)]
        doc = build(events, [], [], brief, None, _ceid(["e1", "e2", "e3"]))
        self.assertEqual(doc["meta"]["baseline_present"], False)
        self.assertEqual(doc["meta"]["basis"], "seed_first_run")
        self.assertLessEqual(len(doc["semantic_alerts"]), MAX_ALERTS)
        # 待复核且无决策的事件应进入 DECISION_REQUIRED（seed）
        types = [a["type"] for a in doc["semantic_alerts"]]
        self.assertIn("DECISION_REQUIRED", types)
        for a in doc["semantic_alerts"]:
            self.assertEqual(a["basis"], "seed")
        validate(doc)  # 不抛即通过

    def test_seed_no_fabricated_delta(self):
        """首跑无基线：internal_diffs 必须为空（不得伪造变化）。"""
        doc = build([_ev("e1", review=True)], [], [], [_brief("e1", 90)], None, _ceid(["e1"]))
        self.assertEqual(doc["internal_diffs"], [])
        self.assertTrue(any(o["dimension"] == "历史基线（delta 类告警）" for o in doc["open_questions"]))


class TestDeltaAlerts(unittest.TestCase):
    def test_stage_change_emits_event_stage_changed(self):
        base = {"e1": {"stage": "rumor", "trust_score": 60, "evidence_count": 1,
                       "proposition_count": 0, "decision_urgency": None,
                       "review_required": False, "daily_priority": 50, "event_id": "e1", "title": "t", "topic": "x"}}
        events = [_ev("e1", trust=60)]
        lifecycle = [{"canonical_event_id": "e1", "identity_key": "e1", "title": "t", "stage": "agreement"}]
        doc = build(events, lifecycle, [], [], base, _ceid(["e1"]))
        alerts = doc["semantic_alerts"]
        self.assertTrue(any(a["type"] == "EVENT_STAGE_CHANGED" for a in alerts))
        st = next(a for a in alerts if a["type"] == "EVENT_STAGE_CHANGED")
        self.assertEqual(st["severity"], "high")  # 阶段前移 = 高
        self.assertEqual(st["basis"], "delta")
        self.assertIn("rumor", st["rationale"])
        self.assertIn("agreement", st["rationale"])

    def test_trust_drop_emits_risk_increased(self):
        base = {"e1": {"stage": "n/a", "trust_score": 70, "evidence_count": 1,
                       "proposition_count": 0, "decision_urgency": None,
                       "review_required": False, "daily_priority": 50, "event_id": "e1", "title": "t", "topic": "x"}}
        doc = build([_ev("e1", trust=50)], [], [], [], base, _ceid(["e1"]))
        risk = next((a for a in doc["semantic_alerts"] if a["type"] == "RISK_INCREASED"), None)
        self.assertIsNotNone(risk)
        self.assertEqual(risk["severity"], "high")  # 降 20 ≥15
        self.assertEqual(risk["basis"], "delta")

    def test_evidence_increase_emits_material_changed(self):
        base = {"e1": {"stage": "n/a", "trust_score": 60, "evidence_count": 1,
                       "proposition_count": 0, "decision_urgency": None,
                       "review_required": False, "daily_priority": 50, "event_id": "e1", "title": "t", "topic": "x"}}
        doc = build([_ev("e1", evidence=4, props=2)], [], [], [], base, _ceid(["e1"]))
        mat = next((a for a in doc["semantic_alerts"] if a["type"] == "EVENT_MATERIAL_CHANGED"), None)
        self.assertIsNotNone(mat)
        self.assertEqual(mat["severity"], "high")  # 增量 3+2 >=3
        self.assertEqual(mat["basis"], "delta")

    def test_urgency_escalation_emits_decision_required(self):
        base = {"e1": {"stage": "n/a", "trust_score": 60, "evidence_count": 1,
                       "proposition_count": 0, "decision_urgency": "watch",
                       "review_required": False, "daily_priority": 50, "event_id": "e1", "title": "t", "topic": "x"}}
        doc = build([_ev("e1")], [], [{"event_id": "e1", "urgency": "now"}], [], base, _ceid(["e1"]))
        dec = next((a for a in doc["semantic_alerts"] if a["type"] == "DECISION_REQUIRED"), None)
        self.assertIsNotNone(dec)
        self.assertEqual(dec["severity"], "high")
        self.assertEqual(dec["basis"], "delta")
        self.assertIn("now", dec["rationale"])


class TestCapAndValidation(unittest.TestCase):
    def test_cap_at_eight(self):
        ids = [f"e{i}" for i in range(20)]
        base = {i: {"stage": "rumor", "trust_score": 60, "evidence_count": 1,
                   "proposition_count": 0, "decision_urgency": None,
                   "review_required": False, "daily_priority": 50, "event_id": i, "title": "t", "topic": "x"}
                for i in ids}
        lifecycle = [{"canonical_event_id": i, "identity_key": i, "title": "t", "stage": "agreement"} for i in ids]
        doc = build([_ev(i) for i in ids], lifecycle, [], [], base, _ceid(ids))
        self.assertLessEqual(len(doc["semantic_alerts"]), MAX_ALERTS)
        self.assertEqual(len(doc["semantic_alerts"]), MAX_ALERTS)

    def test_validate_rejects_over_cap(self):
        doc = build([_ev("e1", review=True)], [], [], [_brief("e1", 90)], None, _ceid(["e1"]))
        # 用 9 条合法告警覆盖（MAX_ALERTS=8），确保真实超限
        over = [{
            "type": "DECISION_REQUIRED", "canonical_event_id": f"x{i}",
            "event_id": f"x{i}", "title": f"t{i}", "topic": "ai_intelligent",
            "severity": "low", "rationale": "r", "basis": "seed", "changed_fields": [],
        } for i in range(MAX_ALERTS + 1)]
        doc["semantic_alerts"] = over
        doc["meta"]["alert_count"] = len(over)
        self.assertGreater(len(doc["semantic_alerts"]), MAX_ALERTS)
        with self.assertRaises(AssertionError):
            validate(doc)

    def test_validate_rejects_bad_type(self):
        doc = build([_ev("e1", review=True)], [], [], [_brief("e1", 90)], None, _ceid(["e1"]))
        doc["semantic_alerts"][0]["type"] = "NOT_A_TYPE"
        with self.assertRaises(AssertionError):
            validate(doc)

    def test_validate_rejects_missing_severity(self):
        doc = build([_ev("e1", review=True)], [], [], [_brief("e1", 90)], None, _ceid(["e1"]))
        doc["semantic_alerts"][0].pop("severity")
        with self.assertRaises(AssertionError):
            validate(doc)

    def test_alert_types_are_closed_set(self):
        self.assertEqual(ALERT_TYPES, {
            "EVENT_STAGE_CHANGED", "EVENT_MATERIAL_CHANGED",
            "RISK_INCREASED", "DECISION_REQUIRED",
        })


if __name__ == "__main__":
    unittest.main()
