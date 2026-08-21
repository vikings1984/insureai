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
    def test_missing_site_url_is_failed(self):
        result = verify_deployment(site_url="")
        self.assertFalse(result["verified"])
        self.assertEqual(result["error"], "site_url_missing")

    @patch("deployment_verification.urllib.request.urlopen")
    def test_http_200_and_marker_verifies(self, urlopen):
        urlopen.return_value = _Response(b"<html><title>InsureAI</title></html>")
        result = verify_deployment(site_url="https://example.test")
        self.assertTrue(result["verified"])
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["http_status"], 200)
        self.assertTrue(result["marker_found"])

    @patch("deployment_verification.urllib.request.urlopen")
    def test_missing_marker_does_not_verify(self, urlopen):
        urlopen.return_value = _Response(b"<html>not our site</html>")
        result = verify_deployment(site_url="https://example.test")
        self.assertFalse(result["verified"])
        self.assertEqual(result["error"], "http_or_marker_check_failed")


if __name__ == "__main__":
    unittest.main()
