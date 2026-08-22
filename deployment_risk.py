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
        classification, priority, attention = "deployment_verified", 0, False
    elif status == "failed" or error:
        classification, priority, attention = "deployment_failed", 90, True
    else:
        classification, priority, attention = "deployment_unverified", 70, True
    return {
        "version": 1, "classification": classification, "priority": priority,
        "attention": attention, "verified": verified, "status": status,
        "error": error, "checked_at": deployment.get("checked_at"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "principle": "部署风险只影响人工注意力与发布可信度，不修改 Decision/Trust/Urgency。",
    }
