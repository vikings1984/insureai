import unittest
from claims_build import build_claims


class ClaimsBuildTests(unittest.TestCase):
    def setUp(self):
        self.event = {"event_id": "evt_claims", "title": "Munich Re acquires At-Bay"}
        self.items = [
            {"source_name": "Reuters", "source_url": "https://www.reuters.com/example", "published_at": "2026-08-25T08:00:00Z", "title": "Munich Re acquires At-Bay", "summary": "Munich Re agreed to acquire At-Bay for $575m.", "tags": "Munich Re, At-Bay", "date_verified": True},
            {"source_name": "Insurance Journal", "source_url": "https://www.insurancejournal.com/example", "published_at": "2026-08-25T09:00:00Z", "title": "Munich Re agrees to buy At-Bay", "summary": "The transaction value is $575m.", "tags": "Munich Re, At-Bay", "date_verified": True},
        ]

    def test_cross_checked_claims_have_two_domains(self):
        result = build_claims(self.items, self.event)
        self.assertGreaterEqual(result["cross_checked"], 1)
        self.assertEqual(result["unsupported"], 0)
        self.assertGreaterEqual(result["coverage"], 100)
        amount = next(x for x in result["claims"] if x["claim_type"] == "transaction_amount")
        self.assertEqual(amount["verification_status"], "cross_checked")
        self.assertEqual(amount["independent_domains"], 2)
        self.assertTrue(amount["evidence_refs"])

    def test_single_source_amount_claim_does_not_become_cross_checked(self):
        result = build_claims(self.items[:1], self.event)
        amount = next(x for x in result["claims"] if x["claim_type"] == "transaction_amount")
        self.assertEqual(amount["independent_domains"], 1)
        self.assertEqual(amount["verification_status"], "single_source")
        self.assertLessEqual(amount["confidence"], 65)

    def test_state_counts_are_consistent(self):
        result = build_claims(self.items, self.event)
        self.assertEqual(result["cross_checked"], sum(x["verification_status"] == "cross_checked" for x in result["claims"]))
        self.assertEqual(result["unsupported"], sum(x["verification_status"] == "unverified" for x in result["claims"]))
        self.assertEqual(result["conflicted"], sum(x["verification_status"] == "conflicted" for x in result["claims"]))

    def test_conflicted_claims_are_counted(self):
        conflict = [
            dict(self.items[0]),
            dict(self.items[1], summary="The transaction value is $600m.", title="Munich Re agrees to buy At-Bay"),
        ]
        result = build_claims(conflict, self.event)
        self.assertGreaterEqual(result["conflicted"], 1)
        conflicted = [x for x in result["claims"] if x["verification_status"] == "conflicted"]
        self.assertTrue(all(x["contradicting_evidence"] for x in conflicted))


if __name__ == "__main__":
    unittest.main()
