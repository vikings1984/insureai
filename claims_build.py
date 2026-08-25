#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a lightweight, source-linked claim/evidence artifact per event."""
from __future__ import annotations

import json
from pathlib import Path

from claims import build_claims

ROOT = Path(__file__).resolve().parent
INTEL = ROOT / "intelligence.json"
DATA = ROOT / "data.json"
OUT = ROOT / "claims.json"


def main() -> None:
    intelligence = json.loads(INTEL.read_text(encoding="utf-8"))
    items = json.loads(DATA.read_text(encoding="utf-8"))
    if isinstance(items, dict):
        items = items.get("items") or items.get("data") or []
    items = items if isinstance(items, list) else []
    by_id = {str(x.get("id")): x for x in items if isinstance(x, dict) and x.get("id") is not None}

    events = []
    total_claims = 0
    total_cross_checked = 0
    for event in intelligence.get("events", []):
        article_ids = [str(x) for x in (event.get("article_ids") or [])]
        evidence_items = [by_id[x] for x in article_ids if x in by_id]
        result = build_claims(evidence_items, event)
        for claim in result.get("claims", []):
            claim["event_id"] = event.get("event_id")
        events.append({
            "event_id": event.get("event_id"),
            "coverage": result.get("coverage", 0),
            "cross_checked": result.get("cross_checked", 0),
            "unsupported": result.get("unsupported", 0),
            "claims": result.get("claims", []),
        })
        total_claims += len(result.get("claims", []))
        total_cross_checked += int(result.get("cross_checked", 0) or 0)

    payload = {
        "version": 1,
        "generated_from": "intelligence.json + data.json",
        "event_count": len(events),
        "claim_count": total_claims,
        "cross_checked_claim_count": total_cross_checked,
        "events": events,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Claims artifact: events={len(events)} claims={total_claims} cross_checked={total_cross_checked}")


if __name__ == "__main__":
    main()
