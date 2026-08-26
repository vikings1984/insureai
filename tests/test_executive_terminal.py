#!/usr/bin/env python3
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import executive_terminal


class ExecutiveTerminalTests(unittest.TestCase):
    def test_builds_from_existing_artifacts_without_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "intelligence.json").write_text(json.dumps({
                "events": [
                    {"event_id": "e1", "topic": "AI保险", "importance": 90, "evidence_coverage": 100, "trust": 82, "review_required": False, "insight": "关注"}
                ],
                "radar": {"topic_trends": [{"topic": "AI保险", "direction": "rising", "signal_strength": 88}]},
            }), encoding="utf-8")
            (root / "claims.json").write_text(json.dumps({"cross_checked_claim_count": 2, "single_source_claim_count": 1}), encoding="utf-8")
            (root / "review_queue.json").write_text(json.dumps({"items": [{"title": "监管事项", "reason": "需要人工判断"}]}), encoding="utf-8")
            (root / "daily_risk_radar.json").write_text(json.dumps({"items": [{"title": "数据新鲜度", "reason": "需关注"}]}), encoding="utf-8")
            (root / "decision_credibility.json").write_text(json.dumps({"status": "review"}), encoding="utf-8")
            (root / "deployment_verification.json").write_text(json.dumps({"status": "verified", "verified": True, "release_marker": "insureai-x", "marker_found": True}), encoding="utf-8")
            old_root, old_output = executive_terminal.ROOT, executive_terminal.OUTPUT
            executive_terminal.ROOT = root
            executive_terminal.OUTPUT = root / "executive_terminal.json"
            try:
                with patch.dict(os.environ, {"GITHUB_SHA": "abc123"}, clear=False):
                    executive_terminal.main()
                output = json.loads((root / "executive_terminal.json").read_text(encoding="utf-8"))
            finally:
                executive_terminal.ROOT, executive_terminal.OUTPUT = old_root, old_output
        self.assertEqual(output["source_commit"], "abc123")
        self.assertEqual(output["summary"]["event_count"], 1)
        self.assertEqual(output["summary"]["cross_checked_claims"], 2)
        self.assertEqual(output["summary"]["deployment_status"], "verified")
        self.assertEqual(len(output["what_is_accelerating"]), 1)

    def test_does_not_require_release_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "intelligence.json").write_text(json.dumps({"events": [], "radar": {"topic_trends": []}}), encoding="utf-8")
            old_root, old_output = executive_terminal.ROOT, executive_terminal.OUTPUT
            executive_terminal.ROOT = root
            executive_terminal.OUTPUT = root / "executive_terminal.json"
            try:
                with patch.dict(os.environ, {"GITHUB_SHA": "def456"}, clear=False):
                    executive_terminal.main()
                output = json.loads((root / "executive_terminal.json").read_text(encoding="utf-8"))
            finally:
                executive_terminal.ROOT, executive_terminal.OUTPUT = old_root, old_output
        self.assertEqual(output["source_commit"], "def456")
        self.assertEqual(output["summary"]["deployment_status"], "unknown")


if __name__ == "__main__":
    unittest.main()
