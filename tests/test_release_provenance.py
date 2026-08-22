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
            "release_marker": "insureai:commit-123",
            "release_channel": "github_pages",
            "site_url": "https://example.test",
            "quality_status": "passed",
            "deployment_status": "pending",
            "deployment_verified": False,
        }), encoding="utf-8")
        (root / "audit_ledger.json").write_text(json.dumps({
            "version": 1,
            "privacy": "hashes_and_metadata_only",
            "stages": [{"artifact": "data.json", "sha256": "a" * 64}],
        }), encoding="utf-8")
        (root / "change_impact.json").write_text(json.dumps({
            "version": 1,
            "baseline_available": True,
            "impacted_count": 3,
        }), encoding="utf-8")
        return root

    def test_build_contains_stable_release_marker(self):
        root = self._root()
        provenance = build_provenance(source_commit="commit-123", site_url="https://example.test", root=root)
        self.assertEqual(provenance["version"], 1)
        self.assertEqual(provenance["schema_version"], "release-provenance-v1")
        self.assertEqual(provenance["release_marker"], "insureai:commit-123")
        self.assertEqual(provenance["deployment"]["status"], "pending")
        self.assertFalse(provenance["deployment"]["verified"])

    def test_verified_deployment_requires_release_identity_match(self):
        root = self._root()
        (root / "release_provenance.json").write_text(json.dumps(build_provenance(
            source_commit="commit-123", site_url="https://example.test", root=root
        )), encoding="utf-8")
        (root / "deployment_verification.json").write_text(json.dumps({
            "version": 2, "status": "verified", "verified": True,
            "release_marker": "insureai:old", "release_marker_found": True,
            "http_status": 200, "marker_found": True,
            "checked_at": "2026-08-22T00:00:00+00:00",
        }), encoding="utf-8")
        updated = attach_deployment_verification(root=root)
        self.assertEqual(updated["deployment"]["status"], "stale")
        self.assertFalse(updated["deployment"]["verified"])

        (root / "deployment_verification.json").write_text(json.dumps({
            "version": 2, "status": "verified", "verified": True,
            "release_marker": "insureai:commit-123", "release_marker_found": True,
            "http_status": 200, "marker_found": True,
            "checked_at": "2026-08-22T00:00:01+00:00",
        }), encoding="utf-8")
        updated = attach_deployment_verification(root=root)
        self.assertEqual(updated["deployment"]["status"], "verified")
        self.assertTrue(updated["deployment"]["verified"])


if __name__ == "__main__":
    unittest.main()
