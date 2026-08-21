import unittest

from owner_risk_view import build_owner_view


class OwnerRiskViewTests(unittest.TestCase):
    def test_uses_execution_readiness_owner_deadline_and_next_step(self):
        radar = {
            "items": [{
                "event_id": "E1",
                "title": "Exposure event",
                "attention_score": 88,
                "urgency": "now",
                "trust_level": "medium",
                "reasons": ["urgent"],
                "source": "intelligence.json",
            }]
        }
        readiness = {
            "results": [{
                "event_id": "E1",
                "action_id": "exposure_mapping",
                "owner_roles": ["portfolio_risk_owner"],
                "deadline": "within_5_business_days",
                "deliverables": ["impact_map"],
                "approval_boundary": "analysis only; human review",
            }]
        }
        result = build_owner_view(radar, readiness)
        item = result["items"][0]
        self.assertEqual(item["owners"], ["portfolio_risk_owner"])
        self.assertEqual(item["deadline"], "within_5_business_days")
        self.assertIn("impact_map", item["next_step"])
        self.assertEqual(item["automation"], "advisory_only")

    def test_regression_backlog_gets_quality_review_step(self):
        radar = {
            "items": [{
                "event_id": "module:trust",
                "title": "模块质量：trust",
                "attention_score": 90,
                "reasons": ["optimization_backlog", "regressed"],
                "source": "optimization_backlog.json",
            }]
        }
        result = build_owner_view(radar, {"results": []})
        self.assertIn("regression", result["items"][0]["next_step"])
        self.assertEqual(result["items"][0]["owners"], ["risk_review_owner"])

    def test_limits_view_to_radar_cap(self):
        radar = {"items": [{"event_id": str(i), "attention_score": i} for i in range(50)]}
        result = build_owner_view(radar, {"results": []})
        self.assertEqual(result["item_count"], 50)
        self.assertEqual(len(result["items"]), 30)


if __name__ == "__main__":
    unittest.main()
