#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build and update a privacy-safe release provenance record."""
# release-provenance-v1-compatible: add deployment trend, release marker, and gate evidence as metadata.
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from deployment_trend import attribute_deployment_trend

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "release_provenance.json"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_history(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _deployment_matches_release(deployment: dict, release: dict) -> bool:
    expected = release.get("release_marker")
    observed = deployment.get("release_marker") or deployment.get("expected_marker")
    return bool(expected and observed and expected == observed)


def _normalize_deployment_status(*, deployment: dict, release_status: str = "pending", marker_matches: bool = False, verified: bool = False) -> str:
    if verified:
        return "verified"
    if deployment.get("verified", False) and not marker_matches:
        return "stale"
    raw = deployment.get("status")
    if raw == "unconfigured" or deployment.get("error") == "site_url_missing":
        return "configuration_debt"
    if raw == "failed" or deployment.get("error"):
        return "failed"
    if raw in {"pending", "unknown", "configuration_debt", "stale"}:
        return raw
    if release_status in {"pending", "unknown", "configuration_debt", "stale", "failed", "verified"}:
        return release_status
    return "pending"


def build_provenance(*, source_commit: str, site_url: str, root: Path = ROOT) -> dict:
    release_path = root / "release_manifest.json"
    audit_path = root / "audit_ledger.json"
    impact_path = root / "change_impact.json"
    deployment_path = root / "deployment_verification.json"
    history_path = root / "deployment_verification_history.json"
    release = _read_json(release_path)
    audit = _read_json(audit_path)
    gate = release.get("production_quality_gate") or {}
    impact = _read_json(impact_path) if impact_path.exists() else {}
    deployment_check = _read_json(deployment_path) if deployment_path.exists() else {}
    history = _read_history(history_path)
    stages = audit.get("stages", [])
    marker_matches = _deployment_matches_release(deployment_check, release)
    verified = bool(deployment_check.get("verified", False)) and marker_matches
    deployment_status = _normalize_deployment_status(
        deployment=deployment_check,
        release_status=release.get("deployment_status", "pending"),
        marker_matches=marker_matches,
        verified=verified,
    )
    deployment_trend = attribute_deployment_trend(history)
    return {
        "version": 1,
        "schema_version": "release-provenance-v1",
        "source_commit": source_commit or release.get("source_commit") or "unknown",
        "release_channel": release.get("release_channel", "cloudflare_workers"),
        "site_url": site_url or release.get("site_url", ""),
        "release_marker": release.get("release_marker"),
        "quality": {
            "status": release.get("quality_status", "unknown"),
            "production_gate_status": gate.get("status", "unknown"),
            "production_gate_failed_checks": gate.get("failed_checks", []),
            "audit_privacy": audit.get("privacy", "unknown"),
            "audit_stage_count": len(stages),
            "audit_artifact_count": len({row.get("artifact") for row in stages if row.get("artifact")}),
        },
        "impact": {
            "baseline_available": bool(impact.get("baseline_available", False)),
            "impacted_count": int(impact.get("impacted_count", 0)),
        },
        "deployment": {
            "status": deployment_status,
            "verified": verified,
            "release_match": marker_matches,
            "checked_at": deployment_check.get("checked_at"),
            "final_url": deployment_check.get("final_url"),
            "content_type": deployment_check.get("content_type"),
            "http_status": deployment_check.get("http_status"),
            "marker_found": bool(deployment_check.get("marker_found", False)),
            "release_marker": deployment_check.get("release_marker") or deployment_check.get("expected_marker"),
            "error": deployment_check.get("error"),
            "trend": deployment_trend,
        },
        "artifacts": {
            "release_manifest_sha256": _sha256(release_path),
            "audit_ledger_sha256": _sha256(audit_path),
            "change_impact_sha256": _sha256(impact_path) if impact_path.exists() else None,
            "deployment_verification_sha256": _sha256(deployment_path) if deployment_path.exists() else None,
            "deployment_history_sha256": _sha256(history_path) if history_path.exists() else None,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def attach_deployment_verification(*, root: Path = ROOT) -> dict:
    """Update existing provenance with latest verification and derived trend only."""
    provenance_path = root / "release_provenance.json"
    deployment_path = root / "deployment_verification.json"
    history_path = root / "deployment_verification_history.json"
    provenance = _read_json(provenance_path)
    deployment = _read_json(deployment_path)
    history = _read_history(history_path)
    expected_marker = provenance.get("release_marker")
    observed_marker = deployment.get("release_marker") or deployment.get("expected_marker")
    marker_matches = bool(expected_marker and observed_marker and expected_marker == observed_marker)
    verified = bool(deployment.get("verified", False)) and marker_matches
    provenance["deployment"] = {
        "status": _normalize_deployment_status(
            deployment=deployment,
            release_status=provenance.get("deployment", {}).get("status", "pending"),
            marker_matches=marker_matches,
            verified=verified,
        ),
        "verified": verified,
        "release_match": marker_matches,
        "checked_at": deployment.get("checked_at"),
        "final_url": deployment.get("final_url"),
        "content_type": deployment.get("content_type"),
        "http_status": deployment.get("http_status"),
        "marker_found": bool(deployment.get("marker_found", False)),
        "release_marker": observed_marker,
        "error": deployment.get("error"),
        "trend": attribute_deployment_trend(history),
    }
    artifacts = provenance.setdefault("artifacts", {})
    artifacts["deployment_verification_sha256"] = _sha256(deployment_path)
    artifacts["deployment_history_sha256"] = _sha256(history_path) if history_path.exists() else None
    provenance["generated_at"] = datetime.now(timezone.utc).isoformat()
    provenance["schema_version"] = "release-provenance-v1"
    provenance["version"] = 1
    provenance_path.write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return provenance


def main() -> None:
    provenance = build_provenance(
        source_commit=os.environ.get("GITHUB_SHA", "unknown"),
        site_url=os.environ.get("SITE_URL", ""),
    )
    OUTPUT.write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(provenance, ensure_ascii=False))


if __name__ == "__main__":
    main()
