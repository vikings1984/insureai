import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import audit_ledger


class AuditLedgerTests(unittest.TestCase):
    def test_ledger_has_hashes_and_no_content_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data.json").write_text(json.dumps({"news": [{"title": "secret title", "url": "https://example.com", "body": "private"}]}), encoding="utf-8")
            with patch.object(audit_ledger, "ROOT", root):
                ledger = audit_ledger.build_ledger()
        row = ledger["stages"][0]
        self.assertEqual(len(row["sha256"]), 64)
        self.assertNotIn("title", row)
        self.assertNotIn("url", row)
        self.assertNotIn("body", row)
        self.assertEqual(ledger["privacy"], "hashes_and_metadata_only")

    def test_empty_or_invalid_artifact_is_skipped_without_content_leak(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data.json").write_text("not-json", encoding="utf-8")
            with patch.object(audit_ledger, "ROOT", root):
                ledger = audit_ledger.build_ledger()
        self.assertEqual(ledger["stages"][0]["counts"], {})
        self.assertEqual(len(ledger["stages"][0]["sha256"]), 64)

    def test_ledger_covers_downstream_quality_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for filename in (
                "data.json", "intelligence.json", "decision_stability.json", "decision_credibility.json",
                "counterfactual.json", "scenario.json", "scenario_matrix.json", "action_triggers.json",
                "execution_readiness.json", "change_impact.json", "freshness.json", "evidence_availability.json",
                "review_queue.json", "feedback_attribution.json", "module_health.json", "module_health_history.json",
                "module_health_trend.json", "trend_attribution.json", "optimization_backlog.json",
                "optimization_backlog_history.json", "daily_risk_radar.json", "owner_risk_view.json",
            ):
                (root / filename).write_text(json.dumps({"version": 1}), encoding="utf-8")
            with patch.object(audit_ledger, "ROOT", root):
                ledger = audit_ledger.build_ledger()
        names = {row["artifact"] for row in ledger["stages"]}
        self.assertIn("trend_attribution.json", names)
        self.assertIn("optimization_backlog.json", names)
        self.assertIn("daily_risk_radar.json", names)
        self.assertIn("owner_risk_view.json", names)
        self.assertIn("decision_credibility.json", names)
        self.assertEqual(ledger["coverage_principle"], "ledger is generated after all analytical quality artifacts; release_manifest carries the production gate result")


if __name__ == "__main__":
    unittest.main()
