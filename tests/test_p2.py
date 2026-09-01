import json
import tempfile
import unittest
from pathlib import Path

import p2_intelligence


def _event(event_id: str, title: str, score: int, **extra) -> dict:
    """Build an event shaped like `intelligence.build()` output."""
    event = {
        "event_id": event_id,
        "title": title,
        "entities": [],
        "topic": "ai_intelligent",
        "scores": {"intelligence_score": score},
    }
    event.update(extra)
    return event


class P2Tests(unittest.TestCase):
    def test_watchlist_and_feedback_change_priority(self):
        with tempfile.TemporaryDirectory() as d:
            old = p2_intelligence.STATE_PATH
            p2_intelligence.STATE_PATH = Path(d) / "state.json"
            try:
                state = p2_intelligence.load_state()
                p2_intelligence.upsert_watchlist(state, {
                    "id": "ai", "name": "AI", "topics": ["ai_intelligent"],
                    "keywords": ["AI"], "priority_boost": 10
                })
                p2_intelligence.record_feedback(state, "e1", "important", "acted on")
                self.assertEqual(state["watchlists"][0]["id"], "ai")
                self.assertEqual(state["feedback"][0]["label"], "important")
                self.assertEqual(p2_intelligence._feedback_boost("e1", state["feedback"]), 5)
            finally:
                p2_intelligence.STATE_PATH = old

    def test_monitoring_state(self):
        with tempfile.TemporaryDirectory() as d:
            old = p2_intelligence.STATE_PATH
            p2_intelligence.STATE_PATH = Path(d) / "state.json"
            try:
                state = p2_intelligence.load_state()
                row = p2_intelligence.register_monitor(state, "ai", "e1")
                self.assertEqual(row["status"], "active")
                row2 = p2_intelligence.register_monitor(state, "ai", "e1", "resolved")
                self.assertEqual(row2["status"], "resolved")
                self.assertEqual(len(state["monitoring"]), 1)
            finally:
                p2_intelligence.STATE_PATH = old

    def test_brief_is_sorted_by_daily_priority(self):
        news = [{
            "title": "AI insurance agent policy launch",
            "summary": "AI cyber insurance product launch",
            "source_name": "Reuters",
            "source_url": "https://example.com/a",
            "published_at": "2026-08-28T00:00:00+00:00",
            "tags": "AI Insurance",
            "research_topic": "ai_intelligent",
            "ai_score": 90,
            "source_authority": 90,
        }]
        state = {"version":"p2-v1.0", "watchlists":[], "feedback":[], "monitoring":[]}
        result = p2_intelligence.daily_brief(news, state)
        self.assertGreaterEqual(result["event_count"], 1)
        self.assertGreaterEqual(result["brief"][0]["daily_priority"], 0)

    def test_priority_reads_nested_intelligence_score(self):
        """The engine nests the score under `scores`; reading it top-level
        silently produced a flat, unsorted brief on production data."""
        self.assertEqual(p2_intelligence._intelligence_score(_event("e1", "a", 73)), 73)
        self.assertEqual(p2_intelligence._intelligence_score({"scores": {}}), 0)
        self.assertEqual(p2_intelligence._intelligence_score({"intelligence_score": 55}), 55)

    def test_brief_is_ordered_by_real_priority(self):
        news = [
            {"title": "low priority insurance product launch", "ai_score": 20, "research_topic": "ai_intelligent"},
            {"title": "high priority insurance regulation change", "ai_score": 95, "research_topic": "regulatory_change"},
        ]
        state = {"version": "p2-v1.0", "watchlists": [], "feedback": [], "monitoring": []}
        result = p2_intelligence.daily_brief(news, state)
        priorities = [row["daily_priority"] for row in result["brief"]]
        self.assertEqual(priorities, sorted(priorities, reverse=True))
        self.assertTrue(any(p > 0 for p in priorities), priorities)

    def test_watchlist_boost_and_feedback_apply_to_real_events(self):
        news = [{"title": "AI cyber insurance underwriting platform launch", "ai_score": 70, "research_topic": "ai_intelligent"}]
        state = {
            "version": "p2-v1.0",
            "watchlists": [{"id": "ai", "name": "AI", "enabled": True, "topics": ["ai_intelligent"], "keywords": ["AI"], "priority_boost": 10}],
            "feedback": [{"event_id": "e0", "label": "important"}],
            "monitoring": [],
        }
        result = p2_intelligence.daily_brief(news, state)
        self.assertEqual(result["watchlist_hits"], 1)
        self.assertEqual(result["brief"][0]["watchlist_matches"], ["ai"])

    def test_topic_scoped_watchlist_still_requires_keywords(self):
        """A topic filter narrows the candidate set; it must not satisfy the
        keyword filter on its own. Folding the topic slug into the keyword
        haystack made "AI" match `ai_intelligent`, so every event in the topic
        counted as a watchlist hit.
        """
        watchlist = {
            "id": "ai", "name": "AI保险", "enabled": True,
            "topics": ["ai_intelligent"], "keywords": ["AI", "大模型"],
            "priority_boost": 8,
        }
        on_topic_without_keywords = _event(
            "e1", "马云罕见海外投资布局公示", 70, topic="ai_intelligent"
        )
        on_topic_with_keywords = _event(
            "e2", "保险公司 大模型 智能核保平台上线", 70, topic="ai_intelligent"
        )
        off_topic = _event("e3", "再保险资本充足率调整", 70, topic="capital_reinsurance")

        self.assertFalse(p2_intelligence._match_watchlist(on_topic_without_keywords, watchlist))
        self.assertTrue(p2_intelligence._match_watchlist(on_topic_with_keywords, watchlist))
        self.assertFalse(p2_intelligence._match_watchlist(off_topic, watchlist))

    def test_load_news_accepts_production_data_shape(self):
        """`data.json` is a dict; P2 previously passed it straight through and
        crashed inside the clustering engine."""
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "data.json"
            path.write_text(json.dumps({
                "news": [{"title": "a"}, {"title": "b"}],
                "sources": [],
                "days": {},
                "version": "2.3.0",
            }), encoding="utf-8")
            self.assertEqual(len(p2_intelligence.load_news(path)), 2)

            bare = Path(d) / "bare.json"
            bare.write_text(json.dumps([{"title": "a"}]), encoding="utf-8")
            self.assertEqual(len(p2_intelligence.load_news(bare)), 1)


