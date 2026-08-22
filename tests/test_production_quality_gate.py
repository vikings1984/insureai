#!/usr/bin/env python3
import json
import tempfile
import unittest
from pathlib import Path

from production_quality_gate import REQUIRED_ARTIFACTS, run_gate


class TestProductionQualityGate(unittest.TestCase):
    def _write_fixture(self, root: Path, *, unsafe: bool = False, missing_article: bool = False, blocked: bool = False) -> None:
        news = [
            {"id": "a1", "published_at": "2026-08-22T08:00:00+00:00", "source_url": "https://example.com/a1"},
            {"id": "a2", "published_at": "2026-08-22T09:00:00+00:00", "source_url": "https://example.com/a2"},
        ]
        events = [
            {
                "event_id": "evt_1",
                "article_ids": ["a1"] if missing_article else ["a1", "a2"],
                "scores": {"intelligence_score": 90},
            }
        ]
        decision = {
            "event_id": "evt_1",
            "urgency": "now" if unsafe else "soon",
            "basis": {"trust_level": "low" if unsafe else "high", "conflict": unsafe},
            "guardrail": "advisory_only",
        }
        intelligence = {"version": 7, "events": events, "decisions": [decision]}
        credibility_status = "blocked" if blocked else "ready"
        for name, payload in {
            "data.json": {"news": news},
            "intelligence.json": intelligence,
            "decision_stability.json": {"version": 1, "results": []},
            "decision_credibility.json": {"version": 3, "status": credibility_status, "reasons": [{"code": "quality_not_passed"}] if blocked else []},
            "evidence_availability.json": {"version": 1, "results": []},
            "owner_risk_view.json": {"version": 2, "items": []},
        }.items():
            (root / name).write_text(json.dumps(payload), encoding="utf-8")

    def test_real_artifact_contract_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_fixture(root)
            result = run_gate(root)
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["failed_checks"], [])

    def test_missing_lineage_blocks_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_fixture(root, missing_article=True)
            result = run_gate(root)
            self.assertEqual(result["status"], "failed")
            self.assertIn("lineage", result["failed_checks"])

    def test_unsafe_now_blocks_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_fixture(root, unsafe=True)
            result = run_gate(root)
            self.assertEqual(result["status"], "failed")
            self.assertIn("decision_safety", result["failed_checks"])

    def test_blocked_credibility_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_fixture(root, blocked=True)
            result = run_gate(root)
            self.assertEqual(result["status"], "failed")
            self.assertIn("credibility_contract", result["failed_checks"])

    def test_required_artifacts_match_runtime_contract(self):
        self.assertNotIn("decision.json", REQUIRED_ARTIFACTS)
        self.assertIn("intelligence.json", REQUIRED_ARTIFACTS)


if __name__ == "__main__":
    unittest.main()
