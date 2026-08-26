#!/usr/bin/env python3
"""Build a management-level daily intelligence terminal from existing artifacts."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "executive_terminal.json"


def load(name: str, default):
    path = ROOT / name
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def main() -> None:
    intelligence = load("intelligence.json", {})
    claims = load("claims.json", {})
    review = load("review_queue.json", {})
    risk = load("daily_risk_radar.json", {})
    owner = load("owner_risk_view.json", {})
    credibility = load("decision_credibility.json", {})
    provenance = load("release_provenance.json", {})

    events = intelligence.get("events") or []
    stats = intelligence.get("stats") or {}
    trends = (intelligence.get("radar") or {}).get("topic_trends") or []
    rising = [x for x in trends if x.get("direction") == "rising"]
    attention = [x for x in (risk.get("items") or risk.get("signals") or []) if isinstance(x, dict)]
    reviews = review.get("items") or review.get("queue") or []

    def score_event(event: dict) -> float:
        return float(event.get("importance", event.get("score", 0)) or 0) + (15 if event.get("review_required") else 0)

    priority_events = sorted(events, key=score_event, reverse=True)[:8]
    avg_coverage = (
        sum(float(e.get("evidence_coverage", 0) or 0) for e in events) / len(events)
        if events else 0
    )

    output = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "event_count": len(events),
            "rising_topics": len(rising),
            "review_queue": len(reviews),
            "attention_signals": len(attention),
            "avg_evidence_coverage": round(avg_coverage, 1),
            "cross_checked_claims": int(claims.get("cross_checked_claim_count", 0) or 0),
            "single_source_claims": int(claims.get("single_source_claim_count", 0) or 0),
            "credibility_status": credibility.get("status", "unknown"),
            "deployment_status": (provenance.get("deployment") or {}).get("status", "unknown"),
        },
        "what_changed": [
            {"title": e.get("topic") or e.get("title") or "未命名事件", "why": e.get("insight") or e.get("summary"), "event_id": e.get("event_id"), "trust": e.get("trust"), "evidence_coverage": e.get("evidence_coverage"), "review_required": bool(e.get("review_required", False))}
            for e in priority_events
        ],
        "what_is_accelerating": rising[:8],
        "what_needs_attention": attention[:8],
        "what_needs_human_decision": reviews[:8],
        "release": {
            "source_commit": provenance.get("source_commit"),
            "release_marker": provenance.get("release_marker"),
            "deployment": provenance.get("deployment", {}),
            "quality": provenance.get("quality", {}),
        },
        "artifact_sources": [
            "intelligence.json",
            "claims.json",
            "review_queue.json",
            "daily_risk_radar.json",
            "owner_risk_view.json",
            "decision_credibility.json",
            "release_provenance.json",
        ],
    }
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
