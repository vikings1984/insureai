#!/usr/bin/env python3
import unittest
from pathlib import Path
import tempfile
import json

import decision_credibility


class TestCredibilityProvenance(unittest.TestCase):
    def test_summary_contains_source_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixtures = {
                "release_manifest.json": {"quality_status": "passed", "deployment_status": "pending", "deployment_verified": False, "source_commit": "abc"},
                "decision_stability.json": {"results": [{"event_id": "e1", "status": "jitter"}]},
                "evidence_availability.json": {"results": [{"availability": "low"}]},
                "evaluation_metrics.json": {"macro_quality": 1.0},
            }
            for name, value in fixtures.items():
                (root / name).write_text(json.dumps(value), encoding="utf-8")
            original = decision_credibility.ROOT
            decision_credibility.ROOT = root
            try:
                result = decision_credibility.build_credibility()
            finally:
                decision_credibility.ROOT = original
            self.assertEqual(result["status"], "review")
            self.assertIn("provenance", result)
            self.assertEqual(result["provenance"]["quality"]["source"], "release_manifest.json")
            self.assertEqual(result["provenance"]["stability"]["source"], "decision_stability.json")
            self.assertEqual(result["provenance"]["evidence"]["source"], "evidence_availability.json")
            self.assertEqual(result["provenance"]["quality"]["source_commit"], "abc")
            self.assertTrue(result["provenance"]["generated_at"])


if __name__ == "__main__":
    unittest.main()
