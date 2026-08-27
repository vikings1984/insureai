#!/usr/bin/env python3
import json
import tempfile
import unittest
from pathlib import Path

import knowledge_graph


class KnowledgeGraphTests(unittest.TestCase):
    def test_links_event_claim_evidence_with_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "intelligence.json").write_text(json.dumps({
                "events": [{
                    "event_id": "e1",
                    "title": "Munich Re 收购 At-Bay",
                    "topic": "capital_reinsurance",
                    "article_ids": ["a1"],
                    "trust": {"level": "high"},
                    "evidence_status": "cross_checked",
                    "source_count": 2,
                    "evidence": [{"source_name": "Reuters", "source_url": "https://reuters.example/a1", "domain": "reuters.example"}],
                }]
            }), encoding="utf-8")
            (root / "claims.json").write_text(json.dumps({
                "events": [{"event_id": "e1", "claims": [{
                    "claim_id": "e1/c1", "claim_type": "transaction_amount",
                    "claim_text": "交易金额为 $575 million", "verification_status": "cross_checked",
                    "confidence": 89, "independent_domains": 2, "subject": "Munich Re", "object": "At-Bay",
                    "value": {"raw": "$575 million", "normalized": 575000000.0},
                    "supporting_evidence": [{"evidence_id": "a1", "source_name": "Reuters", "source_url": "https://reuters.example/a1", "domain": "reuters.example", "source_tier": 2}],
                    "contradicting_evidence": [{"evidence_id": "a2", "source_name": "Rival Post", "source_url": "https://rival.example/a2", "domain": "rival.example", "source_tier": 3}],
                    "evidence_refs": ["a1"],
                }]}]
            }), encoding="utf-8")
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

        self.assertGreaterEqual(result["stats"]["node_count"], 5)
        relationships = {(e["relationship"], e["source"], e["target"]) for e in result["edges"]}
        self.assertTrue(any(e["relationship"] == "INVOLVES" for e in result["edges"]))
        self.assertTrue(any(e["relationship"] == "SUPPORTS" for e in result["edges"]))
        self.assertTrue(any(e["relationship"] == "CONTRADICTS" for e in result["edges"]))
        self.assertTrue(all(0 <= e["confidence"] <= 1 for e in result["edges"]))


if __name__ == "__main__":
    unittest.main()
