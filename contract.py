#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""InsureAI Intelligence Data Contract."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INTEL = ROOT / "intelligence.json"
CONTRACT_VERSION = 1
EXPECTED_VERSION = 7

# Single source of truth for versioned pipeline artifacts. Generators and the
# validation script both read from this map, so a version bump in a generator
# can never silently drift out of sync with the pipeline's contract gate.
ARTIFACT_VERSIONS = {
    "decision_stability.json": 1,
    "decision_history.json": 1,
    "decision_credibility.json": 3,
    "daily_risk_radar.json": 4,
    "owner_risk_view.json": 2,
    "trend_attribution.json": 1,
    "review_queue.json": 3,
    "change_impact.json": 1,
    "audit_ledger.json": 1,
    "feedback_attribution.json": 1,
    "module_health.json": 1,
    "module_health_trend.json": 1,
    "optimization_backlog.json": 3,
    "optimization_backlog_history.json": 2,
}

# Single source of truth for the production release channel and cross-artifact
# schema identities. Generators, the production workflow, and release provenance
# all read from here, so a channel/schema rename in a generator can never drift
# out of sync with the CI contract gates.
RELEASE_CHANNEL = "cloudflare_workers"

SCHEMA_VERSIONS = {
    "release_manifest": 1,
    "release_provenance": 1,
    "release_provenance_schema": "release-provenance-v1",
    "audit_ledger_schema": "audit-ledger-v1",
}

EVENT_REQUIRED = {"event_id", "title", "event_type", "entities", "topic", "published_at", "source_count", "article_count", "article_ids", "scores", "insight", "trust", "claims"}
SCORE_KEYS = {"relevance", "impact", "novelty", "actionability", "confidence", "intelligence_score"}

def _sha(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]

def validate(data: dict) -> list[str]:
    errors: list[str] = []
    if data.get("version") != EXPECTED_VERSION:
        errors.append(f"unsupported intelligence version: {data.get('version')}")
    events = data.get("events")
    if not isinstance(events, list) or not events:
        errors.append("events must be a non-empty list")
        return errors
    seen = set()
    for idx, event in enumerate(events):
        missing = EVENT_REQUIRED - set(event)
        if missing:
            errors.append(f"event[{idx}] missing: {sorted(missing)}")
        event_id = event.get("event_id")
        if not event_id or event_id in seen:
            errors.append(f"event[{idx}] invalid/duplicate event_id: {event_id}")
        seen.add(event_id)
        scores = event.get("scores") or {}
        missing_scores = SCORE_KEYS - set(scores)
        if missing_scores:
            errors.append(f"event[{idx}] missing scores: {sorted(missing_scores)}")
        for key in SCORE_KEYS:
            if key in scores and not isinstance(scores[key], (int, float)):
                errors.append(f"event[{idx}] score {key} is not numeric")
        claims = event.get("claims") or {}
        if not isinstance(claims.get("claims"), list):
            errors.append(f"event[{idx}] claims.claims must be a list")
        trust = event.get("trust") or {}
        if trust.get("level") not in {"high", "medium", "low"}:
            errors.append(f"event[{idx}] invalid trust level: {trust.get('level')}")
    decisions = data.get("decisions") or []
    if not isinstance(decisions, list):
        errors.append("decisions must be a list")
    else:
        for idx, decision in enumerate(decisions):
            for key in ("event_id", "urgency", "guardrail"):
                if not decision.get(key):
                    errors.append(f"decision[{idx}] missing: {key}")
            if decision.get("urgency") not in {"now", "soon", "watch"}:
                errors.append(f"decision[{idx}] invalid urgency: {decision.get('urgency')}")
    temporal = data.get("temporal") or {}
    if not isinstance(temporal.get("topic_signals"), list):
        errors.append("temporal.topic_signals must be a list")
    if not isinstance(temporal.get("entity_momentum"), list):
        errors.append("temporal.entity_momentum must be a list")
    return errors

def attach_contract(data: dict) -> dict:
    errors = validate(data)
    if errors:
        raise ValueError("; ".join(errors[:20]))
    data["data_contract"] = {
        "schema_version": CONTRACT_VERSION,
        "intelligence_version": data.get("version"),
        "producer": "insureai-intelligence-pipeline",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "components": {
            "events": _sha(data.get("events", [])),
            "trust": _sha(data.get("trust_stats", {})),
            "claims": _sha(data.get("claim_stats", {})),
            "temporal": _sha(data.get("temporal", {})),
            "decisions": _sha(data.get("decisions", [])),
            "radar": _sha(data.get("radar", {})),
        },
        "counts": {
            "events": len(data.get("events", [])),
            "decisions": len(data.get("decisions", [])),
            "topic_signals": len(data.get("temporal", {}).get("topic_signals", [])),
            "entity_momentum": len(data.get("temporal", {}).get("entity_momentum", [])),
        },
    }
    return data

def main() -> None:
    data = json.loads(INTEL.read_text(encoding="utf-8"))
    attach_contract(data)
    INTEL.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Data contract validated: schema", CONTRACT_VERSION)

if __name__ == "__main__":
    main()
