#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Detect downstream intelligence changes between the previous build and current build."""
from __future__ import annotations
import json
import subprocess
from pathlib import Path
from contract import ARTIFACT_VERSIONS

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "change_impact.json"


def _load_json_text(text):
    try:
        value = json.loads(text or "{}")
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def load_baseline(path: str = "intelligence.json"):
    try:
        previous = subprocess.check_output(
            ["git", "show", f"HEAD:{path}"], text=True, stderr=subprocess.DEVNULL
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {}
    return _load_json_text(previous)


def _event_map(doc):
    return {str(row.get("event_id")): row for row in doc.get("events", []) if row.get("event_id")}


def _dict(row, key):
    value = row.get(key, {}) if isinstance(row, dict) else {}
    return value if isinstance(value, dict) else {}


def compare_intelligence(previous: dict, current: dict) -> dict:
    old, new = _event_map(previous), _event_map(current)
    impacts = []
    for event_id in sorted(set(old) | set(new)):
        before, after = old.get(event_id), new.get(event_id)
        if before is None or after is None:
            impacts.append({"event_id": event_id, "impact": "event_set_changed", "risk": "medium"})
            continue
        changes = []
        bd, ad = _dict(before, "decision"), _dict(after, "decision")
        bt, at = _dict(before, "trust"), _dict(after, "trust")
        bm, am = _dict(before, "temporal"), _dict(after, "temporal")
        for field, left, right in (
            ("decision.urgency", bd.get("urgency"), ad.get("urgency")),
            ("trust.level", bt.get("level"), at.get("level")),
            ("temporal.phase", bm.get("phase"), am.get("phase")),
        ):
            if left != right:
                changes.append({"field": field, "from": left, "to": right})
        if not changes:
            continue
        urgency_rank = {"watch": 0, "soon": 1, "now": 2}
        trust_rank = {"low": 0, "medium": 1, "high": 2}
        from_u, to_u = urgency_rank.get(bd.get("urgency"), 0), urgency_rank.get(ad.get("urgency"), 0)
        from_t, to_t = trust_rank.get(bt.get("level"), 1), trust_rank.get(at.get("level"), 1)
        risk = "high" if to_u > from_u else "medium" if to_t < from_t else "low"
        impacts.append({"event_id": event_id, "impact": "judgement_changed", "risk": risk, "changes": changes})
    return {
        "version": ARTIFACT_VERSIONS["change_impact.json"],
        "baseline_available": bool(previous),
        "impacted_events": impacts,
        "impacted_count": len(impacts),
    }


def build_impact() -> dict:
    current_path = ROOT / "intelligence.json"
    current = _load_json_text(current_path.read_text(encoding="utf-8")) if current_path.exists() else {}
    previous = load_baseline()
    return compare_intelligence(previous, current)


def main():
    result = build_impact()
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Change impact: {result['impacted_count']} impacted events; baseline={result['baseline_available']}")


if __name__ == "__main__":
    main()
