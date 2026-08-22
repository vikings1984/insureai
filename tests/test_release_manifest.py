#!/usr/bin/env python3
import unittest
from release_manifest import build_manifest


class TestReleaseManifest(unittest.TestCase):
    def test_quality_pass_does_not_claim_deployment(self):
        m = build_manifest(source_commit="abc123", site_url="https://example.test")
        self.assertEqual(m["quality_status"], "passed")
        self.assertEqual(m["deployment_status"], "pending")
        self.assertFalse(m["deployment_verified"])
        self.assertEqual(m["release_channel"], "github_pages")
        self.assertEqual(m["release_marker"], "insureai:abc123")

    def test_failed_quality_is_explicit(self):
        m = build_manifest(source_commit="abc123", site_url="https://example.test", quality_passed=False)
        self.assertEqual(m["quality_status"], "failed")
        self.assertFalse(m["deployment_verified"])
        self.assertEqual(m["release_marker"], "insureai:abc123")


if __name__ == "__main__":
    unittest.main()
