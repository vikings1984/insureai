#!/usr/bin/env python3
import unittest

from review import build_review_queue


class TestReviewQueue(unittest.TestCase):
    def test_conflict_and_weak_evidence_get_review_priority(self):
        data = {
            "events": [{
                "event_id": "evt1",
                "title": "Test event",
                "scores": {"intelligence_score": 90},
                "trust": {"level": "medium", "conflict": True},
                "claims": {"coverage": 50},
                "decision": {"urgency": "now"},
                "article_count": 1,
                "article_ids": ["a1"],
                "source_count": 2,
            }]
        }
        result = build_review_queue(data)
        self.assertEqual(result["generated_count"], 1)
        item = result["items"][0]
        self.assertEqual(item["status"], "pending")
        self.assertGreaterEqual(item["priority"], 90)
        reason_types = {x["type"] for x in item["reasons"]}
        self.assertIn("conflict", reason_types)
        self.assertIn("evidence", reason_types)
        self.assertIn("decision", reason_types)

    def test_clean_low_impact_event_is_not_queued(self):
        data = {
            "events": [{
                "event_id": "evt2",
                "title": "Routine update",
                "scores": {"intelligence_score": 60},
                "trust": {"level": "high", "conflict": False},
                "claims": {"coverage": 100},
                "decision": {"urgency": "watch"},
                "article_count": 3,
                "article_ids": ["a1", "a2", "a3"],
                "source_count": 3,
            }]
        }
        result = build_review_queue(data)
        self.assertEqual(result["generated_count"], 0)


if __name__ == "__main__":
    unittest.main()
