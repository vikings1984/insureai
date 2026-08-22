#!/usr/bin/env python3
"""Verify that the published site matches the current release identity."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent / "deployment_verification.json"
RELEASE_MANIFEST = Path(__file__).resolve().parent / "release_manifest.json"


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
        "expected_marker": expected_marker,
        "release_marker": expected_marker,
        "http_status": None,
        "content_length": 0,
        "marker_found": False,
        "error": None,
        "checked_at": checked_at,
    }
    if not site_url:
        result["status"] = "unconfigured"
        result["error"] = "site_url_missing"
        return result
    try:
        request = urllib.request.Request(site_url, headers={"User-Agent": "InsureAI-Deployment-Verification/1.0"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            text = body.decode("utf-8", errors="replace")
            published_marker = _extract_release_marker(text)
            result["http_status"] = int(response.status)
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
    result = verify_deployment(
        site_url=os.environ.get("DEPLOYMENT_URL", ""),
        expected_marker=_current_release_marker(),
    )
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    if not result["verified"] and result["status"] != "unconfigured":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
