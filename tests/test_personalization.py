#!/usr/bin/env python3
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import personalization as P


class TestPersonalization(unittest.TestCase):
    def setUp(self):
        self.events = [
            {"title": "AI insurance product launch", "topic": "ai_intelligent", "event_type": "product", "entities": ["nvidia"], "scores": {"intelligence_score": 72}, "published_at": "2026-08-21T10:00:00+00:00"},
            {"title": "Munich Re acquisition", "topic": "capital_reinsurance", "event_type": "acquisition", "entities": ["munich re"], "scores": {"intelligence_score": 68}, "published_at": "2026-08-21T09:00:00+00:00"},
        ]

    def test_topic_and_entity_boost(self):
        profile = {"role": "technology", "topics": ["ai_intelligent"], "entities": ["nvidia"]}
        result = P.personalize(self.events, profile)
        self.assertEqual(result[0]["title"], "AI insurance product launch")
        self.assertTrue(result[0]["personalization"]["topic_match"])
        self.assertEqual(result[0]["personalization"]["entity_matches"], ["nvidia"])
        self.assertGreater(result[0]["personalization"]["personal_score"], 80)

    def test_role_boost_is_deterministic(self):
        profile = {"role": "investment", "topics": [], "entities": []}
        result = P.personalize(self.events, profile)
        self.assertEqual(result[0]["title"], "Munich Re acquisition")
        self.assertEqual(result[0]["personalization"]["personal_score"], 76)

    def test_profile_is_normalized_and_bounded(self):
        profile = P.normalize_profile({"role": "unknown", "topics": list(range(20)), "entities": list(range(30))})
        self.assertEqual(profile["role"], "executive")
        self.assertLessEqual(len(profile["topics"]), 8)
        self.assertLessEqual(len(profile["entities"]), 12)


if __name__ == "__main__":
    unittest.main()
