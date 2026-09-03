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


class TestPerfMemoization(unittest.TestCase):
    """T1 性能债治理回归守卫。

    性能优化（_entities/_event_type/_tokens/_norm/_timestamp 记忆化 + canonical
    registry 单次构建复用）必须满足三条不变式，任一被破坏即失败：
      (a) 去重生效：二次调用命中缓存、返回同一对象（这是提速的来源）；
      (b) 语义透明：缓存前后的返回值必须逐字节一致（memo 不得改变任何结果）；
      (c) 可清空：clear_memo() 能彻底重置全部缓存，不跨构建泄漏状态。
    """

    ITEM = {
        "id": 9001, "title": "Munich Re to acquire At-Bay",
        "summary": "Munich Re announced acquisition of cyber insurance company At-Bay.",
        "tags": "Munich Re,At-Bay", "published_at": "2026-08-21T08:00:00+00:00",
        "source_name": "Reuters", "ai_score": 90, "research_topic": "capital_reinsurance",
    }

    def setUp(self):
        I.clear_memo()

    def tearDown(self):
        I.clear_memo()

    def test_clear_memo_empties_all_caches(self):
        I._entities(self.ITEM)
        I._event_type(self.ITEM)
        I._timestamp(self.ITEM)
        I._norm(self.ITEM["title"])
        I._tokens(self.ITEM["title"])
        I._canonical_registry()
        # 先确认缓存确实被填充（否则"清空"断言毫无意义）
        self.assertTrue(I._ENTITIES_MEMO)
        self.assertTrue(I._EVENT_TYPE_MEMO)
        self.assertTrue(I._TIMESTAMP_MEMO)
        self.assertTrue(I._NORM_MEMO)
        self.assertTrue(I._TOKENS_MEMO)
        self.assertTrue(I._CANON_REGISTRY_LOADED)

        I.clear_memo()
        self.assertEqual(len(I._ENTITIES_MEMO), 0)
        self.assertEqual(len(I._EVENT_TYPE_MEMO), 0)
        self.assertEqual(len(I._TIMESTAMP_MEMO), 0)
        self.assertEqual(len(I._NORM_MEMO), 0)
        self.assertEqual(len(I._TOKENS_MEMO), 0)
        self.assertFalse(I._CANON_REGISTRY_LOADED)

    def test_memo_does_not_change_returned_values(self):
        """不变式 (b)：memo 必须语义透明，缓存前后返回值完全一致。"""
        item = dict(self.ITEM)
        first = (I._entities(item), I._event_type(item), I._timestamp(item),
                 I._norm(item["title"]), I._tokens(item["title"]))
        I.clear_memo()
        second = (I._entities(item), I._event_type(item), I._timestamp(item),
                  I._norm(item["title"]), I._tokens(item["title"]))
        self.assertEqual(first, second)

    def test_cache_hit_returns_same_object(self):
        """不变式 (a)：二次调用命中缓存返回同一对象，证明重复计算已被消除。"""
        item = dict(self.ITEM)
        self.assertIs(I._entities(item), I._entities(item))
        self.assertIs(I._event_type(item), I._event_type(item))
        self.assertIs(I._tokens(item["title"]), I._tokens(item["title"]))

    def test_registry_loaded_once_per_build(self):
        """不变式 (a)：canonical registry 在单次构建内只从磁盘加载一次。"""
        self.assertFalse(I._CANON_REGISTRY_LOADED)
        r1 = I._canonical_registry()
        self.assertTrue(I._CANON_REGISTRY_LOADED)
        r2 = I._canonical_registry()
        self.assertIs(r1, r2)
        I.clear_memo()
        self.assertFalse(I._CANON_REGISTRY_LOADED)

    def test_build_is_deterministic_with_memo(self):
        """不变式 (c)：连续两次 build，事件与统计必须一致，memo 不得跨构建污染。

        注意只比对 events/stats，不比对 radar——radar 由 datetime.now() 驱动的
        时间衰减权重构成，本身即随时间漂移，与 memo 无关。
        """
        data = {"news": [
            {"id": 1, "title": "Munich Re to acquire At-Bay", "summary": "Munich Re announced acquisition of At-Bay.", "source_name": "Reuters", "source_url": "https://reuters.example/a", "published_at": "2026-08-21T08:00:00+00:00", "ai_score": 90, "research_topic": "capital_reinsurance", "source_authority": 95, "date_verified": True},
            {"id": 2, "title": "Munich Re agrees to buy At-Bay", "summary": "The reinsurer will acquire At-Bay.", "source_name": "Insurance Journal", "source_url": "https://insurance.example/b", "published_at": "2026-08-21T07:30:00+00:00", "ai_score": 86, "research_topic": "capital_reinsurance", "source_authority": 84, "date_verified": True},
        ]}
        first = I.build(data)
        second = I.build(data)
        self.assertEqual(first["events"], second["events"])
        self.assertEqual(first["stats"], second["stats"])


if __name__ == "__main__":
    unittest.main()
