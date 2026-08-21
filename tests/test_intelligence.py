#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import intelligence as I


class TestIntelligence(unittest.TestCase):
    def test_multi_source_event_clustering(self):
        data = {"news": [
            {"id": 1, "title": "Munich Re to acquire At-Bay", "summary": "Munich Re announced acquisition of cyber insurance company At-Bay.", "source_name": "Reuters", "source_url": "https://reuters.example/a", "published_at": "2026-08-21T08:00:00+00:00", "ai_score": 90, "research_topic": "capital_reinsurance", "source_authority": 95, "date_verified": True},
            {"id": 2, "title": "Munich Re agrees to buy At-Bay", "summary": "The reinsurer will acquire At-Bay, expanding cyber insurance capabilities.", "source_name": "Insurance Journal", "source_url": "https://insurance.example/b", "published_at": "2026-08-21T07:30:00+00:00", "ai_score": 86, "research_topic": "capital_reinsurance", "source_authority": 84, "date_verified": True},
        ]}
        result = I.build(data)
        self.assertEqual(result["stats"]["event_count"], 1)
        event = result["events"][0]
        self.assertEqual(event["source_count"], 2)
        self.assertEqual(event["article_count"], 2)
        self.assertIn("what_happened", event["insight"])
        self.assertGreaterEqual(event["scores"]["confidence"], 70)

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
        for key in ("relevance", "impact", "novelty", "actionability", "confidence", "intelligence_score"):
            self.assertIn(key, event["scores"])
        for key in ("what_happened", "why_it_matters", "who_is_affected", "what_to_watch", "evidence", "confidence"):
            self.assertIn(key, event["insight"])
        self.assertEqual(event["insight"]["confidence"], event["scores"]["confidence"])


if __name__ == "__main__":
    unittest.main()
