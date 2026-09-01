import json
import tempfile
import unittest
from pathlib import Path

import second_brain as SB


def _pm(watchlists, memory_entries=None, gaps=None, affinity=None):
    return {
        "version": "p2.5-v1.0",
        "watchlists": {"enabled_count": len(watchlists), "items": watchlists},
        "memory_entries": memory_entries or [],
        "entity_affinity": affinity or {},
        "gaps": gaps or [],
    }


def _wl(wid, hit_count=0, hit_topics=None):
    return {
        "id": wid, "name": wid, "topics": [], "keywords": [], "priority_boost": 7,
        "updated_at": None, "hit_count": hit_count, "hit_topics": hit_topics or {}, "hit_terms": [],
    }


def _brief_item(event_id, topic, matches):
    return {"event_id": event_id, "title": topic, "topic": topic, "entities": [], "watchlist_matches": matches}


class SecondBrainTests(unittest.TestCase):
    def test_role_config_is_three_and_exact(self):
        pm = _pm([_wl("ma", 3), _wl("regulatory", 2), _wl("health", 1), _wl("ai", 5)])
        roles = SB.role_views(pm, [])
        self.assertEqual(set(roles), set(SB.ROLE_CONFIG))
        for rid, r in roles.items():
            self.assertEqual([w["id"] for w in r["watchlists"]], SB.ROLE_CONFIG[rid]["watchlist_ids"])

    def test_role_view_filters_by_topic_and_watchlist(self):
        pm = _pm([_wl("ma", 3), _wl("regulatory", 2), _wl("health", 1), _wl("ai", 5)])
        # strategy 关心 capital_reinsurance / regulatory_change + 关注 ma/regulatory
        brief = [
            _brief_item("e1", "capital_reinsurance", ["ma"]),       # topic 命中
            _brief_item("e2", "product_innovation", []),            # 都不命中 → 排除
            _brief_item("e3", "regulatory_change", ["regulatory"]),  # topic 命中
            _brief_item("e4", "pension_finance", []),               # strategy 含 pension_finance → 命中
        ]
        roles = SB.role_views(pm, brief)
        strat = roles["strategy"]
        # strategy 应含 e1/e3/e4，不含 e2
        matched = [b for b in brief if (b["topic"] in set(strat["topics"]))
                   or (set(b["watchlist_matches"]) & set(strat["watchlist_ids"]))]
        self.assertEqual({m["event_id"] for m in matched}, {"e1", "e3", "e4"})
        self.assertNotIn("e2", {m["event_id"] for m in matched})

    def test_role_view_rejects_unknown_watchlist(self):
        # 配置声明了 ma，但记忆层没这个清单 → fail-closed 抛错
        pm = _pm([_wl("regulatory", 2), _wl("health", 1), _wl("ai", 5)])
        with self.assertRaises(ValueError):
            SB.role_views(pm, [])

    def test_entity_threads_sorted_by_time_and_bounded(self):
        graph = {
            "nodes": [
                {"id": "n1", "type": "Company", "name": "Foo"},
                {"id": "e1", "type": "Event", "name": "ev1", "title": "a", "topic": "x", "published_at": "2026-01-01"},
                {"id": "e2", "type": "Event", "name": "ev2", "title": "b", "topic": "x", "published_at": "2026-03-01"},
                {"id": "e3", "type": "Event", "name": "ev3", "title": "c", "topic": "x", "published_at": "2025-12-01"},
                {"id": "e4", "type": "Event", "name": "ev4", "title": "d", "topic": "x", "published_at": "2026-02-01"},
            ],
            "edges": [
                {"source": "n1", "target": "e1", "relationship": "PARTICIPATES_IN"},
                {"source": "n1", "target": "e2", "relationship": "PARTICIPATES_IN"},
                {"source": "n1", "target": "e3", "relationship": "PARTICIPATES_IN"},
                {"source": "n1", "target": "e4", "relationship": "LINKS_TO"},  # 非 PARTICIPATES_IN → 排除
            ],
        }
        threads = SB.build_entity_threads(graph, ["Foo"])
        self.assertEqual(len(threads), 1)
        t = threads[0]
        self.assertEqual(t["entity"], "Foo")
        self.assertEqual(t["event_count"], 3)
        self.assertEqual([e["event_id"] for e in t["events"]], ["ev3", "ev1", "ev2"])
        self.assertEqual(t["first_seen"], "2025-12-01")
        self.assertEqual(t["last_seen"], "2026-03-01")

    def test_entity_threads_capped_per_thread(self):
        events = [{"id": f"e{i}", "type": "Event", "name": f"ev{i}", "title": f"t{i}",
                   "topic": "x", "published_at": f"2026-01-{i:02d}"} for i in range(1, 13)]
        nodes = [{"id": "n1", "type": "Company", "name": "Foo"}] + events
        edges = [{"source": "n1", "target": ev["id"], "relationship": "PARTICIPATES_IN"} for ev in events]
        graph = {"nodes": nodes, "edges": edges}
        threads = SB.build_entity_threads(graph, ["Foo"])
        self.assertLessEqual(len(threads[0]["events"]), SB.MAX_EVENTS_PER_THREAD)
        self.assertLessEqual(threads[0]["event_count"], SB.MAX_EVENTS_PER_THREAD)

    def test_open_questions_records_no_signal_and_no_decisions(self):
        # ma 命中 0 → no_signal；operations/risk 角色无决策 → no_decisions
        pm = _pm([_wl("ma", 0), _wl("regulatory", 2), _wl("health", 1), _wl("ai", 5)],
                 memory_entries=[{"event_id": "d1", "topic": "capital_reinsurance"}])
        roles = SB.role_views(pm, [_brief_item("d1", "capital_reinsurance", ["ma"])])
        oq = SB.open_questions(pm, roles)
        dims = [o["dimension"] for o in oq]
        self.assertIn("关注清单 ma 无信号", dims)
        self.assertIn("角色 operations 决策覆盖", dims)
        self.assertIn("角色 risk 决策覆盖", dims)

    def test_validate_fail_closed(self):
        doc = SB.build({}, {"items": []}, {"brief": []}, _pm([_wl("ma"), _wl("regulatory"), _wl("health"), _wl("ai")]))
        SB.validate(doc)  # 不应抛
        # 缺 open_questions
        bad = json.loads(json.dumps(doc))
        del bad["open_questions"]
        with self.assertRaises(AssertionError):
            SB.validate(bad)
        # open_questions 为空
        bad2 = json.loads(json.dumps(doc))
        bad2["open_questions"] = []
        with self.assertRaises(AssertionError):
            SB.validate(bad2)
        # roles 多一档
        bad3 = json.loads(json.dumps(doc))
        bad3["roles"]["ghost"] = bad3["roles"]["strategy"]
        with self.assertRaises(AssertionError):
            SB.validate(bad3)

    def test_build_is_deterministic(self):
        pm = _pm([_wl("ma", 3), _wl("regulatory", 2), _wl("health", 1), _wl("ai", 5)])
        a = SB.build({}, {"items": []}, {"brief": []}, pm)
        b = SB.build({}, {"items": []}, {"brief": []}, pm)
        a.pop("generated_at"); b.pop("generated_at")
        self.assertEqual(a, b)


class SecondBrainProductionTests(unittest.TestCase):
    """端到端守护：必须能吃真实提交的 artifact 跑通（合成 fixture 从没暴露过生产形状）。"""

    def test_build_on_production_artifacts(self):
        root = Path(__file__).resolve().parents[1]
        needed = ["p2_state.json", "review_queue.json", "p2_daily_brief.json",
                  "p2_personal_memory.json", "knowledge_graph.json"]
        if not all((root / f).exists() for f in needed):
            self.skipTest("生产 artifact 不全")
        doc = SB.run(persist=False)
        self.assertEqual(set(doc["roles"]), set(SB.ROLE_CONFIG))
        self.assertGreater(len(doc["entity_threads"]), 0)
        self.assertGreater(len(doc["open_questions"]), 0)
        SB.validate(doc)


if __name__ == "__main__":
    unittest.main()
