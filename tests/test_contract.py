import unittest

from contract import attach_contract, validate


def event():
    return {
        "event_id": "evt_1", "title": "示例事件", "event_type": "regulatory",
        "entities": ["example"], "topic": "regulatory_change", "published_at": "2026-08-21T00:00:00Z",
        "source_count": 2, "article_count": 2, "article_ids": [1, 2],
        "scores": {"relevance": 80, "impact": 75, "novelty": 90, "actionability": 70, "confidence": 88, "intelligence_score": 80},
        "insight": {"evidence": []}, "trust": {"level": "high"}, "claims": {"claims": []},
    }


class ContractTests(unittest.TestCase):
    def base(self):
        return {
            "version": 7,
            "events": [event()],
            "temporal": {"topic_signals": [], "entity_momentum": []},
            "decisions": [{"event_id": "evt_1", "urgency": "soon", "guardrail": "仅供辅助决策"}],
            "trust_stats": {}, "claim_stats": {}, "radar": {},
        }

    def test_valid_contract_attaches_metadata(self):
        data = attach_contract(self.base())
        self.assertEqual(data["data_contract"]["schema_version"], 1)
        self.assertEqual(data["data_contract"]["counts"]["events"], 1)
        self.assertEqual(len(data["data_contract"]["components"]["events"]), 16)

    def test_duplicate_event_ids_fail(self):
        data = self.base()
        data["events"].append(dict(event()))
        errors = validate(data)
        self.assertTrue(any("duplicate" in x for x in errors))

    def test_invalid_decision_urgency_fails(self):
        data = self.base()
        data["decisions"][0]["urgency"] = "later"
        errors = validate(data)
        self.assertTrue(any("urgency" in x for x in errors))


if __name__ == "__main__":
    unittest.main()