class P2ProductionDataTests(unittest.TestCase):
    """End-to-end guard: P2 must run against the real committed data.json.

    The synthetic fixtures above never exercised the production payload shape,
    which is why two bugs shipped unnoticed.
    """

    def test_daily_brief_runs_on_production_data(self):
        data_file = Path(__file__).resolve().parents[1] / "data.json"
        if not data_file.exists():
            self.skipTest("data.json not present")
        with tempfile.TemporaryDirectory() as d:
            old_state, old_output = p2_intelligence.STATE_PATH, p2_intelligence.OUTPUT_PATH
            p2_intelligence.STATE_PATH = Path(d) / "state.json"
            p2_intelligence.OUTPUT_PATH = Path(d) / "brief.json"
            try:
                result = p2_intelligence.run(p2_intelligence.load_news(data_file))
            finally:
                p2_intelligence.STATE_PATH, p2_intelligence.OUTPUT_PATH = old_state, old_output

        self.assertGreater(result["event_count"], 0)
        self.assertTrue(result["brief"])
        priorities = [row["daily_priority"] for row in result["brief"]]
        self.assertEqual(priorities, sorted(priorities, reverse=True))
        self.assertTrue(all(p > 0 for p in priorities), priorities)
        self.assertLessEqual(len(result["brief"]), p2_intelligence.BRIEF_LIMIT)


