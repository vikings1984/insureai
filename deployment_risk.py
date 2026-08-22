#!/usr/bin/env python3
"""Convert deployment verification into an advisory risk signal."""
from __future__ import annotations

from datetime import datetime, timezone


def build_deployment_risk(deployment: dict | None) -> dict:
    deployment = deployment or {}
    verified = bool(deployment.get("verified", False))
    status = deployment.get("status", "unknown")
    error = deployment.get("error")
    if verified or status == "verified":
        classification = "deployment_verified"
        priority = 0
        attention = False
    elif status == "failed" or error:
        classification = "deployment_failed"
        priority = 90
        attention = True
    else:
        classification = "deployment_unverified"
        priority = 70
        attention = True
    return {
        "version": 1,
        "classification": classification,
        "priority": priority,
        "attention": attention,
        "verified": verified,
        "status": status,
        "error": error,
        "checked_at": deployment.get("checked_at"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "principle": "部署风险只影响人工注意力与发布可信度，不修改 Decision/Trust/Urgency。",
    }


if __name__ == "__main__":
    print(build_deployment_risk({"status": "pending", "verified": False}))
