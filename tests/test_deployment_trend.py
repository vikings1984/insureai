#!/usr/bin/env python3
import unittest
from deployment_trend import attribute_deployment_trend


class TestDeploymentTrend(unittest.TestCase):
    def test_single_failure(self):
        result = attribute_deployment_trend([{"verified": False}])
        self.assertEqual(result["classification"], "single_failure")
        self.assertEqual(result["failure_streak"], 1)

    def test_persistent_failure(self):
        result = attribute_deployment_trend([{"verified": True}, {"verified": False}, {"verified": False}])
        self.assertEqual(result["classification"], "persistent_failure")
        self.assertEqual(result["failure_streak"], 2)

    def test_recovered(self):
        result = attribute_deployment_trend([{"verified": False}, {"verified": True}])
        self.assertEqual(result["classification"], "recovered")
        self.assertEqual(result["failure_streak"], 0)


if __name__ == "__main__":
    unittest.main()
