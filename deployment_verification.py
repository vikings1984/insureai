#!/usr/bin/env python3
"""Verify that the published site matches the current release identity."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent / "deployment_verification.json"
RELEASE_MANIFEST = Path(__file__).resolve().parent / "release_manifest.json"
MAX_RESPONSE_BYTES = 1_048_576


class _ReleaseMarkerParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.marker: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "meta":
            return
        attributes = {key.lower(): value for key, value in attrs}
        if attributes.get("name", "").lower() == "insureai-release-marker":
            value = attributes.get("content")
            if value:
                self.marker = value


def _extract_release_marker(html: str) -> str | None:
    parser = _ReleaseMarkerParser()
    try:
        parser.feed(html)
        parser.close()
    except ValueError:
        return None
    return parser.marker


def _current_release_marker() -> str:
    override = os.environ.get("DEPLOYMENT_RELEASE_MARKER")
    if override:
        return override
    if RELEASE_MANIFEST.exists():
        try:
            marker = json.loads(RELEASE_MANIFEST.read_text(encoding="utf-8")).get("release_marker")
            if marker:
                return marker
        except (OSError, json.JSONDecodeError):
            pass
    return os.environ.get("DEPLOYMENT_MARKER", "InsureAI")


def verify_deployment(*, site_url: str, expected_marker: str = "InsureAI", timeout: float = 15.0) -> dict:
    checked_at = datetime.now(timezone.utc).isoformat()
    result = {
        "version": 1,
        "status": "failed",
        "verified": False,
        "site_url": site_url,
        "final_url": None,
        "expected_marker": expected_marker,
        "release_marker": None,
        "http_status": None,
        "content_type": None,
        "content_length": 0,
        "marker_found": False,
        "error": None,
        "checked_at": checked_at,
    }
    if not site_url:
        result["status"] = "unconfigured"
        result["error"] = "site_url_missing"
        return result
    parsed = urllib.parse.urlparse(site_url)
    if parsed.scheme != "https" or not parsed.netloc:
        result["error"] = "insecure_or_invalid_site_url"
        return result
    try:
        request = urllib.request.Request(site_url, headers={"User-Agent": "InsureAI-Deployment-Verification/1.1"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            final_url = response.geturl() if callable(getattr(response, "geturl", None)) else site_url
            result["final_url"] = final_url
            final = urllib.parse.urlparse(final_url)
            if final.scheme != "https" or final.netloc != parsed.netloc:
                result["error"] = "redirect_origin_mismatch"
                return result
            result["http_status"] = int(response.status)
            result["content_type"] = ((response.headers.get("Content-Type") if getattr(response, "headers", None) else "text/html") or "").split(";", 1)[0].strip().lower()
            if result["content_type"] not in {"text/html", "application/xhtml+xml"}:
                result["error"] = "unexpected_content_type"
                return result
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                result["content_length"] = len(body)
                result["error"] = "response_too_large"
                return result
            text = body.decode("utf-8", errors="replace")
            published_marker = _extract_release_marker(text)
            result["content_length"] = len(body)
            result["release_marker"] = published_marker
            result["marker_found"] = published_marker == expected_marker
            if response.status == 200 and body and result["marker_found"]:
                result["status"] = "verified"
                result["verified"] = True
            else:
                result["error"] = "http_or_marker_check_failed"
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        result["error"] = f"request_failed:{type(exc).__name__}"
    return result


def main() -> None:
    result = verify_deployment(site_url=os.environ.get("DEPLOYMENT_URL", ""), expected_marker=_current_release_marker())
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    if not result["verified"] and result["status"] != "unconfigured":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
