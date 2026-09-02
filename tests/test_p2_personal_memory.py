#!/usr/bin/env python3
"""P2.5 Personal Memory 的纪律测试。

重点不是「能不能跑出数字」，而是三条硬纪律有没有被守住：
1. 样本不足时**只出观察、不出结论**，且必须给出阻塞原因；
2. **不伪造时间线**（决策无时间戳时，不得声称任何先后顺序）；
3. 推不出的维度必须写进 gaps，不静默省略。

断言一律用具体值（如 == 0 / == 2 / == "watch"），避免 ">= 0" 这类恒真断言。
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from p2_personal_memory import (
    MIN_SAMPLE_FOR_CONCLUSION,
    VERSION,
    backlog_profile,
    build,
    build_event_index,
    decision_profile,
    entity_affinity,
    memory_gaps,
    validate,
    watchlist_profile,
)


def _item(event_id: str, **kw) -> dict:
    base = {
        "event_id": event_id,
        "title": f"事件 {event_id}",
        "topic": "ai_intelligent",
        "event_type": "regulatory",
        "priority": 50,
        "trust_level": "medium",
        "decision": None,
    }
    base.update(kw)
    return base


def _acted(n: int, urgency: str = "watch", action: str = "复核资本配置与竞争格局") -> list[dict]:
    return [_item(f"evt_{i:04d}", decision={"urgency": urgency, "action": action}) for i in range(n)]


def _rec(event_id: str, urgency: str = "watch", action: str = "复核资本配置与竞争格局",
         decided_at: str | None = None) -> dict:
    """归一化决策记录（顶层 urgency/action/decided_at），匹配 decision_profile 新契约。"""
    r = {"event_id": event_id, "topic": "ai_intelligent", "event_type": "regulatory",
         "urgency": urgency, "action": action}
    if decided_at is not None:
        r["decided_at"] = decided_at
    return r


def _acted_records(n: int, urgency: str = "watch", action: str = "复核资本配置与竞争格局",
                  decided_at: str | None = None) -> list[dict]:
    """decision_profile 单测用：已归一化的决策记录列表。"""
    return [_rec(f"evt_{i:04d}", urgency, action, decided_at) for i in range(n)]


# 隔离：build() 默认会读 ROOT/decisions_ledger.json，单测用不存在的路径强制回退到复核队列样本
_NO_LEDGER = Path("/dev/null/insureai_no_ledger.json")


def _graph(events: dict[str, list[str]], extra_edges: list[tuple[str, str, str]] | None = None) -> dict:
    """events: event_id -> [company names]（全部以 PARTICIPATES_IN 相连）。"""
    nodes = [{"id": "kg-topic", "type": "Topic", "name": "ai_intelligent", "topic": "ai_intelligent"}]
    edges: list[dict] = []
    for i, (event_id, companies) in enumerate(events.items()):
        eid = f"kg-evt-{i}"
        nodes.append(
            {
                "id": eid,
                "type": "Event",
                "name": event_id,
                "topic": "ai_intelligent",
                "published_at": "2026-08-01T00:00:00Z",
            }
        )
        for j, comp in enumerate(companies):
            cid = f"kg-co-{i}-{j}"
            nodes.append({"id": cid, "type": "Company", "name": comp})
            edges.append({"source": cid, "target": eid, "relationship": "PARTICIPATES_IN", "confidence": 0.8})
    for src, tgt, rel in extra_edges or []:
        edges.append({"source": src, "target": tgt, "relationship": rel, "confidence": 0.5})
    return {"nodes": nodes, "edges": edges}


class TestDecisionProfile(unittest.TestCase):
    def test_below_threshold_observes_but_concludes_nothing(self):
        r = decision_profile(_acted_records(11))
        self.assertEqual(r["observations"]["sample_size"], 11)
        # 核心纪律：11 条远低于阈值，结论必须为空
        self.assertEqual(r["conclusions"], [])
        self.assertIsNotNone(r["conclusion_blocked"])
        self.assertIn(f"低于 {MIN_SAMPLE_FOR_CONCLUSION}", r["conclusion_blocked"]["reason"])
        # 观察值仍须如实给出
        self.assertEqual(r["observations"]["by_urgency"], {"watch": 11})
        self.assertEqual(r["observations"]["by_action"], {"复核资本配置与竞争格局": 11})

    def test_zero_decisions_blocked_with_reason(self):
        r = decision_profile([])
        self.assertEqual(r["observations"]["sample_size"], 0)
        self.assertEqual(r["conclusions"], [])
        self.assertIn("尚无任何已落决策", r["conclusion_blocked"]["reason"])

    def test_at_threshold_conclusion_emitted(self):
        r = decision_profile(_acted_records(MIN_SAMPLE_FOR_CONCLUSION))
        self.assertEqual(len(r["conclusions"]), 1)
        self.assertEqual(r["conclusions"][0]["type"], "urgency_preference")
        self.assertIn("watch", r["conclusions"][0]["statement"])
        self.assertIsNone(r["conclusion_blocked"])

    def test_urgency_without_variance_is_called_out(self):
        """单一 urgency 取值时，阻塞原因必须点明「无区分度」。"""
        r = decision_profile(_acted_records(5))
        self.assertIn("无区分度", r["conclusion_blocked"]["reason"])
        self.assertIn("urgency 取值单一", r["conclusion_blocked"]["reason"])
        # E2 后解锁路径改为「累计至 ≥30 条真实决策（来自决策账本，不伪造）」
        self.assertIn("决策账本", r["conclusion_blocked"]["need"])


class TestEventIndex(unittest.TestCase):
    def test_joins_by_event_id_and_only_entity_relations(self):
        g = _graph(
            {"evt_a": ["AM Best", "Hiscox"]},
            # ABOUT 指向 Topic、INVOLVES 指向 Claim —— 都不该被当成关注主体
            extra_edges=[("kg-evt-0", "kg-topic", "ABOUT")],
        )
        idx = build_event_index(g)
        self.assertEqual(idx["evt_a"]["entities"], ["AM Best", "Hiscox"])
        self.assertEqual(idx["evt_a"]["published_at"], "2026-08-01T00:00:00Z")

    def test_multihop_entity_not_counted(self):
        """只取一跳：经由中间 Company 再连到的 Company 不算用户关注过。"""
        nodes = [
            {"id": "e1", "type": "Event", "name": "evt_x", "topic": "t", "published_at": "2026-08-01T00:00:00Z"},
            {"id": "c1", "type": "Company", "name": "直达公司"},
            {"id": "c2", "type": "Company", "name": "二跳公司"},
        ]
        edges = [
            {"source": "c1", "target": "e1", "relationship": "PARTICIPATES_IN", "confidence": 0.9},
            {"source": "c2", "target": "c1", "relationship": "RELATED_TO", "confidence": 0.9},
        ]
        idx = build_event_index({"nodes": nodes, "edges": edges})
        self.assertEqual(idx["evt_x"]["entities"], ["直达公司"])


class TestEntityAffinity(unittest.TestCase):
    def test_counts_and_overlap_are_exact(self):
        idx = build_event_index(_graph({"evt_1": ["AM Best"], "evt_2": ["AM Best", "Hiscox"], "evt_3": ["KCC"]}))
        r = entity_affinity(idx, ["evt_1", "evt_2"], ["evt_2", "evt_3"])
        self.assertEqual(r["acted_entities"], [{"key": "AM Best", "count": 2}, {"key": "Hiscox", "count": 1}])
        # overlap = 既在关注清单命中里、又有已决决策 → 只有 evt_2 的实体
        self.assertEqual(r["overlap_entities"], [{"key": "AM Best", "count": 1}, {"key": "Hiscox", "count": 1}])
        self.assertEqual(r["acted_event_count"], 2)
        self.assertEqual(r["watched_event_count"], 2)

    def test_quality_caveat_is_declared(self):
        r = entity_affinity({}, [], [])
        self.assertEqual(r["quality"]["cleaning"], "none")
        self.assertIn("噪声", r["quality"]["caveat"])


class TestWatchlistProfile(unittest.TestCase):
    def test_hits_counted_from_watchlist_matches(self):
        wls = [{"id": "ai", "name": "AI保险", "topics": ["ai_intelligent"], "keywords": ["AI"], "priority_boost": 8}]
        brief = [
            {"event_id": "evt_1", "topic": "ai_intelligent", "entities": ["ai", "大模型"], "watchlist_matches": ["ai"]},
            {"event_id": "evt_2", "topic": "regulatory_change", "entities": ["监管"], "watchlist_matches": ["ai"]},
            {"event_id": "evt_3", "topic": "ai_intelligent", "entities": [], "watchlist_matches": []},
        ]
        r = watchlist_profile(wls, brief)
        self.assertEqual(r["enabled_count"], 1)
        self.assertEqual(r["total_hits"], 2)
        self.assertEqual(r["distinct_hit_events"], 2)
        self.assertEqual(r["top_topics"], [{"key": "ai_intelligent", "count": 1}, {"key": "regulatory_change", "count": 1}])
        # 未命中的 evt_3 不得进入 hit_event_ids
        self.assertEqual(r["hit_event_ids"], ["evt_1", "evt_2"])

    def test_disabled_watchlist_ignored(self):
        wls = [{"id": "off", "name": "停用", "enabled": False}]
        r = watchlist_profile(wls, [{"event_id": "e", "watchlist_matches": ["off"]}])
        self.assertEqual(r["enabled_count"], 0)
        self.assertEqual(r["items"], [])


class TestBacklog(unittest.TestCase):
    def test_pending_only_and_ordered_by_priority(self):
        pending = [
            _item("evt_low", priority=10, topic="ai_intelligent"),
            _item("evt_high", priority=90, topic="regulatory_change"),
            _item("evt_mid", priority=50, topic="ai_intelligent"),
        ]
        r = backlog_profile(pending)
        self.assertEqual(r["sample_size"], 3)
        self.assertEqual(r["by_topic"], {"ai_intelligent": 2, "regulatory_change": 1})
        self.assertEqual([x["event_id"] for x in r["top_by_priority"]][:3], ["evt_high", "evt_mid", "evt_low"])


class TestGaps(unittest.TestCase):
    def test_empty_feedback_and_monitoring_reported(self):
        gaps = memory_gaps([], [], 3, has_decided_at=False)
        dims = [g["dimension"] for g in gaps]
        self.assertIn("反馈偏好（useful/noise/incorrect…）", dims)
        self.assertIn("持续跟踪偏好（snoozed/resolved）", dims)
        by_status = {g["dimension"]: g["status"] for g in gaps}
        self.assertEqual(by_status["反馈偏好（useful/noise/incorrect…）"], "empty")

    def test_timeline_gap_present_when_no_decided_at(self):
        """缺少 decided_at 时，记忆时间线结构性不可得（不伪造顺序）。"""
        gaps = memory_gaps([{"label": "useful"}], [{"event_id": "e"}],
                            MIN_SAMPLE_FOR_CONCLUSION, has_decided_at=False)
        dims = [g["dimension"] for g in gaps]
        self.assertIn("记忆时间线（按决策先后排序）", dims)
        timeline = next(g for g in gaps if g["dimension"].startswith("记忆时间线"))
        self.assertEqual(timeline["status"], "structurally_unavailable")
        self.assertIn("decided_at", timeline["unblock"])

    def test_timeline_gap_unlocked_when_decided_at_present(self):
        """E2：决策普遍带真实 decided_at 后，记忆时间线解锁，不再列为结构性缺口。"""
        gaps = memory_gaps([{"label": "useful"}], [{"event_id": "e"}],
                            MIN_SAMPLE_FOR_CONCLUSION, has_decided_at=True)
        dims = [g["dimension"] for g in gaps]
        self.assertNotIn("记忆时间线（按决策先后排序）", dims)

    def test_upstream_entity_noise_declared(self):
        gaps = memory_gaps([], [], 3, has_decided_at=False)
        dims = [g["dimension"] for g in gaps]
        self.assertIn("关注主体准确性", dims)


class TestBuildAndValidate(unittest.TestCase):
    def _doc(self, n_acted: int = 3, with_graph: bool = True):
        state = {"watchlists": [{"id": "ai", "name": "AI保险", "topics": ["ai_intelligent"], "keywords": ["AI"]}],
                 "feedback": [], "monitoring": []}
        acted = _acted(n_acted)
        queue = {"items": acted + [_item("evt_pending")]}
        brief = {"brief": [{"event_id": "evt_0000", "topic": "ai_intelligent",
                            "entities": ["ai"], "watchlist_matches": ["ai"]}]}
        graph = _graph({"evt_0000": ["AM Best"]}) if with_graph else None
        return build(state, queue, brief, graph, ledger_path=_NO_LEDGER)

    def test_full_doc_passes_validation(self):
        doc = self._doc()
        validate(doc)  # 不抛即通过
        self.assertEqual(doc["version"], VERSION)
        self.assertEqual(doc["sources"]["review_queue.json"], {"items": 4, "decided": 3, "pending": 1})

    def test_memory_entries_carry_decision_and_honest_decided_at(self):
        doc = self._doc(n_acted=4)
        self.assertEqual(len(doc["memory_entries"]), 4)
        for e in doc["memory_entries"]:
            self.assertIsNotNone(e["decision"])
            # E2：decided_at 是引擎真实产出时间；fixture 决策未带该字段 → 必须为 None，不得伪造
            self.assertIsNone(e.get("decided_at"))

        # fixture 里只有 evt_0000 进了图谱：它应有事件发布时间，
        # 其余三条不在图谱中 → 时间必须是 None（缺数据就留空，不得编造或用当前时间占位）
        by_id = {e["event_id"]: e for e in doc["memory_entries"]}
        self.assertEqual(by_id["evt_0000"]["event_published_at"], "2026-08-01T00:00:00Z")
        self.assertEqual(by_id["evt_0000"]["entities"], ["AM Best"])
        for missing in ("evt_0001", "evt_0002", "evt_0003"):
            self.assertIsNone(by_id[missing]["event_published_at"])
            self.assertEqual(by_id[missing]["entities"], [])

    def test_memory_entries_carry_decided_at_when_present(self):
        """E2：决策携带真实 decided_at 时，记忆条目须如实透传（不改写、不丢弃）。"""
        acted = [_item(f"evt_{i:04d}",
                       decision={"urgency": "watch", "action": "复核", "decided_at": "2026-08-20T00:00:00Z"})
                 for i in range(3)]
        state = {"watchlists": [{"id": "ai", "topics": ["ai_intelligent"], "keywords": ["AI"]}],
                 "feedback": [], "monitoring": []}
        queue = {"items": acted + [_item("evt_pending")]}
        brief = {"brief": [{"event_id": "evt_0000", "topic": "ai_intelligent",
                            "entities": ["ai"], "watchlist_matches": ["ai"]}]}
        doc = build(state, queue, brief, None, ledger_path=_NO_LEDGER)
        for e in doc["memory_entries"]:
            self.assertEqual(e["decided_at"], "2026-08-20T00:00:00Z")

    def test_without_graph_entity_affinity_degrades_cleanly(self):
        doc = self._doc(with_graph=False)
        validate(doc)
        self.assertEqual(doc["sources"]["knowledge_graph.json"], None)
        self.assertEqual(doc["entity_affinity"]["acted_entities"], [])
        self.assertEqual(doc["memory_entries"][0]["entities"], [])

    def test_validate_rejects_conclusions_below_threshold(self):
        """fail-closed：样本不足却写了结论，必须报错而不是静默放过。"""
        doc = self._doc(n_acted=3)
        doc["decisions"]["conclusions"] = [{"type": "urgency_preference", "statement": "编造的偏好"}]
        with self.assertRaises(AssertionError):
            validate(doc)

    def test_validate_rejects_missing_block_reason(self):
        doc = self._doc(n_acted=3)
        doc["decisions"]["conclusion_blocked"] = None
        with self.assertRaises(AssertionError):
            validate(doc)

    def test_validate_rejects_entry_count_mismatch(self):
        doc = self._doc(n_acted=3)
        doc["memory_entries"].append({"event_id": "evt_ghost", "decision": {"urgency": "watch"}})
        with self.assertRaises(AssertionError):
            validate(doc)

    def test_validate_rejects_empty_gaps(self):
        doc = self._doc()
        doc["gaps"] = []
        with self.assertRaises(AssertionError):
            validate(doc)

    def test_output_is_json_serializable_and_stable(self):
        doc = self._doc()
        text = json.dumps(doc, ensure_ascii=False, sort_keys=True)
        self.assertEqual(json.loads(text)["version"], VERSION)


if __name__ == "__main__":
    unittest.main()
