#!/usr/bin/env python3
"""S6 Replay / Projection 的纪律测试。

重点：首跑仅播种（不伪造跨期跃迁）、阶段跃迁由真实历史差值检测、next_stage 为顺序事实（非预测）、
历史按日期去重、validate fail-closed。
"""
from __future__ import annotations

import unittest

from replay_projection import (
    VERSION,
    append_history,
    build,
    current_snapshot,
    validate,
)


def _lc(ceid, stage="rumor", title="t", eid=None) -> dict:
    return {
        "canonical_event_id": ceid, "identity_key": eid or ceid,
        "title": title, "stage": stage, "confidence": 0.8,
        "matched_stage_count": 1, "evidence_refs": [], "reason": None,
    }


def _ev(eid, ceid, evidence=1, props=0, source=1, trust=60, topic="ai_intelligent") -> dict:
    return {
        "event_id": eid, "title": "t", "topic": topic,
        "trust": {"level": "medium", "score": trust},
        "evidence": [{"x": i} for i in range(evidence)],
        "claims": {"proposition_count": props},
        "source_count": source,
    }


def _ceid(pairs):
    return {e: c for e, c in pairs}


def _snap(ceid, date, stage="rumor", evidence=1, props=0, source=1, trust=60) -> dict:
    return {
        "date": date, "stage": stage, "evidence_count": evidence,
        "proposition_count": props, "source_count": source, "trust_score": trust,
    }


def _hist(ceid, snaps) -> dict:
    return {ceid: list(snaps)}


class TestSeedFirstRun(unittest.TestCase):
    def test_seed_no_fabricated_transition(self):
        lc = [_lc("c1", "rumor"), _lc("c2", "agreement")]
        ev = [_ev("e1", "c1"), _ev("e2", "c2")]
        doc = build(ev, lc, {}, _ceid([("e1", "c1"), ("e2", "c2")]), prior_history=None, run_date="2026-09-02")
        self.assertEqual(doc["meta"]["with_transitions"], 0)
        for r in doc["replays"]:
            self.assertEqual(r["snapshot_count"], 1)
            self.assertIn("首次观测", r["why_important_today"])
        validate(doc)  # 不抛即通过

    def test_open_question_flags_seeded(self):
        lc = [_lc("c1", "rumor")]
        doc = build([_ev("e1", "c1")], lc, {}, _ceid([("e1", "c1")]), prior_history=None, run_date="2026-09-02")
        self.assertTrue(any(o["status"] == "seeded_first_run" and o["dimension"] == "跨期回放（replay）"
                            for o in doc["open_questions"]))


class TestTransitions(unittest.TestCase):
    def test_stage_advance_detected(self):
        prior = _hist("c1", [_snap("c1", "2026-09-01", "rumor")])
        lc = [_lc("c1", "agreement")]
        doc = build([_ev("e1", "c1")], lc, {}, _ceid([("e1", "c1")]),
                    prior_history=prior, run_date="2026-09-02")
        r = next(x for x in doc["replays"] if x["canonical_event_id"] == "c1")
        self.assertEqual(r["snapshot_count"], 2)
        self.assertEqual(len(r["transitions"]), 1)
        self.assertEqual(r["transitions"][0]["from"], "rumor")
        self.assertEqual(r["transitions"][0]["to"], "agreement")
        self.assertIn("阶段前移 rumor→agreement", r["why_important_today"])

    def test_evidence_growth_detected(self):
        prior = _hist("c1", [_snap("c1", "2026-09-01", "rumor", evidence=1, props=0)])
        lc = [_lc("c1", "rumor")]
        ev = [_ev("e1", "c1", evidence=5, props=0)]  # +4 → 实质新增
        doc = build(ev, lc, {}, _ceid([("e1", "c1")]), prior_history=prior, run_date="2026-09-02")
        r = next(x for x in doc["replays"] if x["canonical_event_id"] == "c1")
        self.assertIn("证据/主张实质新增 +4", r["why_important_today"])


