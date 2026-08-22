#!/usr/bin/env python3
"""Verify that the published site matches the current release marker."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "deployment_verification.json"


def _load_release_marker() -> str:
    path = ROOT / "release_manifest.json"
    if not path.exists():
        return ""
    data = json.loads(path.read_text(encoding="utf-8"))
    return str(data.get("release_marker") or "")


def verify_deployment(*, site_url: str, expected_marker: str = "", timeout: float = 15.0) -> dict:
    checked_at = datetime.now(timezone.utc).isoformat()
    expected_marker = expected_marker or _load_release_marker()
    result = {
        "version": 2,
        "status": "failed",
        "verified": False,
        "site_url": site_url,
        "expected_marker": expected_marker,
        "release_marker_found": False,
        "http_status": None,
        "content_length": 0,
        "marker_found": False,
        "error": None,
        "checked_at": checked_at,
    }
    if not site_url:
        result["error"] = "site_url_missing"
        return result
    if not expected_marker:
        result["error"] = "release_marker_missing"
        return result
    try:
        request = urllib.request.Request(site_url, headers={"User-Agent": "InsureAI-Deployment-Verification/2.0"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            text = body.decode("utf-8", errors="replace")
            result["http_status"] = int(response.status)
            result["content_length"] = len(body)
            result["marker_found"] = "InsureAI" in text
            result["release_marker_found"] = expected_marker in text
            if response.status == 200 and body and result["marker_found"] and result["release_marker_found"]:
                result["status"] = "verified"
                result["verified"] = True
            elif response.status == 200 and body and result["marker_found"]:
                result["error"] = "release_marker_mismatch"
            else:
                result["error"] = "http_or_marker_check_failed"
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        result["error"] = f"request_failed:{type(exc).__name__}"
    return result


def main() -> None:
    result = verify_deployment(site_url=os.environ.get("SITE_URL", ""))
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    if not result["verified"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
