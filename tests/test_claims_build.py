import unittest
from claims_build import build_claims


class ClaimsBuildTests(unittest.TestCase):
    def setUp(self):
        self.event = {"event_id": "evt_claims", "title": "Munich Re acquires At-Bay"}
        self.items = [
            {"source_name":"Reuters","source_url":"https://www.reuters.com/example","published_at":"2026-08-25T08:00:00Z","title":"Munich Re acquires At-Bay","summary":"Munich Re agreed to acquire At-Bay for $575m.","tags":"Munich Re, At-Bay","date_verified":True},
            {"source_name":"Insurance Journal","source_url":"https://www.insurancejournal.com/example","published_at":"2026-08-25T09:00:00Z","title":"Munich Re agrees to buy At-Bay","summary":"The transaction value is $575m.","tags":"Munich Re, At-Bay","date_verified":True},
        ]

    def test_cross_checked_claims_have_two_domains(self):
        result = build_claims(self.items, self.event)
        self.assertGreaterEqual(result["cross_checked"], 1)
        self.assertEqual(result["unsupported"], 0)
        self.assertGreaterEqual(result["coverage"], 100)
        numeric = next(x for x in result["claims"] if x["type"] == "numeric")
        self.assertEqual(numeric["status"], "cross_checked")
        self.assertEqual(numeric["independent_domains"], 2)
        self.assertTrue(numeric["evidence_refs"])

    def test_single_source_numeric_claim_does_not_become_cross_checked(self):
        result = build_claims(self.items[:1], self.event)
        numeric = next(x for x in result["claims"] if x["type"] == "numeric")
        self.assertEqual(numeric["independent_domains"], 1)
        self.assertEqual(numeric["status"], "single_source")

    def test_state_counts_are_consistent(self):
        result = build_claims(self.items, self.event)
        self.assertEqual(result["cross_checked"], sum(x["status"] == "cross_checked" for x in result["claims"]))
        self.assertEqual(result["unsupported"], sum(x["status"] == "unverified" for x in result["claims"]))


if __name__ == "__main__":
    unittest.main()
