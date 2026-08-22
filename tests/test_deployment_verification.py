#!/usr/bin/env python3
import unittest
from unittest.mock import patch

from deployment_verification import verify_deployment


class _Response:
    status = 200

    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.body


class TestDeploymentVerification(unittest.TestCase):
    def test_missing_site_url_is_unconfigured(self):
        result = verify_deployment(site_url="")
        self.assertFalse(result["verified"])
        self.assertEqual(result["status"], "unconfigured")
        self.assertEqual(result["error"], "site_url_missing")

    @patch("deployment_verification.urllib.request.urlopen")
    def test_http_200_and_exact_release_marker_verifies(self, urlopen):
        marker = "insureai-abc123"
        urlopen.return_value = _Response(
            f'<html><head><meta name="insureai-release-marker" content="{marker}"></head></html>'.encode()
        )
        result = verify_deployment(site_url="https://example.test", expected_marker=marker)
        self.assertTrue(result["verified"])
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["http_status"], 200)
        self.assertTrue(result["marker_found"])
        self.assertEqual(result["release_marker"], marker)

    @patch("deployment_verification.urllib.request.urlopen")
    def test_body_marker_without_metadata_does_not_verify(self, urlopen):
        urlopen.return_value = _Response(b"<html><title>insureai-abc123</title></html>")
        result = verify_deployment(site_url="https://example.test", expected_marker="insureai-abc123")
        self.assertFalse(result["verified"])
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["marker_found"])
        self.assertIsNone(result["release_marker"])
        self.assertEqual(result["error"], "http_or_marker_check_failed")

    @patch("deployment_verification.urllib.request.urlopen")
    def test_wrong_release_marker_does_not_verify(self, urlopen):
        urlopen.return_value = _Response(
            b'<html><head><meta name="insureai-release-marker" content="insureai-old"></head></html>'
        )
        result = verify_deployment(site_url="https://example.test", expected_marker="insureai-current")
        self.assertFalse(result["verified"])
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["marker_found"])
        self.assertEqual(result["release_marker"], "insureai-old")

    @patch("deployment_verification.urllib.request.urlopen")
    def test_missing_marker_does_not_verify(self, urlopen):
        urlopen.return_value = _Response(b"<html>not our site</html>")
        result = verify_deployment(site_url="https://example.test")
        self.assertFalse(result["verified"])
        self.assertEqual(result["status"], "failed")
        self.assertIsNone(result["release_marker"])
        self.assertEqual(result["error"], "http_or_marker_check_failed")


if __name__ == "__main__":
    unittest.main()
