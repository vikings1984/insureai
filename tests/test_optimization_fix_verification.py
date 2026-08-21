import unittest
from optimization_fix_verification import verify_fix


class OptimizationFixVerificationTests(unittest.TestCase):
    def test_insufficient_history_is_not_verified(self):
        history = {"snapshots": [{"modules": {"trust": {"error_rate": 0.4}}}]}
        result = verify_fix("trust", history)
        self.assertEqual(result["status"], "unavailable")

    def test_persistent_improvement_is_verified(self):
        history = {
            "snapshots": [
                {"modules": {"trust": {"error_rate": 0.4}}},
                {"modules": {"trust": {"error_rate": 0.1}}},
                {"modules": {"trust": {"error_rate": 0.08}}},
            ]
        }
        result = verify_fix("trust", history)
        self.assertEqual(result["status"], "verified")
        self.assertTrue(result["persisted"])
        self.assertGreaterEqual(result["improvement"], 0.05)

    def test_last_snapshot_regression_is_detected(self):
        history = {
            "snapshots": [
                {"modules": {"trust": {"error_rate": 0.4}}},
                {"modules": {"trust": {"error_rate": 0.08}}},
                {"modules": {"trust": {"error_rate": 0.2}}},
            ]
        }
        result = verify_fix("trust", history)
        self.assertEqual(result["status"], "regressed")


if __name__ == "__main__":
    unittest.main()
