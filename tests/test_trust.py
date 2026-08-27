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


class TestSourceTierTrust(unittest.TestCase):
    def test_tier1_single_source_reaches_medium(self):
        items=[{"source_name":"金融监管总局","source_url":"https://www.nfra.gov.cn/x","title":"监管发布保险业资金运用新规","published_at":"2026-08-21T10:00:00+00:00","date_verified":True}]
        result=T.assess(items,{"source_count":1})
        self.assertEqual(result["best_source_tier"],1)
        self.assertIn(result["level"],["medium","high"])
        self.assertGreaterEqual(result["score"],62)

    def test_tier3_pair_never_reaches_high(self):
        items=[
          {"source_url":"https://www.insurancejournal.com/a","title":"Munich Re to acquire At-Bay for 575 million","published_at":"2026-08-21T10:00:00+00:00","date_verified":True},
          {"source_url":"https://www.reinsurancene.ws/b","title":"Munich Re agrees to buy At-Bay for 575 million","published_at":"2026-08-21T11:00:00+00:00","date_verified":True},
        ]
        result=T.assess(items,{"source_count":2})
        self.assertEqual(result["best_source_tier"],3)
        self.assertNotEqual(result["level"],"high")
        self.assertLessEqual(result["score"],78)

    def test_tier1_plus_announcement_can_reach_high(self):
        items=[
          {"source_name":"金融监管总局","source_url":"https://www.nfra.gov.cn/a","title":"国家金融监督管理总局 NFRA issues new insurance fund utilization rules","published_at":"2026-08-21T10:00:00+00:00","date_verified":True},
          {"source_name":"公司公告","source_url":"https://example.com/b","source_type":"公司发布","title":"NFRA issues new insurance fund utilization rules 公司公告","published_at":"2026-08-21T11:00:00+00:00","date_verified":True},
        ]
        result=T.assess(items,{"source_count":2})
        self.assertEqual(result["best_source_tier"],1)
        self.assertEqual(result["level"],"high")

    def test_tier3_pair_distinguishable_from_tier1_pair(self):
        tier3=T.assess([
          {"source_url":"https://www.insurancejournal.com/a","title":"Munich Re to acquire At-Bay for 575 million","published_at":"2026-08-21T10:00:00+00:00","date_verified":True},
          {"source_url":"https://www.reinsurancene.ws/b","title":"Munich Re agrees to buy At-Bay for 575 million","published_at":"2026-08-21T11:00:00+00:00","date_verified":True},
        ],{"source_count":2})
        tier1=T.assess([
          {"source_name":"金融监管总局","source_url":"https://www.nfra.gov.cn/a","title":"国家金融监督管理总局 NFRA issues new insurance fund utilization rules","published_at":"2026-08-21T10:00:00+00:00","date_verified":True},
          {"source_name":"公司公告","source_url":"https://example.com/b","source_type":"公司发布","title":"NFRA issues new insurance fund utilization rules 公司公告","published_at":"2026-08-21T11:00:00+00:00","date_verified":True},
        ],{"source_count":2})
        self.assertGreater(tier1["score"],tier3["score"])

    def test_evidence_rows_carry_source_tier(self):
        items=[{"source_name":"Reuters","source_url":"https://www.reuters.com/a","title":"Munich Re to acquire At-Bay","published_at":"2026-08-21T10:00:00+00:00","date_verified":True}]
        trust=T.summarize_event_trust(items,{"source_count":1})
        self.assertEqual(trust["evidence"][0]["source_tier"],2)
        self.assertEqual(trust["best_source_tier"],2)

if __name__=="__main__": unittest.main()
