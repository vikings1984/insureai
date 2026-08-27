#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the proposition-level claim/evidence artifact (Claim Schema v3)."""
from __future__ import annotations

import json
from pathlib import Path

from claims import build_claims
from contract import ARTIFACT_VERSIONS

ROOT = Path(__file__).resolve().parent
INTEL = ROOT / "intelligence.json"
DATA = ROOT / "data.json"
OUT = ROOT / "claims.json"


def main() -> None:
    intelligence = json.loads(INTEL.read_text(encoding="utf-8"))
    items = json.loads(DATA.read_text(encoding="utf-8"))
    if isinstance(items, dict):
        items = items.get("news") or items.get("items") or items.get("data") or []
    items = items if isinstance(items, list) else []
    by_id = {str(x.get("id")): x for x in items if isinstance(x, dict) and x.get("id") is not None}

    events = []
    total_claims = 0
    total_cross_checked = 0
    total_single_source = 0
    total_unverified = 0
    total_conflicted = 0
    events_with_proposition = 0
    for event in intelligence.get("events", []):
        article_ids = [str(x) for x in (event.get("article_ids") or [])]
        evidence_items = [by_id[x] for x in article_ids if x in by_id]
        result = build_claims(evidence_items, event)
        for claim in result.get("claims", []):
            claim["event_id"] = event.get("event_id")
        proposition_count = int(result.get("proposition_count", 0) or 0)
        if proposition_count >= 1:
            events_with_proposition += 1
        conflicted = int(result.get("conflicted", 0) or 0)
        events.append({
            "event_id": event.get("event_id"),
            "coverage": result.get("coverage", 0),
            "cross_checked": result.get("cross_checked", 0),
            "unsupported": result.get("unsupported", 0),
            "conflicted": conflicted,
            "proposition_count": proposition_count,
            "single_source": sum(1 for x in result.get("claims", []) if x.get("verification_status") == "single_source"),
            "claims": result.get("claims", []),
        })
        total_claims += len(result.get("claims", []))
        total_cross_checked += int(result.get("cross_checked", 0) or 0)
        total_single_source += sum(1 for x in result.get("claims", []) if x.get("verification_status") == "single_source")
        total_unverified += sum(1 for x in result.get("claims", []) if x.get("verification_status") == "unverified")
        total_conflicted += conflicted

    proposition_coverage = round(100 * events_with_proposition / len(events), 1) if events else 0
    claim_evidence_match_rate = round((total_claims - total_unverified) / total_claims, 4) if total_claims else 0.0
    payload = {
        "version": ARTIFACT_VERSIONS["claims.json"],
        "generated_from": "intelligence.json + data.json",
        "event_count": len(events),
        "claim_count": total_claims,
        "cross_checked_claim_count": total_cross_checked,
        "single_source_claim_count": total_single_source,
        "unverified_claim_count": total_unverified,
        "conflicted_claim_count": total_conflicted,
        "proposition_coverage": proposition_coverage,
        "claim_evidence_match_rate": claim_evidence_match_rate,
        "events": events,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Claims artifact v{payload['version']}: events={len(events)} claims={total_claims} cross_checked={total_cross_checked} single_source={total_single_source} conflicted={total_conflicted} proposition_coverage={proposition_coverage}% match_rate={claim_evidence_match_rate}")


if __name__ == "__main__":
    main()
