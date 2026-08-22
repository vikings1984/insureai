#!/usr/bin/env python3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from deployment_verification import verify_deployment
from release_manifest import build_release_marker, inject_release_marker


class _Response:
    status = 200

    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._body


class TestReleaseIdentity(unittest.TestCase):
    def test_marker_is_stable_for_same_source_and_audit(self):
        with tempfile.TemporaryDirectory() as td:
            audit = Path(td) / "audit_ledger.json"
            audit.write_text('{"stages":[{"artifact":"a"}]}\n', encoding="utf-8")
            first = build_release_marker(source_commit="abc123", audit_path=audit)
            second = build_release_marker(source_commit="abc123", audit_path=audit)
            changed = build_release_marker(source_commit="def456", audit_path=audit)
        self.assertEqual(first, second)
        self.assertNotEqual(first, changed)
        self.assertTrue(first.startswith("insureai-"))

    def test_marker_injection_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            import release_manifest
            original = release_manifest.INDEX
            index = Path(td) / "index.html"
            index.write_text("<html><head></head><body>InsureAI</body></html>", encoding="utf-8")
            release_manifest.INDEX = index
            try:
                inject_release_marker("insureai-1234")
                inject_release_marker("insureai-1234")
                text = index.read_text(encoding="utf-8")
            finally:
                release_manifest.INDEX = original
        self.assertEqual(text.count('name="insureai-release-marker"'), 1)
        self.assertIn('content="insureai-1234"', text)

    def test_deployment_marker_mismatch_is_not_verified(self):
        body = b'<html><head><meta name="insureai-release-marker" content="insureai-old"></head>InsureAI</html>'
        with patch("deployment_verification.urllib.request.urlopen", return_value=_Response(body)):
            result = verify_deployment(site_url="https://example.test", expected_marker="insureai-current")
        self.assertFalse(result["verified"])
        self.assertEqual(result["error"], "http_or_release_marker_check_failed")
        self.assertFalse(result["marker_found"])


if __name__ == "__main__":
    unittest.main()
