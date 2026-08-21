import unittest
from evidence_availability import build_availability


class EvidenceAvailabilityTests(unittest.TestCase):
    def test_unavailable_is_not_quality(self):
        out = build_availability({"status": "unavailable", "date_coverage": 0.0})
        self.assertEqual(out["level"], "unavailable")

    def test_stale_is_low(self):
        out = build_availability({"status": "ok", "date_coverage": 1.0, "stale": True})
        self.assertEqual(out["level"], "low")

    def test_partial_coverage_is_medium(self):
        out = build_availability({"status": "ok", "date_coverage": 0.7, "stale": False})
        self.assertEqual(out["level"], "medium")

    def test_good_coverage_is_high(self):
        out = build_availability({"status": "ok", "date_coverage": 1.0, "stale": False})
        self.assertEqual(out["level"], "high")

    def test_does_not_create_decision_fields(self):
        out = build_availability({"status": "ok", "date_coverage": 1.0, "stale": False})
        self.assertNotIn("urgency", out)
        self.assertNotIn("action", out)


if __name__ == "__main__":
    unittest.main()
