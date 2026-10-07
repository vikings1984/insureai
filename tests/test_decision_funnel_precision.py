#!/usr/bin/python3
"""P0-B Decision Funnel precision 基准（Event OS 第四阶段「生产验证」）。

reviewer 的核心担忧：decision_ready 有了「门」但还没验证「精度」——
「这 4 个真的值得人做决定吗？」本测试用合成 review_queue 直接驱动
`decision_funnel.build`，断言：

- 只有真正达到六条件的事件进入 decision_ready（precision=1.0，无假阳性）；
- 未监控 / 单源监管·评级 / 低信任 / 已决 四类典型负例均被拒；
- event_type 白名单边界正确：industry_update / claims_loss 即便其他条件全过也不准入，
  personnel / product / market_entry / capital / rating 在监控+证据齐备时准入。

不读取任何生产产物，纯单元级驱动 build()，是 CI 中 decision_ready precision 的主门。
（`benchmark.py` 的 `funnel_benchmark` 作为生产产物契约的次级校验。）
"""
from __future__ import annotations

import unittest

from decision_funnel import (
    DECISION_RELEVANT_EVENT_TYPES,
    build,
)


def _canonical(ceid: str, event_type: str, domain: str = "other",
               stage: str = "n/a", status=None, topic: str = "x") -> dict:
    return {
        "domain": domain,
        "event_type": event_type,
        "topic": topic,
        "lifecycle": {"stage": stage, "status": status},
        "title": ceid,
    }


def _review(event_id: str, topic: str = "x") -> dict:
    return {"event_id": event_id, "status": "pending", "title": event_id,
            "topic": topic, "priority": 50, "reasons": [{"type": "event_cluster"}]}


def _intel(event_id: str, trust: str = "medium", evidence: int = 1,
           source_count: int = 2) -> dict:
    return {"event_id": event_id, "evidence": [{"x": i} for i in range(evidence)],
            "trust": {"level": trust}, "source_count": source_count, "topic": "x"}


def _run(items: list[tuple], watch_topics: set[str] | None = None,
         ledger: list[dict] | None = None, changed_ceids=None) -> dict:
    """items: (event_id, ceid, event_type, domain, stage, status, topic, trust, source_count)。"""
    review_items, intel_events, canonical = [], [], {"canonical_events": {}}
    ceid_map: dict[str, str] = {}
    for event_id, ceid, et, dom, stage, status, topic, trust, src in items:
        review_items.append(_review(event_id, topic))
        intel_events.append(_intel(event_id, trust, 1, src))
        canonical["canonical_events"][ceid] = _canonical(ceid, et, dom, stage, status, topic)
        ceid_map[event_id] = ceid
    return build(
        review_items, ledger or [], intel_events, canonical,
        alert_ceids=set(), t1_alert_ceids=set(),
        watch_topics=watch_topics or set(), watch_kw=set(),
        feedback_status_by_ceid={}, ceid_map=ceid_map,
        changed_ceids=changed_ceids,
    )


def _funnel_items(doc: dict) -> dict:
    out: dict[str, dict] = {}
    for tier in ("now", "soon", "watch"):
        for it in (doc.get("funnel", {}).get(tier) or []):
            out[it["canonical_event_id"]] = it
    return out


class TestFunnelPrecision(unittest.TestCase):
    def test_only_genuine_decision_grade_admitted(self):
        items = [
            # event_id, ceid, et, dom, stage, status, topic, trust, src
            ("e_good", "cev_good", "product", "other", "n/a", None, "capital_reinsurance", "medium", 2),
            ("e_unmon", "cev_unmon", "product", "other", "n/a", None, "other_topic", "medium", 2),   # c1 未监控
            ("e_ssreg", "cev_ssreg", "rating", "regulatory", "n/a", "issued", "x", "medium", 1),      # c4 单源监管/评级
            ("e_lowt", "cev_lowt", "product", "other", "n/a", None, "capital_reinsurance", "low", 2), # c4 低信任
            ("e_dec", "cev_dec", "product", "other", "n/a", None, "capital_reinsurance", "medium", 2), # c5 已决
        ]
        ledger = [{"event_id": "e_dec", "urgency": "now", "decided_at": "2026-10-01T00:00:00Z"}]
        doc = _run(items, watch_topics={"capital_reinsurance"}, ledger=ledger)
        dr = doc["meta"]["decision_ready_ceids"]
        self.assertEqual(dr, ["cev_good"], "仅真决策级项应进入 decision_ready")
        fitems = _funnel_items(doc)
        for ceid in dr:
            it = fitems[ceid]
            self.assertTrue(it["meets_six"])
            self.assertFalse(it["six_detail"]["single_src_regulatory"])

    def test_no_false_positive_when_all_negative(self):
        items = [
            ("e1", "cev1", "product", "other", "n/a", None, "other_topic", "medium", 2),  # 未监控
            ("e2", "cev2", "rating", "regulatory", "n/a", "issued", "x", "medium", 1),      # 单源监管
        ]
        doc = _run(items, watch_topics=set())
        self.assertEqual(doc["meta"]["decision_ready"], 0)
        self.assertEqual(doc["meta"]["decision_ready_ceids"], [])

    def test_whitelist_boundary_excludes_industry_and_claims(self):
        items = [
            ("e_ind", "cev_ind", "industry_update", "other", "n/a", None, "capital_reinsurance", "medium", 2),
            ("e_clm", "cev_clm", "claims_loss", "other", "n/a", None, "capital_reinsurance", "medium", 2),
            ("e_per", "cev_per", "personnel", "other", "n/a", None, "capital_reinsurance", "medium", 2),  # 应准入
        ]
        doc = _run(items, watch_topics={"capital_reinsurance"})
        self.assertEqual(doc["meta"]["decision_ready_ceids"], ["cev_per"])

    def test_whitelist_covers_all_five_types(self):
        items = [
            ("e_cap", "cev_cap", "capital", "other", "n/a", None, "capital_reinsurance", "medium", 2),
            ("e_rat", "cev_rat", "rating", "other", "n/a", None, "capital_reinsurance", "medium", 2),
            ("e_mkt", "cev_mkt", "market_entry", "other", "n/a", None, "capital_reinsurance", "medium", 2),
            ("e_prd", "cev_prd", "product", "other", "n/a", None, "capital_reinsurance", "medium", 2),
            ("e_per", "cev_per", "personnel", "other", "n/a", None, "capital_reinsurance", "medium", 2),
        ]
        doc = _run(items, watch_topics={"capital_reinsurance"})
        self.assertEqual(set(doc["meta"]["decision_ready_ceids"]),
                         {"cev_cap", "cev_rat", "cev_mkt", "cev_prd", "cev_per"})
        # 与代码白名单一致（防止未来误改白名单导致精度漂移）
        self.assertEqual(DECISION_RELEVANT_EVENT_TYPES,
                         {"capital", "rating", "market_entry", "product", "personnel"})

    def test_precision_field_reported(self):
        items = [("e_good", "cev_good", "product", "other", "n/a", None, "capital_reinsurance", "medium", 2)]
        doc = _run(items, watch_topics={"capital_reinsurance"})
        self.assertEqual(doc["meta"]["decision_ready_precision"], 1.0)
        self.assertEqual(doc["meta"]["human_override_rate"], "n/a")


if __name__ == "__main__":
    unittest.main()
