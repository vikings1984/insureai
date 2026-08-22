#!/usr/bin/env python3
import unittest
from deployment_risk import build_deployment_risk


class TestDeploymentRisk(unittest.TestCase):
    def test_unconfigured_is_configuration_debt_signal(self):
        result = build_deployment_risk({"status": "unconfigured", "verified": False, "error": "site_url_missing"})
        self.assertEqual(result["classification"], "deployment_configuration_missing")
        self.assertTrue(result["attention"])
        self.assertEqual(result["priority"], 40)
        self.assertIn("DEPLOYMENT_URL", result["next_step"])

    def test_unknown_is_verification_missing_signal(self):
        result = build_deployment_risk({"status": "unknown", "verified": False})
        self.assertEqual(result["classification"], "deployment_verification_missing")
        self.assertTrue(result["attention"])
        self.assertEqual(result["priority"], 50)
        self.assertIn("Deployment Verification", result["next_step"])

    def test_unverified_is_attention_signal(self):
        result = build_deployment_risk({"status": "pending", "verified": False})
        self.assertEqual(result["classification"], "deployment_unverified")
        self.assertTrue(result["attention"])
        self.assertEqual(result["priority"], 70)
        self.assertTrue(result["next_step"])

    def test_failed_is_higher_attention_signal(self):
        result = build_deployment_risk({"status": "failed", "verified": False, "error": "request_failed"})
        self.assertEqual(result["classification"], "deployment_failed")
        self.assertTrue(result["attention"])
        self.assertEqual(result["priority"], 90)
        self.assertIn("部署", result["next_step"])

    def test_persistent_failure_gets_higher_priority(self):
        result = build_deployment_risk({"status": "failed", "verified": False, "error": "request_failed"}, [{"verified": False}, {"verified": False}])
        self.assertEqual(result["classification"], "deployment_persistent_failure")
        self.assertEqual(result["priority"], 95)
        self.assertTrue(result["next_step"])

    def test_stale_release_is_highest_advisory_risk(self):
        result = build_deployment_risk({
            "status": "stale",
            "verified": False,
            "release_match": False,
        })
        self.assertEqual(result["classification"], "deployment_release_mismatch")
        self.assertEqual(result["priority"], 98)
        self.assertTrue(result["attention"])
        self.assertIn("release marker", result["next_step"])

    def test_release_match_false_is_risk_even_without_stale_status(self):
        result = build_deployment_risk({
            "status": "pending",
            "verified": False,
            "release_match": False,
        })
        self.assertEqual(result["classification"], "deployment_release_mismatch")
        self.assertEqual(result["priority"], 98)
        self.assertTrue(result["attention"])

    def test_verified_is_not_attention_signal(self):
        result = build_deployment_risk({"status": "verified", "verified": True})
        self.assertEqual(result["classification"], "deployment_verified")
        self.assertFalse(result["attention"])
        self.assertEqual(result["priority"], 0)
        self.assertIsNone(result["next_step"])


if __name__ == "__main__":
    unittest.main()
