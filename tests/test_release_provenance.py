#!/usr/bin/env python3
import json
import tempfile
import unittest
from pathlib import Path

from release_provenance import attach_deployment_verification, build_provenance


class TestReleaseProvenance(unittest.TestCase):
    def _root(self):
        root = Path(tempfile.mkdtemp())
        (root / "release_manifest.json").write_text(json.dumps({
            "version": 1,
            "source_commit": "manifest-sha",
            "release_channel": "github_pages",
            "site_url": "https://example.test",
            "release_marker": "insureai-release-new",
            "quality_status": "passed",
            "deployment_status": "pending",
            "deployment_verified": False,
        }), encoding="utf-8")
        (root / "audit_ledger.json").write_text(json.dumps({
            "version": 1,
            "privacy": "hashes_and_metadata_only",
            "stages": [
                {"artifact": "data.json", "sha256": "a" * 64},
                {"artifact": "decision_credibility.json", "sha256": "b" * 64},
            ],
        }), encoding="utf-8")
        (root / "change_impact.json").write_text(json.dumps({
            "version": 1,
            "baseline_available": True,
            "impacted_count": 3,
        }), encoding="utf-8")
        return root

    def test_aggregates_release_audit_and_impact_without_content(self):
        root = self._root()
        provenance = build_provenance(source_commit="commit-123", site_url="https://example.test", root=root)
        self.assertEqual(provenance["version"], 1)
        self.assertEqual(provenance["schema_version"], "release-provenance-v1")
        self.assertEqual(provenance["source_commit"], "commit-123")
        self.assertEqual(provenance["release_marker"], "insureai-release-new")
        self.assertEqual(provenance["quality"]["audit_stage_count"], 2)
        self.assertEqual(provenance["quality"]["audit_artifact_count"], 2)
        self.assertTrue(provenance["impact"]["baseline_available"])
        self.assertEqual(provenance["impact"]["impacted_count"], 3)
        self.assertEqual(provenance["deployment"]["status"], "pending")
        self.assertFalse(provenance["deployment"]["verified"])
        self.assertFalse(provenance["deployment"]["release_match"])
        self.assertIsNone(provenance["deployment"]["final_url"])
        self.assertIsNone(provenance["deployment"]["content_type"])
        self.assertEqual(provenance["deployment"]["trend"]["classification"], "baseline")
        self.assertIsNone(provenance["artifacts"]["deployment_verification_sha256"])
        self.assertIsNone(provenance["artifacts"]["deployment_history_sha256"])
        self.assertEqual(len(provenance["artifacts"]["release_manifest_sha256"]), 64)
        self.assertEqual(len(provenance["artifacts"]["audit_ledger_sha256"]), 64)
        self.assertNotIn("title", provenance)
        self.assertNotIn("url", provenance)
        self.assertNotIn("body", provenance)

    def test_attaches_verified_deployment_without_changing_source_commit(self):
        root = self._root()
        (root / "release_provenance.json").write_text(json.dumps(build_provenance(
            source_commit="commit-123", site_url="https://example.test", root=root
        )), encoding="utf-8")
        (root / "deployment_verification.json").write_text(json.dumps({
            "version": 1,
            "status": "verified",
            "verified": True,
            "site_url": "https://example.test",
            "final_url": "https://example.test/",
            "content_type": "text/html",
            "expected_marker": "InsureAI",
            "release_marker": "insureai-release-new",
            "http_status": 200,
            "content_length": 123,
            "marker_found": True,
            "error": None,
            "checked_at": "2026-08-22T00:00:00+00:00",
        }), encoding="utf-8")
        (root / "deployment_verification_history.json").write_text(json.dumps([
            {"verified": False, "status": "failed", "error": "request_failed"},
            {"verified": True, "status": "verified", "release_marker": "insureai-release-new", "error": None},
        ]), encoding="utf-8")
        updated = attach_deployment_verification(root=root)
        self.assertEqual(updated["source_commit"], "commit-123")
        self.assertEqual(updated["deployment"]["status"], "verified")
        self.assertTrue(updated["deployment"]["verified"])
        self.assertTrue(updated["deployment"]["release_match"])
        self.assertEqual(updated["deployment"]["release_marker"], "insureai-release-new")
        self.assertEqual(updated["deployment"]["final_url"], "https://example.test/")
        self.assertEqual(updated["deployment"]["content_type"], "text/html")
        self.assertEqual(updated["deployment"]["http_status"], 200)
        self.assertTrue(updated["deployment"]["marker_found"])
        self.assertEqual(updated["deployment"]["trend"]["classification"], "recovered")
        self.assertEqual(updated["deployment"]["trend"]["failure_streak"], 0)
        self.assertEqual(updated["schema_version"], "release-provenance-v1")
        self.assertEqual(updated["version"], 1)
        self.assertEqual(len(updated["artifacts"]["deployment_verification_sha256"]), 64)
        self.assertEqual(len(updated["artifacts"]["deployment_history_sha256"]), 64)

    def test_stale_verified_deployment_is_not_inherited_by_new_release(self):
        root = self._root()
        (root / "release_provenance.json").write_text(json.dumps(build_provenance(
            source_commit="commit-123", site_url="https://example.test", root=root
        )), encoding="utf-8")
        (root / "deployment_verification.json").write_text(json.dumps({
            "version": 1,
            "status": "verified",
            "verified": True,
            "site_url": "https://example.test",
            "final_url": "https://example.test/",
            "expected_marker": "InsureAI",
            "release_marker": "insureai-release-old",
            "http_status": 200,
            "marker_found": True,
            "error": None,
            "checked_at": "2026-08-22T00:00:00+00:00",
        }), encoding="utf-8")
        (root / "deployment_verification_history.json").write_text("[]", encoding="utf-8")

        updated = build_provenance(source_commit="commit-new", site_url="https://example.test", root=root)
        self.assertEqual(updated["release_marker"], "insureai-release-new")
        self.assertEqual(updated["deployment"]["status"], "stale")
        self.assertFalse(updated["deployment"]["verified"])
        self.assertFalse(updated["deployment"]["release_match"])
        self.assertEqual(updated["deployment"]["release_marker"], "insureai-release-old")

    def test_lagging_site_is_stale_not_failed(self):
        """`stale` carries an explanatory error, so it must not be swallowed by
        the generic error branch. Reporting it as `failed` blocks the release
        pipeline that would publish the fix, so the site can never catch up.
        """
        root = self._root()
        (root / "release_provenance.json").write_text(json.dumps(build_provenance(
            source_commit="commit-123", site_url="https://example.test", root=root
        )), encoding="utf-8")
        (root / "deployment_verification.json").write_text(json.dumps({
            "version": 1,
            "status": "stale",
            "verified": False,
            "site_url": "https://example.test",
            "final_url": "https://example.test/",
            "expected_marker": "insureai-release-new",
            "release_marker": "insureai-release-old",
            "http_status": 200,
            "marker_found": False,
            "error": "published_marker_behind_expected",
            "checked_at": "2026-08-31T00:00:00+00:00",
        }), encoding="utf-8")
        (root / "deployment_verification_history.json").write_text("[]", encoding="utf-8")

        updated = build_provenance(source_commit="commit-new", site_url="https://example.test", root=root)
        self.assertEqual(updated["deployment"]["status"], "stale")
        self.assertFalse(updated["deployment"]["verified"])

    def test_unknown_marker_is_still_failed(self):
        """Tolerating lag must not become tolerating anything."""
        root = self._root()
        (root / "release_provenance.json").write_text(json.dumps(build_provenance(
            source_commit="commit-123", site_url="https://example.test", root=root
        )), encoding="utf-8")
        (root / "deployment_verification.json").write_text(json.dumps({
            "version": 1,
            "status": "failed",
            "verified": False,
            "site_url": "https://example.test",
            "final_url": "https://example.test/",
            "expected_marker": "insureai-release-new",
            "release_marker": "insureai-who-knows",
            "http_status": 200,
            "marker_found": False,
            "error": "http_or_marker_check_failed",
            "checked_at": "2026-08-31T00:00:00+00:00",
        }), encoding="utf-8")
        (root / "deployment_verification_history.json").write_text("[]", encoding="utf-8")

        updated = build_provenance(source_commit="commit-new", site_url="https://example.test", root=root)
        self.assertEqual(updated["deployment"]["status"], "failed")

    def test_unconfigured_deployment_is_configuration_debt(self):
        root = self._root()
        (root / "deployment_verification.json").write_text(json.dumps({
            "version": 1,
            "status": "unconfigured",
            "verified": False,
            "error": "site_url_missing",
            "expected_marker": "insureai-release-new",
        }), encoding="utf-8")
        updated = build_provenance(source_commit="commit-new", site_url="https://example.test", root=root)
        self.assertEqual(updated["deployment"]["status"], "configuration_debt")
        self.assertFalse(updated["deployment"]["verified"])

    def test_failed_deployment_remains_failed(self):
        root = self._root()
        (root / "deployment_verification.json").write_text(json.dumps({
            "version": 1,
            "status": "failed",
            "verified": False,
            "error": "request_failed:TimeoutError",
            "expected_marker": "insureai-release-new",
        }), encoding="utf-8")
        updated = build_provenance(source_commit="commit-new", site_url="https://example.test", root=root)
        self.assertEqual(updated["deployment"]["status"], "failed")
        self.assertFalse(updated["deployment"]["verified"])


if __name__ == "__main__":
    unittest.main()
