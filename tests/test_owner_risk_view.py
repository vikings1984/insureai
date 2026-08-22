import unittest

from owner_risk_view import build_owner_view


class OwnerRiskViewTests(unittest.TestCase):
    def test_uses_execution_readiness_owner_deadline_and_next_step(self):
        radar = {"items": [{"event_id": "E1", "title": "Exposure event", "attention_score": 88, "urgency": "now", "trust_level": "medium", "reasons": ["urgent"], "source": "intelligence.json"}]}
        readiness = {"results": [{"event_id": "E1", "action_id": "exposure_mapping", "owner_roles": ["portfolio_risk_owner"], "deadline": "within_5_business_days", "deliverables": ["impact_map"], "approval_boundary": "analysis only; human review"}]}
        result = build_owner_view(radar, readiness)
        item = result["items"][0]
        self.assertEqual(item["owners"], ["portfolio_risk_owner"])
        self.assertEqual(item["deadline"], "within_5_business_days")
        self.assertIn("impact_map", item["next_step"])
        self.assertEqual(item["automation"], "advisory_only")

    def test_regression_backlog_gets_quality_review_step(self):
        radar = {"items": [{"event_id": "module:trust", "title": "模块质量：trust", "attention_score": 90, "reasons": ["optimization_backlog", "regressed"], "source": "optimization_backlog.json"}]}
        result = build_owner_view(radar, {"results": []})
        self.assertIn("regression", result["items"][0]["next_step"])
        self.assertEqual(result["items"][0]["owners"], ["risk_review_owner"])

    def test_limits_view_to_radar_cap(self):
        radar = {"items": [{"event_id": str(i), "attention_score": i} for i in range(50)]}
        result = build_owner_view(radar, {"results": []})
        self.assertEqual(result["item_count"], 50)
        self.assertEqual(len(result["items"]), 30)

    def test_embeds_credibility_status_reasons_and_provenance(self):
        credibility = {"status": "review", "reasons": ["decision_jitter_detected"], "provenance": {"decision_stability": {"sha256": "abc", "producer": "decision_stability.py"}}}
        result = build_owner_view({"items": []}, {"results": []}, credibility)
        self.assertEqual(result["version"], 2)
        self.assertEqual(result["credibility"]["status"], "review")
        self.assertIn("decision_jitter_detected", result["credibility"]["reasons"])
        self.assertEqual(result["credibility"]["provenance"]["decision_stability"]["producer"], "decision_stability.py")

    def test_deployment_configuration_debt_has_platform_owners(self):
        radar = {"items": [{"event_id": "deployment:github_pages", "title": "生产部署状态：deployment_configuration_missing", "attention_score": 40, "urgency": "soon", "reasons": ["deployment_configuration_missing", "site_url_missing"], "source": "deployment_verification.json"}]}
        result = build_owner_view(radar, {"results": []})
        self.assertEqual(result["configuration_debt_count"], 1)
        self.assertEqual(result["items"], [])
        debt = result["configuration_debt"][0]
        self.assertEqual(debt["owners"], ["platform_owner", "release_owner"])
        self.assertIn("configure DEPLOYMENT_URL", debt["next_step"])
        self.assertEqual(debt["automation"], "advisory_only")


if __name__ == "__main__":
    unittest.main()
