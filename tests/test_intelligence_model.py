import unittest

from intelligence import build


class IntelligenceModelTests(unittest.TestCase):
    def _item(self, title, source, url, published_at, tags, topic="capital_reinsurance", score=88, verified=True):
        return {
            "id": f"{source}-{published_at}",
            "title": title,
            "summary": title,
            "tags": tags,
            "source_name": source,
            "source_url": url,
            "published_at": published_at,
            "date_verified": verified,
            "source_authority": 90,
            "ai_score": score,
            "research_topic": topic,
        }

    def test_same_event_clusters_but_personnel_event_does_not_merge(self):
        rows = [
            self._item("Munich Re to acquire At-Bay", "Reuters", "https://reuters.com/a", "2026-08-21T10:00:00+00:00", "Munich Re,At-Bay"),
            self._item("Munich Re agrees to buy At-Bay for $575 million", "Insurance Journal", "https://insurancejournal.com/a", "2026-08-21T11:00:00+00:00", "Munich Re,At-Bay"),
            self._item("Munich Re appoints new CFO", "Reuters", "https://reuters.com/b", "2026-08-21T12:00:00+00:00", "Munich Re", topic="digital_transformation", score=72),
        ]
        result = build({"news": rows})
        self.assertEqual(result["stats"]["event_count"], 2)
        acquisition = next(x for x in result["events"] if x["event_type"] == "acquisition")
        self.assertEqual(acquisition["source_count"], 2)
        self.assertGreaterEqual(acquisition["evidence_coverage"], 80)
        self.assertFalse(acquisition["review_required"])

    def test_same_event_variants_merge_despite_anchor_conflict(self):
        rows = [
            self._item("Munich Re to acquire At-Bay for $575 million", "Reuters", "https://reuters.com/sp1", "2026-08-21T11:00:00+00:00", "Munich Re,At-Bay"),
            self._item("Munich Re seals At-Bay deal", "Insurance Journal", "https://insurancejournal.com/sp2", "2026-08-21T12:00:00+00:00", "Munich Re,At-Bay"),
            self._item("At-Bay confirms acquisition by Munich Re", "At-Bay Press", "https://at-bay.com/sp3", "2026-08-21T13:00:00+00:00", "At-Bay,Munich Re"),
        ]
        result = build({"news": rows})
        self.assertEqual(result["stats"]["event_count"], 1)
        event = result["events"][0]
        self.assertEqual(event["source_count"], 3)
        self.assertEqual(len(event["article_ids"]), 3)

    def test_same_entities_different_actions_do_not_merge(self):
        rows = [
            self._item("Munich Re to acquire At-Bay for $575 million", "Reuters", "https://reuters.com/gd1", "2026-08-21T11:00:00+00:00", "Munich Re,At-Bay"),
            self._item("At-Bay and Munich Re launch cyber insurance partnership", "Insurance Journal", "https://insurancejournal.com/gd2", "2026-08-21T12:00:00+00:00", "At-Bay,Munich Re", topic="digital_transformation"),
        ]
        result = build({"news": rows})
        self.assertEqual(result["stats"]["event_count"], 2)
        types = sorted(x["event_type"] for x in result["events"])
        self.assertIn("acquisition", types)
        self.assertNotEqual(result["events"][0]["event_id"], result["events"][1]["event_id"])

    def test_single_source_event_has_review_boundary(self):
        rows = [
            self._item("Regulator issues new insurance AI guidance", "Regulator", "https://regulator.example/guidance", "2026-08-21T10:00:00+00:00", "Regulator", topic="regulatory_change")
        ]
        result = build({"news": rows})
        event = result["events"][0]
        self.assertEqual(event["evidence_status"], "single_source")
        self.assertLess(event["evidence_coverage"], 75)
        self.assertTrue(event["review_required"])
        self.assertIn("event_fingerprint", event)
        self.assertIn("trust", event)


if __name__ == "__main__":
    unittest.main()
