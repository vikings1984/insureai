#!/usr/bin/env python3
"""P1-3 KG-2 预置查询正确性用例（kg_query.py）。

查询语义与 knowledge-graph.html 前端逻辑对齐：90 天窗口锚定图谱自身
latest_event_at，保证查询可复现。
"""
import unittest
from datetime import datetime, timedelta, timezone

from kg_query import entity_recent, neighbors_of, topic_crossover

NOW = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
ISO = "%Y-%m-%dT%H:%M:%SZ"


def ts(days_ago: int) -> str:
    return (NOW - timedelta(days=days_ago)).strftime(ISO)


def graph() -> dict:
    """合成图：Acme 布局 AI + 产品创新（一个 200 天前，两个窗口内）；Beta 只做产品创新。"""
    return {
        "stats": {"latest_event_at": ts(10), "node_count": 8, "edge_count": 8},
        "nodes": [
            {"id": "n_acme", "type": "Company", "name": "Acme Insurance"},
            {"id": "n_beta", "type": "Company", "name": "Beta Re"},
            {"id": "n_ev_ai", "type": "Event", "name": "ev_ai", "title": "Acme 发布 AI 理赔系统", "topic": "ai_intelligent", "published_at": ts(10), "trust": {"level": "high"}, "evidence_status": "cross_checked", "source_count": 3},
            {"id": "n_ev_ai2", "type": "Event", "name": "ev_ai2", "title": "Acme 扩大 AI 投入", "topic": "ai_intelligent", "published_at": ts(60), "trust": {"level": "medium"}, "evidence_status": "single_source", "source_count": 1},
            {"id": "n_ev_old", "type": "Event", "name": "ev_old", "title": "Acme 推出健康险产品", "topic": "product_innovation", "published_at": ts(200), "trust": {"level": "high"}, "evidence_status": "cross_checked", "source_count": 2},
            {"id": "n_ev_beta", "type": "Event", "name": "ev_beta", "title": "Beta 推出智能核保产品", "topic": "product_innovation", "published_at": ts(30), "trust": {"level": "high"}, "evidence_status": "cross_checked", "source_count": 2},
            {"id": "n_c1", "type": "Claim", "name": "ev_ai/c1", "claim_text": "Acme 投入 1 亿美元", "claim_type": "capital_raise", "verification_status": "cross_checked", "confidence": 80},
            {"id": "n_c2", "type": "Claim", "name": "ev_old/c2", "claim_text": "健康险产品线扩展", "claim_type": "product_launch", "verification_status": "single_source", "confidence": 60},
        ],
        "edges": [
            {"source": "n_acme", "relationship": "PARTICIPATES_IN", "target": "n_ev_ai", "confidence": 0.75},
            {"source": "n_acme", "relationship": "PARTICIPATES_IN", "target": "n_ev_ai2", "confidence": 0.75},
            {"source": "n_acme", "relationship": "PARTICIPATES_IN", "target": "n_ev_old", "confidence": 0.75},
            {"source": "n_beta", "relationship": "PARTICIPATES_IN", "target": "n_ev_beta", "confidence": 0.75},
            {"source": "n_ev_ai", "relationship": "ABOUT", "target": "n_t_ai", "confidence": 0.9},
            {"source": "n_acme", "relationship": "MENTIONS", "target": "n_c1", "confidence": 0.8},
            {"source": "n_acme", "relationship": "MENTIONS", "target": "n_c2", "confidence": 0.8},
            {"source": "n_c1", "relationship": "INVOLVES", "target": "n_ev_ai", "confidence": 0.9},
            {"source": "n_c2", "relationship": "INVOLVES", "target": "n_ev_old", "confidence": 0.9},
        ],
    }


class EntityRecentTests(unittest.TestCase):
    def test_window_keeps_recent_drops_old(self):
        out = entity_recent(graph(), "Acme Insurance")
        event_ids = [x["event_id"] for x in out["events"]]
        self.assertEqual(sorted(event_ids), ["ev_ai", "ev_ai2"])
        self.assertNotIn("ev_old", event_ids)
        # 窗口锚定 latest_event_at=ts(10)=2026-08-17，起点 = 2026-08-17 - 90d。
        self.assertEqual(out["window"][0][:10], "2026-05-19")
        self.assertEqual(out["window"][1][:10], "2026-08-17")

    def test_claim_time_via_event(self):
        out = entity_recent(graph(), "Acme Insurance")
        # c1 属于窗口内事件 ev_ai -> 保留；c2 属于窗口外事件 ev_old -> 过滤。
        self.assertEqual([c["claim_id"] for c in out["claims"]], ["ev_ai/c1"])
        self.assertEqual(out["claims"][0]["published_at"], ts(10))

    def test_case_insensitive_partial_match(self):
        out = entity_recent(graph(), "acme insurance")
        self.assertEqual(out["matched_types"], ["Company"])
        self.assertEqual(out["total"], 3)

    def test_unknown_entity_empty(self):
        out = entity_recent(graph(), "Nobody")
        self.assertEqual(out["total"], 0)
        self.assertEqual(out["events"], [])

    def test_custom_days_widens_window(self):
        out = entity_recent(graph(), "Acme Insurance", days=365)
        self.assertIn("ev_old", [x["event_id"] for x in out["events"]])
        # 365 天窗口：3 个事件 + 2 条 Claim（窗口外的 ev_old/c2 一并回归）。
        self.assertEqual(out["total"], 5)


class TopicCrossoverTests(unittest.TestCase):
    def test_crossover_returns_entities_on_all_topics(self):
        out = topic_crossover(graph(), ["ai_intelligent", "product_innovation"])
        names = [x["entity"] for x in out["entities"]]
        self.assertIn("Acme Insurance", names)
        self.assertNotIn("Beta Re", names)

    def test_crossover_counts_shared_events(self):
        out = topic_crossover(graph(), ["ai_intelligent", "product_innovation"])
        acme = next(x for x in out["entities"] if x["entity"] == "Acme Insurance")
        self.assertEqual(acme["event_count"], 3)
        self.assertEqual(set(acme["topics"]), {"ai_intelligent", "product_innovation"})

    def test_crossover_single_topic_rejected(self):
        out = topic_crossover(graph(), ["ai_intelligent"])
        self.assertEqual(out["entities"], [])
        self.assertIn("至少", out["note"])

    def test_crossover_unmatched_topic_empty(self):
        out = topic_crossover(graph(), ["ai_intelligent", "regulatory_change"])
        self.assertEqual(out["total"], 0)


class NeighborsTests(unittest.TestCase):
    def test_one_hop_with_direction(self):
        out = neighbors_of(graph(), "n_acme")
        rows = {x["node_id"]: x for x in out["neighbors"]}
        self.assertIn("n_ev_ai", rows)
        self.assertEqual(rows["n_ev_ai"]["direction"], "out")
        self.assertEqual(rows["n_ev_ai"]["relationship"], "PARTICIPATES_IN")
        self.assertEqual(rows["n_ev_ai"]["type"], "Event")

    def test_reverse_direction(self):
        out = neighbors_of(graph(), "n_ev_ai")
        rows = {x["node_id"]: x for x in out["neighbors"]}
        self.assertEqual(rows["n_acme"]["direction"], "in")
        self.assertEqual(rows["n_c1"]["direction"], "in")
        self.assertEqual(rows["n_c1"]["relationship"], "INVOLVES")

    def test_missing_node(self):
        out = neighbors_of(graph(), "kg-nonexistent")
        self.assertEqual(out["neighbors"], [])
        self.assertIn("not found", out["note"])


if __name__ == "__main__":
    unittest.main()
