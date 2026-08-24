#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Create a privacy-preserving lineage ledger for the analytical build."""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path
from contract import ARTIFACT_VERSIONS
ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "audit_ledger.json"
STAGES = (
    ("collect", "data.json", "collector"),
    ("intelligence", "intelligence.json", "intelligence"),
    ("trust", "intelligence.json", "trust"),
    ("claims", "intelligence.json", "claims"),
    ("temporal", "intelligence.json", "temporal"),
    ("decision", "intelligence.json", "decision"),
    ("decision_stability", "decision_stability.json", "decision_stability"),
    ("decision_credibility", "decision_credibility.json", "decision_credibility"),
    ("counterfactual", "counterfactual.json", "counterfactual"),
    ("scenario", "scenario.json", "scenario"),
    ("scenario_matrix", "scenario_matrix.json", "scenario_matrix"),
    ("action_triggers", "action_triggers.json", "action_triggers"),
    ("execution_readiness", "execution_readiness.json", "execution_readiness"),
    ("change_impact", "change_impact.json", "change_impact"),
    ("freshness", "freshness.json", "freshness"),
    ("evidence_availability", "evidence_availability.json", "evidence_availability"),
    ("review_queue", "review_queue.json", "human_review"),
    ("feedback_attribution", "feedback_attribution.json", "feedback_attribution"),
    ("module_health", "module_health.json", "module_health"),
    ("module_health_history", "module_health_history.json", "module_health"),
    ("module_health_trend", "module_health_trend.json", "module_health_trend"),
    ("trend_attribution", "trend_attribution.json", "trend_attribution"),
    ("optimization_backlog", "optimization_backlog.json", "optimization_backlog"),
    ("optimization_backlog_history", "optimization_backlog_history.json", "optimization_backlog"),
    ("daily_risk_radar", "daily_risk_radar.json", "daily_risk_radar"),
    ("owner_risk_view", "owner_risk_view.json", "owner_risk_view"),
)

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def _counts(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    counts = {}
    if isinstance(data, dict):
        for key in ("news", "events", "results", "scenarios", "items", "modules", "snapshots"):
            value = data.get(key)
            if isinstance(value, list):
                counts[key] = len(value)
            elif isinstance(value, dict):
                counts[f"{key}_keys"] = len(value)
        if data.get("version") is not None:
            counts["version"] = data["version"]
    return counts

def build_ledger() -> dict:
    records = []
    for stage, filename, producer in STAGES:
        path = ROOT / filename
        if path.exists():
            records.append({
                "stage": stage,
                "producer": producer,
                "artifact": filename,
                "sha256": sha256_file(path),
                "counts": _counts(path),
            })
    release = {}
    release_path = ROOT / "release_manifest.json"
    if release_path.exists():
        try:
            release = json.loads(release_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            release = {}
    gate = release.get("production_quality_gate") or {}
    return {
        "version": ARTIFACT_VERSIONS["audit_ledger.json"],
        "schema_version": "audit-ledger-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "privacy": "hashes_and_metadata_only",
        "coverage_principle": "ledger is generated after all analytical quality artifacts; release_manifest carries the production gate result",
        "production_quality_gate": {
            "status": gate.get("status", "unknown"),
            "failed_checks": list(gate.get("failed_checks") or []),
            "check_count": len(gate.get("checks") or []),
        },
        "stages": records,
    }

def main() -> None:
    ledger = build_ledger()
    OUTPUT.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Audit ledger: {len(ledger['stages'])} stages gate={ledger['production_quality_gate']['status']}")

if __name__ == "__main__":
    main()
