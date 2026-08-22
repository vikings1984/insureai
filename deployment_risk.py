#!/usr/bin/env python3
"""Convert deployment verification into an advisory risk signal."""
from __future__ import annotations
from datetime import datetime, timezone
from deployment_trend import attribute_deployment_trend

def build_deployment_risk(deployment: dict | None, history: list[dict] | None = None) -> dict:
    deployment = deployment or {}
    trend = attribute_deployment_trend(history)
    verified = bool(deployment.get("verified", False))
    status = deployment.get("status", "unknown")
    error = deployment.get("error")
    if verified or status == "verified":
        classification, priority, attention = "deployment_verified", 0, False
    elif status == "unconfigured" or error == "site_url_missing":
        classification, priority, attention = "deployment_configuration_missing", 40, True
    elif trend["classification"] == "persistent_failure":
        classification, priority, attention = "deployment_persistent_failure", 95, True
    elif status == "failed" or error:
        classification, priority, attention = "deployment_failed", 90, True
    else:
        classification, priority, attention = "deployment_unverified", 70, True
    return {
        "version": 2,
        "classification": classification,
        "priority": priority,
        "attention": attention,
        "verified": verified,
        "status": status,
        "error": error,
        "checked_at": deployment.get("checked_at"),
        "trend": trend,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "principle": "部署风险只影响人工注意力与发布可信度，不修改 Decision/Trust/Urgency。",
    }
