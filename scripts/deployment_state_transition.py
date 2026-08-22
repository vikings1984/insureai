#!/usr/bin/env python3
"""Detect deployment verification state transitions without committing heartbeats."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

CURRENT = Path("deployment_verification.json")
LATEST = Path("deployment_verification_latest.json")
HISTORY = Path("deployment_verification_history.json")

STATE_FIELDS = (
    "status",
    "verified",
    "site_url",
    "expected_marker",
    "http_status",
    "marker_found",
    "error",
)


def _load_current() -> dict:
    return json.loads(CURRENT.read_text(encoding="utf-8"))


def _load_previous() -> dict | None:
    try:
        raw = subprocess.check_output(
            ["git", "show", "HEAD:deployment_verification.json"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _state(value: dict | None) -> tuple:
    if not value:
        return ()
    return tuple(value.get(name) for name in STATE_FIELDS)


def main() -> None:
    current = _load_current()
    LATEST.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    previous = _load_previous()
    transitioned = _state(previous) != _state(current)

    if transitioned:
        history = json.loads(HISTORY.read_text(encoding="utf-8")) if HISTORY.exists() else []
        history.append({
            "status": current.get("status"),
            "verified": bool(current.get("verified", False)),
            "error": current.get("error"),
            "checked_at": current.get("checked_at"),
        })
        HISTORY.write_text(
            json.dumps(history[-30:], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print("state_changed=true")
    else:
        if previous is not None:
            CURRENT.write_text(json.dumps(previous, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("state_changed=false")


if __name__ == "__main__":
    main()