class P2WatchlistExpansionTests(unittest.TestCase):
    """2026-09 Watchlist 扩容回归锁：并购重组 / 监管动向 / 健康险。

    这三个关注面靠关键词全局匹配（topics 留空），必须真命中生产语料；
    upsert 不得丢失既有清单（如 ai）。
    """

    def test_expanded_watchlist_keyword_matching(self):
        ma = {"id": "ma", "name": "并购重组", "enabled": True, "topics": [],
              "keywords": ["并购", "收购", "股权"], "priority_boost": 7}
        reg = {"id": "regulatory", "name": "监管动向", "enabled": True, "topics": [],
               "keywords": ["监管", "处罚", "批复"], "priority_boost": 7}
        health = {"id": "health", "name": "健康险", "enabled": True, "topics": [],
                  "keywords": ["健康险", "医疗险", "惠民保", "长期护理", "护理", "重疾", "商业健康", "带病", "医疗"],
                  "priority_boost": 7}
        # 命中：关键词出现在 title
        self.assertTrue(p2_intelligence._match_watchlist(
            _event("e1", "Willis Re 收购美国 BMS Re 加速扩张", 70, topic="capital_reinsurance"), ma))
        self.assertTrue(p2_intelligence._match_watchlist(
            _event("e3", "陕西金融监管局推动巨灾保险机制", 70, topic="regulatory_change"), reg))
        self.assertTrue(p2_intelligence._match_watchlist(
            _event("e4", "人保健康推出长期护理保险产品", 70, topic="pension_finance"), health))
        # 不命中：无相关关键词
        self.assertFalse(p2_intelligence._match_watchlist(
            _event("e2", "AI 大模型合规应用指引发布", 70, topic="ai_intelligent"), ma))
        self.assertFalse(p2_intelligence._match_watchlist(
            _event("e5", "再保险资本充足率调整", 70, topic="capital_reinsurance"), health))

    def test_upsert_watchlist_preserves_existing_ids(self):
        with tempfile.TemporaryDirectory() as d:
            old = p2_intelligence.STATE_PATH
            p2_intelligence.STATE_PATH = Path(d) / "state.json"
            try:
                state = p2_intelligence.load_state()
                p2_intelligence.upsert_watchlist(state, {
                    "id": "ai", "name": "AI保险", "topics": ["ai_intelligent"],
                    "keywords": ["AI"], "priority_boost": 8})
                p2_intelligence.upsert_watchlist(state, {
                    "id": "ma", "name": "并购重组", "topics": [], "keywords": ["并购"], "priority_boost": 7})
                self.assertEqual([w["id"] for w in state["watchlists"]], ["ai", "ma"])
                # 重复 upsert 同 id 不新增重复项
                p2_intelligence.upsert_watchlist(state, {
                    "id": "ma", "name": "并购重组", "topics": [], "keywords": ["股权"], "priority_boost": 7})
                self.assertEqual([w["id"] for w in state["watchlists"]], ["ai", "ma"])
            finally:
                p2_intelligence.STATE_PATH = old

    def test_expanded_watchlists_present_and_surface_in_production(self):
        """锁住扩容：3 个新关注面必须在已提交 p2_state.json 中，且生产数据上
        各自在 top-20 简报内至少命中 1 条（避免静默回退到 0 命中）。"""
        state = p2_intelligence.load_state()
        ids = {w["id"] for w in state["watchlists"]}
        for wid in ("ma", "regulatory", "health"):
            self.assertIn(wid, ids, f"关注清单 {wid} 丢失")
        data_file = Path(__file__).resolve().parents[1] / "data.json"
        if not data_file.exists():
            self.skipTest("data.json not present")
        result = p2_intelligence.daily_brief(p2_intelligence.load_news(data_file), state)
        surfaced = set()
        for row in result["brief"]:
            surfaced.update(row.get("watchlist_matches", []))
        for wid in ("ma", "regulatory", "health"):
            self.assertIn(wid, surfaced, f"{wid} 在生产数据 top-20 简报内 0 命中")


if __name__ == "__main__":
    unittest.main()
