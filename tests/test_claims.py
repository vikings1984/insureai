#!/usr/bin/env python3
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import claims


class TestClaims(unittest.TestCase):
    def setUp(self):
        self.items = [
            {"id":"1","title":"Munich Re to acquire At-Bay for $575 million","tags":"Munich Re,At-Bay","source_name":"Reuters","source_url":"https://www.reuters.com/example","published_at":"2026-08-21T10:00:00+00:00","date_verified":True},
            {"id":"2","title":"Munich Re agrees to buy At-Bay for $575 million","tags":"Munich Re,At-Bay","source_name":"Insurance Journal","source_url":"https://www.insurancejournal.com/example","published_at":"2026-08-21T11:00:00+00:00","date_verified":True},
        ]
        self.event = {"event_id":"evt_1","title":"Munich Re 收购 At-Bay","event_type":"acquisition"}

    def test_claims_are_cross_checked(self):
        result = claims.build_claims(self.items, self.event)
        self.assertGreaterEqual(len(result["claims"]), 3)
        self.assertGreaterEqual(result["cross_checked"], 1)
        self.assertEqual(result["coverage"], 100)
        numeric = next(x for x in result["claims"] if x["type"] == "numeric")
        self.assertEqual(numeric["status"], "cross_checked")
        self.assertEqual(numeric["independent_domains"], 2)

    def test_single_source_claim_not_cross_checked(self):
        result = claims.build_claims(self.items[:1], self.event)
        self.assertTrue(all(x["status"] in ("supported", "uncorroborated") for x in result["claims"]))
        self.assertEqual(result["cross_checked"], 0)


if __name__ == "__main__":
    unittest.main()
