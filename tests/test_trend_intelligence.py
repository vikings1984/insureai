#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P1-1 Trend Intelligence 契约测试（TRD-1/2/3）。

全部用相对 now 构造的 hermetic 事件，不读取磁盘工件；版本值一律取自
contract.ARTIFACT_VERSIONS 单源，防止 schema 升版漂移。
"""
import unittest
from datetime import datetime, timedelta, timezone

from contract import ARTIFACT_VERSIONS
from radar import build_radar, build_topic_trends
from trend_intelligence import attach_cluster_ids, build_event_clusters, build_trend_intelligence


def _now():
    return datetime.now(timezone.utc)


def _ev(event_id, topic, title, days_ago=0, hours_ago=0, entities=(), domains=(), score=80):
    published = _now() - timedelta(days=days_ago, hours=hours_ago)
    return {
        "event_id": event_id,
        "topic": topic,
        "title": title,
        "published_at": published.isoformat(),
        "entities": list(entities),
        "source_count": max(1, len(domains)),
        "scores": {"intelligence_score": score},
        "evidence": [{"domain": d, "source_url": f"https://{d}/a"} for d in domains],
    }


class TopicDynamicsTests(unittest.TestCase):
    def test_velocity_acceleration_and_source_diversity(self):
        events = [
            _ev("a", "capital_reinsurance", "Munich Re to acquire At-Bay", days_ago=1, domains=["reuters.com"]),
            _ev("b", "capital_reinsurance", "Munich Re to acquire At-Bay", days_ago=2, domains=["insurancejournal.com"]),
            _ev("c", "capital_reinsurance", "Munich Re to acquire At-Bay", days_ago=3, domains=["reuters.com"]),
            _ev("d", "capital_reinsurance", "Munich Re to acquire At-Bay", days_ago=10, domains=["reuters.com"]),
            _ev("e", "capital_reinsurance", "Munich Re to acquire At-Bay", days_ago=17, domains=["reuters.com"]),
            _ev("f", "capital_reinsurance", "Munich Re to acquire At-Bay", days_ago=18, domains=["reuters.com"]),
        ]
        trend = build_topic_trends(events)[0]
        # w0=3, w1=1, w2=2 -> velocity=(3-1)/1=2.0; prev_v=(1-2)/2=-0.5; accel=2.5
        self.assertEqual(trend["velocity"], 2.0)
        self.assertEqual(trend["acceleration"], 2.5)
        self.assertEqual(trend["source_diversity"], 2)

    def test_persistence_counts_consecutive_active_days(self):
        events = [
            _ev("today", "pension_finance", "Pension insurer expands annuity range", days_ago=0),
            _ev("yesterday", "pension_finance", "Pension insurer expands annuity range", days_ago=1),
            _ev("twodays", "pension_finance", "Pension insurer expands annuity range", days_ago=2),
            _ev("gap", "pension_finance", "Pension insurer expands annuity range", days_ago=5),
        ]
        trend = build_topic_trends(events)[0]
        self.assertEqual(trend["persistence"], 3)

    def test_new_topic_velocity_uses_events_when_no_previous_week(self):
        events = [_ev("only", "ai_intelligent", "Insurer deploys AI underwriting", days_ago=1)]
        trend = build_topic_trends(events)[0]
        # w1=0 -> velocity = (1-0)/max(1,0) = 1.0
        self.assertEqual(trend["velocity"], 1.0)

    def test_rising_topic_carries_four_element_why(self):
        events = [
            _ev(f"r{i}", "product_innovation", f"Parametric Inc launches parametric product v{i}", days_ago=1, entities=["Parametric Inc"], domains=["reuters.com"])
            for i in range(5)
        ] + [
            _ev("r_prev", "product_innovation", "Parametric Inc launches parametric product", days_ago=10, entities=["Parametric Inc"], domains=["reuters.com"]),
        ]
        trend = build_topic_trends(events)[0]
        self.assertEqual(trend["direction"], "rising")
        why = trend["why"]
        self.assertEqual(why["independent_events"], 5)
        self.assertEqual(why["sources"], 1)
        self.assertIn("days", why)
        self.assertEqual(why["core_entities"], ["Parametric Inc"])
        self.assertEqual(len(why["event_ids"]), 5)


class EventClusterTests(unittest.TestCase):
    def test_similar_events_cluster_and_distinct_entities_do_not(self):
        now = _now()
        events = [
            _ev("c1", "capital_reinsurance", "Munich Re to acquire At-Bay", hours_ago=1, entities=["Munich Re", "At-Bay"]),
            _ev("c2", "capital_reinsurance", "Munich Re seals At-Bay deal", hours_ago=3, entities=["Munich Re", "At-Bay"]),
            _ev("c3", "capital_reinsurance", "Lloyd appoints new chairman of syndicate", hours_ago=5, entities=["Lloyd"]),
        ]
        clusters = build_event_clusters(events, now=now)
        self.assertEqual(len(clusters), 2)
        counts = sorted(c["event_count"] for c in clusters)
        self.assertEqual(counts, [1, 2])
        merged = next(c for c in clusters if c["event_count"] == 2)
        self.assertEqual(sorted(merged["event_ids"]), ["c1", "c2"])
        self.assertEqual(merged["source_diversity"], 0)

    def test_cluster_fields_are_traceable(self):
        now = _now()
        events = [
            _ev("x1", "climate_catastrophe", "PERILS estimates storm loss", days_ago=1, entities=["PERILS"], domains=["artemis.bm"]),
            _ev("x2", "climate_catastrophe", "PERILS estimates storm loss", days_ago=2, entities=["PERILS"], domains=["reinsurancene.ws"]),
        ]
        cluster = build_event_clusters(events, now=now)[0]
        self.assertTrue(cluster["cluster_id"].startswith("tc_climate_catastrophe_"))
        self.assertEqual(cluster["event_count"], 2)
        self.assertEqual(cluster["source_diversity"], 2)
        self.assertEqual(cluster["persistence"], 2)
        self.assertIn("PERILS", cluster["core_entities"])

    def test_events_outside_window_are_excluded(self):
        now = _now()
        events = [
            _ev("fresh", "regulatory_change", "Regulator issues new solvency rule", days_ago=5),
            _ev("stale", "regulatory_change", "Regulator issues new solvency rule", days_ago=45),
        ]
        clusters = build_event_clusters(events, now=now)
        ids = [i for c in clusters for i in c["event_ids"]]
        self.assertIn("fresh", ids)
        self.assertNotIn("stale", ids)

    def test_attach_cluster_ids_links_active_clusters_only(self):
        now = _now()
        events = [
            _ev("recent", "capital_reinsurance", "Munich Re to acquire At-Bay", days_ago=2),
            _ev("old", "capital_reinsurance", "Fitch upgrades insurer rating", days_ago=20),
        ]
        clusters = build_event_clusters(events, now=now)
        trends = [{"topic": "capital_reinsurance", "direction": "stable"}]
        attached = attach_cluster_ids(trends, clusters)
        active_ids = {c["cluster_id"] for c in clusters if "recent" in c["event_ids"]}
        self.assertEqual(set(attached[0]["cluster_ids"]), active_ids)


class TrendArtifactTests(unittest.TestCase):
    def test_radar_json_version_from_contract_single_source(self):
        radar = build_radar([])
        self.assertEqual(radar["version"], ARTIFACT_VERSIONS["radar.json"])
        artifact = build_trend_intelligence({"events": [], "radar": radar})
        self.assertEqual(artifact["version"], ARTIFACT_VERSIONS["radar.json"])

    def test_build_trend_intelligence_shape(self):
        now = _now()
        events = [
            _ev("k1", "capital_reinsurance", "Munich Re to acquire At-Bay", days_ago=1, entities=["Munich Re", "At-Bay"], domains=["reuters.com"]),
            _ev("k2", "capital_reinsurance", "Munich Re seals At-Bay deal", days_ago=2, entities=["Munich Re", "At-Bay"], domains=["insurancejournal.com"]),
        ]
        radar = build_radar(events)
        result = build_trend_intelligence({"events": events, "radar": radar}, now=now)
        self.assertEqual(result["stats"]["clusters"], 1)
        self.assertEqual(result["stats"]["clustered_events"], 2)
        self.assertTrue(result["topic_trends"][0]["cluster_ids"])
        cluster = result["event_clusters"][0]
        self.assertEqual(sorted(cluster["event_ids"]), ["k1", "k2"])
        self.assertEqual(cluster["source_diversity"], 2)

    def test_every_rising_trend_is_explainable_and_traceable(self):
        now = _now()
        events = [
            _ev(f"p{i}", "product_innovation", f"Insurer launches parametric product v{i}", days_ago=1, entities=["Insurer"], domains=["reuters.com"])
            for i in range(5)
        ]
        radar = build_radar(events)
        result = build_trend_intelligence({"events": events, "radar": radar}, now=now)
        rising = [t for t in result["topic_trends"] if t["direction"] == "rising"]
        self.assertTrue(rising)
        for trend in rising:
            why = trend["why"]
            for key in ("independent_events", "sources", "days", "core_entities", "event_ids"):
                self.assertIsNotNone(why.get(key), f"rising 缺少解释要素 {key}")
            self.assertTrue(trend["cluster_ids"])
        self.assertEqual(result["stats"]["rising_with_why"], len(rising))


if __name__ == "__main__":
    unittest.main()
