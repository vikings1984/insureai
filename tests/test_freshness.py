import unittest
from datetime import datetime, timezone, timedelta
from freshness import build_freshness


class FreshnessTests(unittest.TestCase):
    def test_empty_input_is_unavailable(self):
        out = build_freshness(None)
        self.assertEqual(out["status"], "unavailable")
        self.assertIsNone(out["stale"])
        self.assertEqual(out["date_coverage"], 0.0)

    def test_coverage_and_latest_age(self):
        now = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)
        doc = {"items": [
            {"published_at": "2026-08-21T10:00:00+00:00"},
            {"title": "no date"},
            {"date": "2026-08-20"},
        ]}
        out = build_freshness(doc, now=now)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["dated_article_count"], 2)
        self.assertAlmostEqual(out["date_coverage"], 2/3, places=4)
        self.assertAlmostEqual(out["latest_age_hours"], 2.0, places=2)
        self.assertFalse(out["stale"])

    def test_stale_input(self):
        now = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)
        doc = [{"published_at": (now - timedelta(hours=30)).isoformat()}]
        out = build_freshness(doc, now=now, stale_after_hours=24)
        self.assertTrue(out["stale"])

    def test_undated_input_does_not_fake_freshness(self):
        now = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)
        out = build_freshness([{"title": "unknown"}], now=now)
        self.assertEqual(out["status"], "undated")
        self.assertIsNone(out["latest_age_hours"])
        self.assertFalse(out["stale"])


if __name__ == "__main__":
    unittest.main()
