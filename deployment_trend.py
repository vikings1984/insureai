#!/usr/bin/env python3
"""Attribute deployment verification history without changing business decisions."""
from __future__ import annotations
from datetime import datetime, timezone


def attribute_deployment_trend(history: list[dict] | None) -> dict:
    rows = [x for x in (history or []) if isinstance(x, dict)]
    if not rows:
        return {"version": 1, "classification": "baseline", "failure_streak": 0}
    verified = [bool(x.get("verified", False)) for x in rows]
    failure_streak = 0
    for ok in reversed(verified):
        if ok:
            break
        failure_streak += 1
    if len(verified) == 1:
        classification = "single_failure" if not verified[-1] else "stable"
    elif failure_streak >= 2:
        classification = "persistent_failure"
    elif verified[-1] and not verified[-2]:
        classification = "recovered"
    elif not verified[-1] and verified[-2]:
        classification = "single_failure"
    else:
        classification = "stable"
    return {
        "version": 1,
        "classification": classification,
        "failure_streak": failure_streak,
        "sample_count": len(verified),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
