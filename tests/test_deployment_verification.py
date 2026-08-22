#!/usr/bin/env python3
import unittest
from unittest.mock import patch

from deployment_verification import verify_deployment


class _Headers:
    def __init__(self, content_type: str = "text/html; charset=utf-8"):
        self._content_type = content_type

    def get(self, key, default=None):
        if key.lower() == "content-type":
            return self._content_type
        return default


class _Response:
    status = 200

    def __init__(self, body: bytes, url: str = "https://example.test", content_type: str = "text/html; charset=utf-8"):
        self.body = body
        self._url = url
        self.headers = _Headers(content_type)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def geturl(self):
        return self._url

    def read(self, limit=None):
        if limit is None:
            return self.body
        return self.body[:limit]


class TestDeploymentVerification(unittest.TestCase):
    def test_missing_site_url_is_unconfigured(self):
        result = verify_deployment(site_url="")
        self.assertFalse(result["verified"])
        self.assertEqual(result["status"], "unconfigured")
        self.assertEqual(result["error"], "site_url_missing")

    def test_http_site_url_is_rejected(self):
        result = verify_deployment(site_url="http://example.test")
        self.assertFalse(result["verified"])
        self.assertEqual(result["error"], "insecure_or_invalid_site_url")

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
        self.assertEqual(result["final_url"], "https://example.test")
        self.assertEqual(result["content_type"], "text/html")
        self.assertTrue(result["marker_found"])
        self.assertEqual(result["release_marker"], marker)

    @patch("deployment_verification.urllib.request.urlopen")
    def test_redirect_to_different_origin_does_not_verify(self, urlopen):
        urlopen.return_value = _Response(b"<html></html>", url="https://attacker.test")
        result = verify_deployment(site_url="https://example.test", expected_marker="insureai-current")
        self.assertFalse(result["verified"])
        self.assertEqual(result["error"], "redirect_origin_mismatch")

    @patch("deployment_verification.urllib.request.urlopen")
    def test_non_html_response_does_not_verify(self, urlopen):
        marker = "insureai-abc123"
        urlopen.return_value = _Response(
            f'<html><head><meta name="insureai-release-marker" content="{marker}"></head></html>'.encode(),
            content_type="application/json",
        )
        result = verify_deployment(site_url="https://example.test", expected_marker=marker)
        self.assertFalse(result["verified"])
        self.assertEqual(result["error"], "unexpected_content_type")

    @patch("deployment_verification.urllib.request.urlopen")
    def test_oversized_response_does_not_verify(self, urlopen):
        urlopen.return_value = _Response(b"x" * (1_048_576 + 1))
        result = verify_deployment(site_url="https://example.test")
        self.assertFalse(result["verified"])
        self.assertEqual(result["error"], "response_too_large")

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
