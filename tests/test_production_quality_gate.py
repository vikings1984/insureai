#!/usr/bin/env python3
import json
import tempfile
import unittest
from pathlib import Path

from decision import ROLE_ACTIONS
from production_quality_gate import REQUIRED_ARTIFACTS, run_gate


def _context():
    return {
        "business_impact": {"compliance": 90},
        "affected_functions": [{"function": "compliance", "label": "合规", "impact": 90}],
        "potential_opportunity": ["合规能力先行带来的信誉与准入优势"],
        "potential_risk": ["合规成本上升与业务节奏受限"],
        "what_to_monitor": "跟踪后续监管文件与实施时间表",
        "recommended_next_step": "列入近期计划：检查监管暴露与经营影响",
    }


class TestProductionQualityGate(unittest.TestCase):
    def _write_fixture(self, root: Path, *, unsafe: bool = False, missing_article: bool = False, blocked: bool = False, drop_role: str | None = None, strip_context: bool = False) -> None:
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
            "context": _context(),
        }
        if strip_context:
            decision["context"] = {"business_impact": {}, "affected_functions": [], "potential_opportunity": [], "potential_risk": [], "what_to_monitor": "", "recommended_next_step": ""}
        by_role = {role: [dict(decision, role=role)] for role in ROLE_ACTIONS}
        if drop_role:
            by_role.pop(drop_role)
        intelligence = {"version": 8, "events": events, "decisions": [decision], "decisions_by_role": by_role}
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

    def test_missing_role_blocks_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_fixture(root, drop_role="underwriting")
            result = run_gate(root)
            self.assertEqual(result["status"], "failed")
            self.assertIn("decision_safety", result["failed_checks"])

    def test_missing_decision_context_blocks_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_fixture(root, strip_context=True)
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
