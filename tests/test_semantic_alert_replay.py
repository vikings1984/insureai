#!/usr/bin/env python3
"""P0-A 跨日语义变化回归测试（Event OS 第四阶段「生产验证」）。

reviewer 的核心担忧：CE 池扩到 2620 并重建 baseline 后，`change_alert_count=0`
「可能是 baseline 重建掩盖了真实变化」，而不是「今天确实没变化」。

本测试用合成多日 fixture 直接驱动 `semantic_alert.build`（以逐日快照为 baseline），
断言：
- 每个真实的「昨天→今天」变化恰好产 1 条 change 告警；
- 无变化时产 0 条 change 告警（不伪造、不误报）；
- 跨多日的真实变化不会被 baseline 重建掩盖（Day3 相对 Day1 baseline 应检出 2 条）；
- standing 不因 change 而增长（首页能区分「今天发生变化」vs「今天继续重要」）。

不读取任何生产文件，纯单元级驱动 build()，不影响聚类硬约束。
"""
from __future__ import annotations

import unittest

from semantic_alert import build, current_snapshot, validate

EID = "evt_A"
CEID = "cev_A"


def _events(evidence: int, trust: int = 70, props: int = 0) -> list[dict]:
    return [{
        "event_id": EID,
        "title": "CE-A",
        "topic": "acquisition",
        "trust": {"level": "medium", "score": trust},
        "evidence": [{"x": i} for i in range(evidence)],
        "claims": {"proposition_count": props},
        "review_required": False,
    }]


def _lifecycle(stage: str, status=None) -> list[dict]:
    return [{
        "canonical_event_id": CEID,
        "stage": stage,
        "status": status,
        "identity_key": EID,
        "title": "CE-A",
    }]


def _brief(priority: int = 50, watch: bool = False) -> list[dict]:
    return [{"event_id": EID, "daily_priority": priority, "watchlist_matches": watch}]


def _ceid_map() -> dict:
    return {EID: CEID}


def _snapshot(stage: str, evidence: int, status=None, trust: int = 70) -> dict:
    """构造某一天的 current 快照，作为次日的 baseline。"""
    return current_snapshot(
        _events(evidence, trust), _lifecycle(stage, status), [], _brief(), _ceid_map()
    )


def _run_day(stage: str, evidence: int, baseline, status=None, trust: int = 70) -> dict:
    doc = build(
        _events(evidence, trust), _lifecycle(stage, status), [], _brief(),
        baseline=baseline, ceid_map=_ceid_map(),
    )
    validate(doc)  # 硬约束：无 diff 不得产 change 类
    return doc


class TestCrossDayReplay(unittest.TestCase):
    def test_day1_seed_no_change_alert(self):
        doc = _run_day("rumor", 1, baseline=None)
        self.assertEqual(doc["meta"]["basis"], "seed_first_run")
        self.assertEqual(doc["meta"]["internal_diff_count"], 0)
        self.assertEqual(doc["meta"]["change_alert_count"], 0)
        self.assertEqual(doc["meta"]["alert_count"], 0)

    def test_day2_stage_change_emits_one_change(self):
        snap1 = _snapshot("rumor", 1)
        doc = _run_day("negotiation", 1, baseline=snap1)
        self.assertEqual(doc["meta"]["internal_diff_count"], 1)
        self.assertEqual(doc["meta"]["change_alert_count"], 1)
        a = doc["semantic_alerts"][0]
        self.assertEqual(a["type"], "EVENT_STAGE_CHANGED")
        self.assertEqual(a["basis"], "delta")
        self.assertEqual(a["canonical_event_id"], CEID)

    def test_day3_evidence_increase_emits_one_change(self):
        snap2 = _snapshot("negotiation", 1)
        doc = _run_day("negotiation", 3, baseline=snap2)  # 证据 +2，阶段不变
        self.assertEqual(doc["meta"]["internal_diff_count"], 1)
        self.assertEqual(doc["meta"]["change_alert_count"], 1)
        a = doc["semantic_alerts"][0]
        self.assertEqual(a["type"], "EVENT_MATERIAL_CHANGED")
        self.assertEqual(a["basis"], "delta")

    def test_day4_stage_agreement_emits_one_change(self):
        snap3 = _snapshot("negotiation", 3)
        doc = _run_day("agreement", 3, baseline=snap3)
        self.assertEqual(doc["meta"]["internal_diff_count"], 1)
        self.assertEqual(doc["meta"]["change_alert_count"], 1)
        a = doc["semantic_alerts"][0]
        self.assertEqual(a["type"], "EVENT_STAGE_CHANGED")
        self.assertEqual(a["basis"], "delta")

    def test_each_transition_independent_count(self):
        """逐日各 1 条，且 standing 不随 change 增长（首页可区分两类语义）。"""
        snap1 = _snapshot("rumor", 1)
        d2 = _run_day("negotiation", 1, baseline=snap1)
        snap2 = _snapshot("negotiation", 1)
        d3 = _run_day("negotiation", 3, baseline=snap2)
        snap3 = _snapshot("negotiation", 3)
        d4 = _run_day("agreement", 3, baseline=snap3)
        for d in (d2, d3, d4):
            self.assertEqual(d["meta"]["change_alert_count"], 1)
            self.assertEqual(d["meta"]["standing_alert_count"], 0)
            self.assertEqual(d["meta"]["alert_count"], 1)

    def test_no_masking_multi_day_baseline(self):
        """Day3 相对 Day1 baseline（跳过 Day2）应检出 2 条真实变化，证明不被掩盖。"""
        snap1 = _snapshot("rumor", 1)
        doc = _run_day("agreement", 3, baseline=snap1)  # 阶段 + 证据都变了
        # internal_diff_count 计「有变化的 CE 数」（1 个 CE 跨 2 字段 = 1 个 diff）；
        # 但该 diff 确实产出 2 条 change 告警，证明两处真实变化均未被掩盖。
        self.assertEqual(doc["meta"]["internal_diff_count"], 1)
        self.assertEqual(doc["meta"]["change_alert_count"], 2)
        types = {a["type"] for a in doc["semantic_alerts"]}
        self.assertIn("EVENT_STAGE_CHANGED", types)
        self.assertIn("EVENT_MATERIAL_CHANGED", types)

    def test_rebuild_baseline_to_current_no_false_change(self):
        """把 baseline 重建为「与今日相同」不应产生假 change 告警（正确，非掩盖）。"""
        snap2 = _snapshot("negotiation", 1)
        doc = _run_day("negotiation", 1, baseline=snap2)  # 与 baseline 完全一致
        self.assertEqual(doc["meta"]["internal_diff_count"], 0)
        self.assertEqual(doc["meta"]["change_alert_count"], 0)
        self.assertEqual(doc["meta"]["alert_count"], 0)


if __name__ == "__main__":
    unittest.main()
