import unittest
from optimization_backlog import build_backlog


class OptimizationBacklogLifecycleTests(unittest.TestCase):
    def _history(self, rates):
        return {"snapshots": [{"modules": {"trust": {"error_rate": rate}}} for rate in rates]}

    def test_new_issue_is_open(self):
        trend = {"baseline_available": True, "modules": {"trust": {"direction": "worsening", "health": "critical", "error_rate": 0.6, "error_rate_delta": 0.1, "priority": 60, "confidence": 0.9}}}
        out = build_backlog(trend, {})
        self.assertEqual(out["items"][0]["status"], "open")
        self.assertEqual(out["items"][0]["dedupe_key"], "quality:trust")

    def test_existing_active_issue_stays_open(self):
        trend = {"baseline_available": True, "modules": {"trust": {"direction": "worsening", "health": "critical", "error_rate": 0.6, "error_rate_delta": 0.1, "priority": 60, "confidence": 0.9}}}
        previous = {"items": [{"module": "trust", "dedupe_key": "quality:trust", "status": "open", "priority": 90}]}
        out = build_backlog(trend, previous)
        self.assertEqual(out["items"][0]["status"], "open")

    def test_improvement_without_persistence_stays_recovering(self):
        trend = {"baseline_available": True, "modules": {"trust": {"direction": "stable", "health": "healthy", "error_rate": 0.1, "error_rate_delta": -0.1, "priority": 5, "confidence": 0.9}}}
        previous = {"items": [{"module": "trust", "dedupe_key": "quality:trust", "status": "open", "priority": 90}]}
        out = build_backlog(trend, previous, self._history([0.4, 0.2]))
        self.assertEqual(out["items"][0]["status"], "recovering")
        self.assertEqual(out["items"][0]["verification"]["status"], "unavailable")

    def test_resolved_issue_is_retained_as_resolved_after_verified_fix(self):
        trend = {"baseline_available": True, "modules": {"trust": {"direction": "stable", "health": "healthy", "error_rate": 0.1, "error_rate_delta": -0.1, "priority": 5, "confidence": 0.9}}}
        previous = {"items": [{"module": "trust", "dedupe_key": "quality:trust", "status": "open", "priority": 90}]}
        out = build_backlog(trend, previous, self._history([0.4, 0.1, 0.08]))
        self.assertEqual(out["items"][0]["status"], "resolved")
        self.assertEqual(out["items"][0]["verification"]["status"], "verified")

    def test_resolved_issue_reopens_as_regressed(self):
        trend = {"baseline_available": True, "modules": {"trust": {"direction": "worsening", "health": "watch", "error_rate": 0.3, "error_rate_delta": 0.1, "priority": 30, "confidence": 0.9}}}
        previous = {"items": [{"module": "trust", "dedupe_key": "quality:trust", "status": "resolved", "priority": 10}]}
        out = build_backlog(trend, previous)
        self.assertEqual(out["items"][0]["status"], "regressed")

    def test_lifecycle_does_not_change_decision_payload(self):
        trend = {"baseline_available": True, "modules": {"decision": {"direction": "stable", "health": "healthy", "error_rate": 0.1, "priority": 5}}}
        out = build_backlog(trend, {})
        self.assertIn("items", out)
        self.assertNotIn("urgency", out)


if __name__ == "__main__":
    unittest.main()
