#!/usr/bin/env python3
import json
import tempfile
import unittest
from pathlib import Path

from release_manifest import _read_run_id, build_manifest


class TestRunIdResolution(unittest.TestCase):
    """run_id 取值不得依赖步骤顺序（atomic publish 先盖章、后写 run.json）。"""

    def test_run_json_wins_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "run.json").write_text(json.dumps({"run_id": "run_from_run_json"}), encoding="utf-8")
            (root / "intelligence.json").write_text(
                json.dumps({"_provenance": {"run_id": "run_from_artifact"}}), encoding="utf-8"
            )
            self.assertEqual(_read_run_id(root), "run_from_run_json")

    def test_falls_back_to_artifact_provenance(self):
        """run.json 尚未写入（restamp 早于 atomic publish）时，取产物盖章的 run_id。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "intelligence.json").write_text(
                json.dumps({"_provenance": {"run_id": "run_20261001_000729_70d044"}}), encoding="utf-8"
            )
            self.assertEqual(_read_run_id(root), "run_20261001_000729_70d044")

    def test_falls_back_across_artifact_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "claims.json").write_text(json.dumps({"x": 1}), encoding="utf-8")
            (root / "intelligence.json").write_text(
                json.dumps({"_provenance": {"run_id": "run_b"}}), encoding="utf-8"
            )
            self.assertEqual(_read_run_id(root), "run_b")

    def test_missing_everything_returns_none(self):
        """拿不到就老实给 None，不编造 id。"""
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(_read_run_id(Path(tmp)))

    def test_broken_run_json_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "run.json").write_text("{not json", encoding="utf-8")
            (root / "intelligence.json").write_text(
                json.dumps({"_provenance": {"run_id": "run_recovered"}}), encoding="utf-8"
            )
            self.assertEqual(_read_run_id(root), "run_recovered")


class TestReleaseManifest(unittest.TestCase):
    def test_quality_pass_does_not_claim_deployment(self):
        m = build_manifest(source_commit="abc123", site_url="https://example.test")
        self.assertEqual(m["quality_status"], "passed")
        self.assertEqual(m["deployment_status"], "pending")
        self.assertFalse(m["deployment_verified"])
        self.assertEqual(m["release_channel"], "cloudflare_workers")

    def test_release_channel_can_be_explicit(self):
        m = build_manifest(source_commit="abc123", site_url="https://example.test", release_channel="github_pages")
        self.assertEqual(m["release_channel"], "github_pages")

    def test_failed_quality_is_explicit(self):
        m = build_manifest(source_commit="abc123", site_url="https://example.test", quality_passed=False)
        self.assertEqual(m["quality_status"], "failed")
        self.assertFalse(m["deployment_verified"])


if __name__ == "__main__":
    unittest.main()
