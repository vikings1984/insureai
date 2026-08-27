import unittest

from contract import EXPECTED_VERSION, attach_contract, validate
from decision import ROLE_ACTIONS, build_decisions


def event():
    return {
        "event_id": "evt_1", "title": "示例事件", "event_type": "regulatory",
        "entities": ["example"], "topic": "regulatory_change", "published_at": "2026-08-21T00:00:00Z",
        "source_count": 2, "article_count": 2, "article_ids": [1, 2],
        "scores": {"relevance": 80, "impact": 75, "novelty": 90, "actionability": 70, "confidence": 88, "intelligence_score": 80},
        "insight": {"evidence": [], "what_to_watch": "跟踪后续监管文件与实施时间表"}, "trust": {"level": "high"}, "claims": {"claims": []},
    }


def decisions_by_role():
    row = event()
    temporal = {"topic_signals": [], "entity_momentum": []}
    return {role: build_decisions([row], temporal, role)[:1] for role in ROLE_ACTIONS}


class ContractTests(unittest.TestCase):
    def base(self):
        by_role = decisions_by_role()
        return {
            "version": EXPECTED_VERSION,
            "events": [event()],
            "temporal": {"topic_signals": [], "entity_momentum": []},
            "decisions": by_role["executive"],
            "decisions_by_role": by_role,
            "trust_stats": {}, "claim_stats": {}, "radar": {},
        }

    def test_valid_contract_attaches_metadata(self):
        data = attach_contract(self.base())
        self.assertEqual(data["data_contract"]["schema_version"], 1)
        self.assertEqual(data["data_contract"]["counts"]["events"], 1)
        self.assertEqual(data["data_contract"]["counts"]["decision_roles"], len(ROLE_ACTIONS))
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

    def test_missing_decisions_by_role_fails(self):
        data = self.base()
        data.pop("decisions_by_role")
        errors = validate(data)
        self.assertTrue(any("decisions_by_role" in x for x in errors))

    def test_unknown_role_fails(self):
        data = self.base()
        data["decisions_by_role"]["board"] = data["decisions"]
        errors = validate(data)
        self.assertTrue(any("unknown role" in x for x in errors))

    def test_missing_decision_context_fails(self):
        data = self.base()
        data["decisions"][0]["context"].pop("what_to_monitor")
        errors = validate(data)
        self.assertTrue(any("missing context: what_to_monitor" in x for x in errors))

    def test_unsupported_version_fails(self):
        data = self.base()
        data["version"] = EXPECTED_VERSION - 1
        errors = validate(data)
        self.assertTrue(any("unsupported intelligence version" in x for x in errors))


if __name__ == "__main__":
    unittest.main()