class TestNaSafety(unittest.TestCase):
    """回归：n/a 事件（非并购/不适用，占多数）不得让次日回放崩溃。

    真实缺陷：_why_important 直接 STAGE_ORDER.index('n/a') 抛 ValueError，
    一旦历史累计到第二天即整体崩掉（首跑无 prev 掩盖了它）。
    """

    def test_na_day_two_does_not_crash(self):
        prior = _hist("c1", [_snap("c1", "2026-09-01", "n/a")])
        lc = [_lc("c1", "n/a")]
        doc = build([_ev("e1", "c1")], lc, {}, _ceid([("e1", "c1")]),
                    prior_history=prior, run_date="2026-09-02")
        r = next(x for x in doc["replays"] if x["canonical_event_id"] == "c1")
        self.assertEqual(r["snapshot_count"], 2)
        self.assertEqual(r["current_stage"], "n/a")

    def test_na_to_na_reports_no_change(self):
        prior = _hist("c1", [_snap("c1", "2026-09-01", "n/a")])
        lc = [_lc("c1", "n/a")]
        doc = build([_ev("e1", "c1")], lc, {}, _ceid([("e1", "c1")]),
                    prior_history=prior, run_date="2026-09-02")
        r = next(x for x in doc["replays"] if x["canonical_event_id"] == "c1")
        self.assertNotIn("阶段前移", r["why_important_today"])
        self.assertIn("无显著跨期变化", r["why_important_today"])

    def test_na_to_rumor_does_not_claim_stage_advance(self):
        """n/a 表示「非并购/不适用」，不等于「rumor 之前」——不得据此断言阶段前移。"""
        prior = _hist("c1", [_snap("c1", "2026-09-01", "n/a")])
        lc = [_lc("c1", "rumor")]
        doc = build([_ev("e1", "c1")], lc, {}, _ceid([("e1", "c1")]),
                    prior_history=prior, run_date="2026-09-02")
        r = next(x for x in doc["replays"] if x["canonical_event_id"] == "c1")
        self.assertEqual(r["current_stage"], "rumor")
        self.assertNotIn("阶段前移", r["why_important_today"])

    def test_na_evidence_growth_still_detected(self):
        """n/a 事件仍可因证据实质增长而非阶段前移被识别为「变重要」。"""
        prior = _hist("c1", [_snap("c1", "2026-09-01", "n/a", evidence=1, props=0)])
        lc = [_lc("c1", "n/a")]
        ev = [_ev("e1", "c1", evidence=6, props=0)]  # +5
        doc = build(ev, lc, {}, _ceid([("e1", "c1")]), prior_history=prior, run_date="2026-09-02")
        r = next(x for x in doc["replays"] if x["canonical_event_id"] == "c1")
        self.assertIn("证据/主张实质新增 +5", r["why_important_today"])

    def test_mixed_corpus_two_day_run_is_safe(self):
        """混合语料（M&A + 多数 n/a）跨两日运行不得崩溃。"""
        pairs = [("e1", "c1"), ("e2", "c2"), ("e3", "c3")]
        prior = {
            "c1": [_snap("c1", "2026-09-01", "rumor")],
            "c2": [_snap("c2", "2026-09-01", "n/a")],
            "c3": [_snap("c3", "2026-09-01", "n/a")],
        }
        lc = [_lc("c1", "agreement"), _lc("c2", "n/a"), _lc("c3", "n/a")]
        ev = [_ev("e1", "c1"), _ev("e2", "c2"), _ev("e3", "c3")]
        doc = build(ev, lc, {}, _ceid(pairs), prior_history=prior, run_date="2026-09-02")
        self.assertEqual(doc["meta"]["total_canonical"], 3)
        self.assertEqual(doc["meta"]["with_transitions"], 1)  # 仅 c1 真实跃迁
        validate(doc)  # 不抛即通过


class TestProjection(unittest.TestCase):
    def test_next_stage_in_order(self):
        lc = [_lc("c1", "rumor")]
        doc = build([_ev("e1", "c1")], lc, {}, _ceid([("e1", "c1")]), prior_history=None, run_date="2026-09-02")
        r = next(x for x in doc["replays"] if x["canonical_event_id"] == "c1")
        self.assertEqual(r["next_stage_projection"]["stage"], "negotiation")
        self.assertIn("非预测", r["next_stage_projection"]["basis"])

    def test_next_stage_none_for_na(self):
        lc = [_lc("c1", "n/a")]
        doc = build([_ev("e1", "c1")], lc, {}, _ceid([("e1", "c1")]), prior_history=None, run_date="2026-09-02")
        r = next(x for x in doc["replays"] if x["canonical_event_id"] == "c1")
        self.assertIsNone(r["next_stage_projection"]["stage"])

    def test_next_stage_none_at_end(self):
        lc = [_lc("c1", "integration")]
        doc = build([_ev("e1", "c1")], lc, {}, _ceid([("e1", "c1")]), prior_history=None, run_date="2026-09-02")
        r = next(x for x in doc["replays"] if x["canonical_event_id"] == "c1")
        self.assertIsNone(r["next_stage_projection"]["stage"])


class TestHistoryAccumulation(unittest.TestCase):
    def test_dedup_same_date(self):
        prior = _hist("c1", [_snap("c1", "2026-09-01", "rumor")])
        current = {"c1": _snap("c1", "2026-09-01", "agreement")}  # 同日覆盖
        hist = append_history(prior, current, "2026-09-01")
        self.assertEqual(len(hist["c1"]), 1)
        self.assertEqual(hist["c1"][0]["stage"], "agreement")

    def test_append_new_date(self):
        prior = _hist("c1", [_snap("c1", "2026-09-01", "rumor")])
        current = {"c1": _snap("c1", "2026-09-02", "agreement")}
        hist = append_history(prior, current, "2026-09-02")
        self.assertEqual(len(hist["c1"]), 2)

    def test_snapshot_uses_lifecycle_stage(self):
        lc = [_lc("c1", "regulatory")]
        snap = current_snapshot([_ev("e1", "c1")], lc, _ceid([("e1", "c1")]), "2026-09-02")
        self.assertEqual(snap["c1"]["stage"], "regulatory")
        self.assertEqual(snap["c1"]["evidence_count"], 1)


class TestValidation(unittest.TestCase):
    def test_validate_rejects_bad_stage(self):
        lc = [_lc("c1", "rumor")]
        doc = build([_ev("e1", "c1")], lc, {}, _ceid([("e1", "c1")]), prior_history=None, run_date="2026-09-02")
        doc["replays"][0]["current_stage"] = "bogus"
        with self.assertRaises(AssertionError):
            validate(doc)

    def test_validate_rejects_missing_canonical(self):
        lc = [_lc("c1", "rumor")]
        doc = build([_ev("e1", "c1")], lc, {}, _ceid([("e1", "c1")]), prior_history=None, run_date="2026-09-02")
        doc["replays"][0].pop("canonical_event_id")
        with self.assertRaises(AssertionError):
            validate(doc)

    def test_validate_rejects_empty_chain(self):
        lc = [_lc("c1", "rumor")]
        doc = build([_ev("e1", "c1")], lc, {}, _ceid([("e1", "c1")]), prior_history=None, run_date="2026-09-02")
        doc["replays"][0]["replay_chain"] = []
        with self.assertRaises(AssertionError):
            validate(doc)


if __name__ == "__main__":
    unittest.main()
