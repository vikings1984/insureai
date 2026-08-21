#!/usr/bin/env python3
import unittest
import trust as T

class TestTrust(unittest.TestCase):
    def test_single_source_is_not_high_confidence(self):
        items=[{"source_name":"A","source_url":"https://a.example/a","title":"Munich Re acquisition","published_at":"2026-08-21T10:00:00+00:00","date_verified":True}]
        result=T.assess(items,{"source_count":1})
        self.assertIn(result["level"],["low","medium"])
        self.assertEqual(result["independent_domains"],1)

    def test_multiple_sources_improve_trust(self):
        items=[
          {"source_name":"A","source_url":"https://a.example/a","title":"Munich Re acquires At-Bay for 575 million","published_at":"2026-08-21T10:00:00+00:00","date_verified":True},
          {"source_name":"B","source_url":"https://b.example/b","title":"Munich Re acquisition of At-Bay for 575 million","published_at":"2026-08-21T11:00:00+00:00","date_verified":True},
        ]
        result=T.assess(items,{"source_count":2})
        self.assertEqual(result["independent_domains"],2)
        self.assertFalse(result["conflict"])
        self.assertGreater(result["score"],60)

    def test_numeric_conflict_is_flagged(self):
        items=[
          {"source_url":"https://a.example/a","title":"Acquisition for 575 million","published_at":"2026-08-21"},
          {"source_url":"https://b.example/b","title":"Acquisition for 650 million","published_at":"2026-08-21"},
        ]
        result=T.assess(items,{"source_count":2})
        self.assertIn("numeric_facts",result["conflict_fields"])
        self.assertTrue(result["conflict"])

if __name__=="__main__": unittest.main()
