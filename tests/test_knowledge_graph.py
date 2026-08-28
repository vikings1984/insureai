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


if __name__ == "__main__":
    unittest.main()

