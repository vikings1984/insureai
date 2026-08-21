#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Detect downstream intelligence changes between a baseline and current build."""
from __future__ import annotations
import json, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "change_impact.json"

def _load_json_text(text):
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}

def _git_show(path: str):
    try:
        return subprocess.check_output(["git", "show", f"HEAD:{path}"], text=True, stderr=subprocess.DEVNULL)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

def load_baseline(path: str):
    previous = _git_show(path)
    return _load_json_text(previous) if previous is not None else {}

def _event_map(doc):
    return {str(row.get("event_id")): row for row in doc.get("events", []) if row.get("event_id")}

def _decision(row):
    value = row.get("decision", {})
    return value if isinstance(value, dict) else {}

def _trust(row):
    value = row.get("trust", {})
    return value if isinstance(value, dict) else {}

def _temporal(row):
    value = row.get("temporal", {})
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
        bd, ad = _decision(before), _decision(after)
        bt, at = _trust(before), _trust(after)
        bm, am = _temporal(before), _temporal(after)
        if bd.get("urgency") != ad.get("urgency"):
            changes.append({"field": "decision.urgency", "from": bd.get("urgency"), "to": ad.get("urgency")})
        if bt.get("level") != at.get("level"):
            changes.append({"field": "trust.level", "from": bt.get("level"), "to": at.get("level")})
        if bm.get("phase") != am.get("phase"):
            changes.append({"field": "temporal.phase", "from": bm.get("phase"), "to": am.get("phase")})
        if changes:
            urgency_rank = {"watch": 0, "soon": 1, "now": 2}
            from_u, to_u = urgency_rank.get(bd.get("urgency"), 0), urgency_rank.get(ad.get("urgency"), 0)
            trust_rank = {"low": 0, "medium": 1, "high": 2}
            from_t, to_t = trust_rank.get(bt.get("level"), 1), trust_rank.get(at.get("level"), 1)
            risk = "high" if to_u > from_u else "medium" if (to_t < from_t or to_u != from_u) else "low"
            impacts.append({"event_id": event_id, "impact": "judgement_changed", "risk": risk, "changes": changes})
    return {"version": 1, "baseline_available": bool(previous), "impacted_events": impacts, "impacted_count": len(impacts)}

def build_impact() -> dict:
    current_path = ROOT / "intelligence.json"
    current = _load_json_text(current_path.read_text(encoding="utf-8")) if current_path.exists() else {}
    previous = load_baseline("intelligence.json")
    return compare_intelligence(previous, current)

def main():
    result = build_impact()
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Change impact: {result['impacted_count']} impacted events; baseline={result['baseline_available']}")

if __name__ == "__main__": main()
