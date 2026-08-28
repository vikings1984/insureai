import json
import tempfile
import unittest
from pathlib import Path

import p2_intelligence


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


if __name__ == "__main__":
    unittest.main()
