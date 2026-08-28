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


if __name__ == "__main__":
    unittest.main()
