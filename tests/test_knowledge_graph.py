#!/usr/bin/env python3
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import knowledge_graph
from contract import ARTIFACT_VERSIONS
from kg_query import entity_recent, topic_crossover


def _fixture() -> tuple[dict, dict]:
    now = datetime(2026, 8, 27, tzinfo=timezone.utc)
    iso = "%Y-%m-%dT%H:%M:%SZ"
    return {
        "events": [{
            "event_id": "e1",
            "title": "Munich Re 收购 At-Bay",
            "topic": "capital_reinsurance",
            "published_at": now.strftime(iso),
            "article_ids": ["a1"],
            "trust": {"level": "high"},
            "evidence_status": "cross_checked",
            "source_count": 2,
            "evidence": [{"source_name": "Reuters", "source_url": "https://reuters.example/a1", "domain": "reuters.example"}],
        }, {
            "event_id": "e2",
            "title": "Munich Re 发布 AI 核保引擎",
            "topic": "ai_intelligent",
            "published_at": (now - timedelta(days=30)).strftime(iso),
            "article_ids": ["a2"],
            "trust": {"level": "high"},
            "evidence_status": "single_source",
            "source_count": 1,
            "evidence": [],
        }]
    }, {
        "events": [{"event_id": "e1", "claims": [{
            "claim_id": "e1/c1", "claim_type": "transaction_amount",
            "claim_text": "交易金额为 $575 million", "verification_status": "cross_checked",
            "confidence": 89, "independent_domains": 2, "subject": "Munich Re", "object": "At-Bay",
            "value": {"raw": "$575 million", "normalized": 575000000.0},
            "supporting_evidence": [{"evidence_id": "a1", "source_name": "Reuters", "source_url": "https://reuters.example/a1", "domain": "reuters.example", "source_tier": 2}],
            "contradicting_evidence": [{"evidence_id": "a2", "source_name": "Rival Post", "source_url": "https://rival.example/a2", "domain": "rival.example", "source_tier": 3}],
            "evidence_refs": ["a1"],
        }]}]
    }


class KnowledgeGraphTests(unittest.TestCase):
    def _build(self):
        intelligence, claims = _fixture()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "intelligence.json").write_text(json.dumps(intelligence), encoding="utf-8")
            (root / "claims.json").write_text(json.dumps(claims), encoding="utf-8")
            old = knowledge_graph.ROOT
            knowledge_graph.ROOT = root
            knowledge_graph.INTELLIGENCE = root / "intelligence.json"
            knowledge_graph.CLAIMS = root / "claims.json"
            knowledge_graph.OUTPUT = root / "knowledge_graph.json"
            try:
                result = knowledge_graph.build()
            finally:
                knowledge_graph.ROOT = old
                knowledge_graph.INTELLIGENCE = old / "intelligence.json"
                knowledge_graph.CLAIMS = old / "claims.json"
                knowledge_graph.OUTPUT = old / "knowledge_graph.json"
        return result

    def test_links_event_claim_evidence_with_provenance(self):
        result = self._build()
        self.assertGreaterEqual(result["stats"]["node_count"], 5)
        relationships = {(e["relationship"], e["source"], e["target"]) for e in result["edges"]}
        self.assertTrue(any(e["relationship"] == "INVOLVES" for e in result["edges"]))
        self.assertTrue(any(e["relationship"] == "SUPPORTS" for e in result["edges"]))
        self.assertTrue(any(e["relationship"] == "CONTRADICTS" for e in result["edges"]))
        self.assertTrue(all(0 <= e["confidence"] <= 1 for e in result["edges"]))

    def test_event_nodes_carry_timestamp_and_stats_v3(self):
        result = self._build()
        self.assertEqual(result["version"], ARTIFACT_VERSIONS["knowledge_graph.json"])
        events = [n for n in result["nodes"] if n["type"] == "Event"]
        self.assertEqual({n.get("published_at") for n in events}, {
            "2026-08-27T00:00:00Z", "2026-07-28T00:00:00Z",
        })
        self.assertEqual(result["stats"]["node_types"]["Event"], 2)
        self.assertEqual(result["stats"]["latest_event_at"], "2026-08-27T00:00:00Z")
        self.assertEqual(sum(result["stats"]["node_types"].values()), result["stats"]["node_count"])

    def test_build_feeds_preset_queries(self):
        result = self._build()
        recent = entity_recent(result, "Munich Re", days=90)
        # fixture 两个事件都在 90 天窗口内，且 e1 附带 1 条 claim。
        self.assertEqual(len(recent["events"]), 2)
        self.assertEqual([c["claim_id"] for c in recent["claims"]], ["e1/c1"])
        crossover = topic_crossover(result, ["capital_reinsurance", "ai_intelligent"])
        self.assertIn("Munich Re", [x["entity"] for x in crossover["entities"]])


class EntityExtractionNoiseTests(unittest.TestCase):
    """E1：KG 实体抽取噪声治理 — 过滤句首状语片段、剥离中文前缀、限制长度。"""

    def test_filters_sentence_initial_adverbial_fragments(self):
        out = knowledge_graph.entities("According to sources, Munich Re 收购 At-Bay")
        self.assertNotIn("According", out)
        self.assertNotIn("Sources", out)
        self.assertIn("Munich Re", out)
        self.assertIn("At-Bay", out)

    def test_keeps_mid_sentence_function_word_org(self):
        # 句中出现的 "The Hartford" 不应被句首规则误杀
        out = knowledge_graph.entities("瑞士再保险宣布 The Hartford 加入再保联盟")
        self.assertIn("The Hartford", out)

    def test_strips_cn_adverbial_prefix(self):
        out = knowledge_graph.entities("随着再保险公司寻求与本地险企合作")
        self.assertIn("再保险公司", out)
        self.assertNotIn("随着再保险公司", out)

    def test_drops_overlong_capitalized_fragment(self):
        long = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz Insurance"
        self.assertNotIn(long, knowledge_graph.entities(long))

    def test_caps_to_twelve(self):
        text = " ".join(f"Company{i} Group" for i in range(20))
        self.assertLessEqual(len(knowledge_graph.entities(text)), 12)

    def test_clean_cn_entity_rejects_after_strip(self):
        # 纯状语前缀 + 非机构词，剥离后不构成机构名
        self.assertIsNone(knowledge_graph._clean_cn_entity("随着市场"))
        self.assertEqual(knowledge_graph._clean_cn_entity("在工商银行"), "工商银行")

    def test_clean_cn_entity_splits_clause_fragment(self):
        # 句中动词粒子切分：保留机构尾片，去掉从句与动词
        self.assertEqual(knowledge_graph._clean_cn_entity("摩根大通表示再保险"), "再保险")
        self.assertEqual(knowledge_graph._clean_cn_entity("将收购保险服务公司"), "保险服务公司")
        # 真实机构名（慕尼黑再保险）不含动词粒子，原样保留
        self.assertEqual(knowledge_graph._clean_cn_entity("慕尼黑再保险公司"), "慕尼黑再保险公司")


if __name__ == "__main__":
    unittest.main()

