#!/usr/bin/env python3
import unittest
from deployment_risk import build_deployment_risk

class TestDeploymentRisk(unittest.TestCase):
    def test_unverified_is_attention_signal(self):
        result = build_deployment_risk({"status": "pending", "verified": False})
        self.assertEqual(result["classification"], "deployment_unverified")
        self.assertTrue(result["attention"])
        self.assertEqual(result["priority"], 70)

    def test_failed_is_higher_attention_signal(self):
        result = build_deployment_risk({"status": "failed", "verified": False, "error": "request_failed"})
        self.assertEqual(result["classification"], "deployment_failed")
        self.assertTrue(result["attention"])
        self.assertEqual(result["priority"], 90)

    def test_verified_is_not_attention_signal(self):
        result = build_deployment_risk({"status": "verified", "verified": True})
        self.assertEqual(result["classification"], "deployment_verified")
        self.assertFalse(result["attention"])
        self.assertEqual(result["priority"], 0)

if __name__ == "__main__":
    unittest.main()
