#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import unittest
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import intelligence as I


class TestIntelligence(unittest.TestCase):
    def test_multi_source_event_clustering(self):
        data = {"news": [
            {"id": 1, "title": "Munich Re to acquire At-Bay", "summary": "Munich Re announced acquisition of cyber insurance company At-Bay.", "source_name": "Reuters", "source_url": "https://reuters.example/a", "published_at": "2026-08-21T08:00:00+00:00", "ai_score": 90, "research_topic": "capital_reinsurance", "source_authority": 95, "date_verified": True},
            {"id": 2, "title": "Munich Re agrees to buy At-Bay", "summary": "The reinsurer will acquire At-Bay, expanding cyber insurance capabilities.", "source_name": "Insurance Journal", "source_url": "https://insurance.example/b", "published_at": "2026-08-21T07:30:00+00:00", "ai_score": 86, "research_topic": "capital_reinsurance", "source_authority": 84, "date_verified": True},
        ]}
        event = I.build(data)["events"][0]
        self.assertEqual(event["source_count"], 2)
        self.assertEqual(event["article_count"], 2)
        self.assertEqual(event["event_type"], "acquisition")
        self.assertTrue(any("munich" in entity for entity in event["entities"]))
        self.assertTrue(any("at-bay" in entity for entity in event["entities"]))
        self.assertGreaterEqual(event["scores"]["confidence"], 70)

    def test_same_company_different_old_event_is_not_merged(self):
        data = {"news": [
            {"id": 1, "title": "Munich Re to acquire At-Bay", "summary": "acquisition of cyber insurance company At-Bay", "source_name": "Reuters", "source_url": "https://reuters.example/a", "published_at": "2026-08-21T08:00:00+00:00", "ai_score": 90, "research_topic": "capital_reinsurance", "source_authority": 95},
            {"id": 2, "title": "Munich Re exits legacy portfolio", "summary": "Munich Re announces a separate portfolio transaction", "source_name": "Insurance Journal", "source_url": "https://insurance.example/b", "published_at": "2026-08-16T08:00:00+00:00", "ai_score": 82, "research_topic": "capital_reinsurance", "source_authority": 84},
        ]}
        result = I.build(data)
        self.assertEqual(result["stats"]["event_count"], 2)

    def test_personnel_event_is_less_actionable(self):
        data = {"news": [{
            "id": 3,
            "title": "Vantage appoints Lucy Fato as General Counsel",
            "summary": "The specialty reinsurance business announced the appointment.",
            "source_name": "Reinsurance News",
            "source_url": "https://example.com/c",
            "published_at": "2026-08-21T06:00:00+00:00",
            "ai_score": 80,
            "research_topic": "capital_reinsurance",
            "source_authority": 82,
        }]}
        event = I.build(data)["events"][0]
        self.assertEqual(event["event_type"], "personnel")
        self.assertLessEqual(event["scores"]["actionability"], 42)
        self.assertLessEqual(event["scores"]["impact"], 55)

    def test_output_is_explainable(self):
        result = I.build({"news": [{
            "id": 4,
            "title": "Regulator launches new cyber insurance rules",
            "summary": "The regulator announced new insurance compliance requirements.",
            "source_name": "Regulator",
            "source_url": "https://example.com/d",
            "published_at": "2026-08-21T05:00:00+00:00",
            "ai_score": 92,
            "research_topic": "regulatory_change",
            "source_authority": 100,
            "date_verified": True,
        }]})
        event = result["events"][0]
        self.assertEqual(event["event_type"], "regulatory")
        for key in ("relevance", "impact", "novelty", "actionability", "confidence", "intelligence_score"):
            self.assertIn(key, event["scores"])
        for key in ("what_happened", "why_it_matters", "who_is_affected", "what_to_watch", "evidence", "confidence"):
            self.assertIn(key, event["insight"])
        self.assertEqual(event["insight"]["confidence"], event["scores"]["confidence"])

    def test_radar_contains_entity_and_trend_signals(self):
        now = datetime.now(timezone.utc)
        def item(i, title, days_ago, topic):
            ts = (now - timedelta(days=days_ago)).isoformat()
            return {
                "id": i, "title": title, "summary": "insurance event",
                "source_name": "Source", "source_url": "https://example.com/%s" % i,
                "published_at": ts, "ai_score": 85, "research_topic": topic,
                "source_authority": 85, "date_verified": True,
            }
        result = I.build({"news": [
            item(1, "Munich Re acquires At-Bay", 1, "capital_reinsurance"),
            item(2, "Munich Re expands cyber business", 2, "capital_reinsurance"),
            item(3, "Munich Re launches new risk service", 3, "capital_reinsurance"),
            item(4, "New pension reform released", 10, "pension_finance"),
        ]})
        radar = result["radar"]
        self.assertIn("entity_radar", radar)
        self.assertIn("topic_trends", radar)
        self.assertGreaterEqual(radar["stats"]["entities"], 1)
        self.assertTrue(any(x["topic"] == "capital_reinsurance" for x in radar["topic_trends"]))


if __name__ == "__main__":
    unittest.main()
