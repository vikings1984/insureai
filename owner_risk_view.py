#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Turn daily risk radar items into human owner views without executing actions."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

DEFAULT_OWNER_BY_ACTION = {
    "evidence_refresh": ["risk_intelligence_owner"],
    "exposure_mapping": ["portfolio_risk_owner", "operations_owner"],
    "trigger_thresholds": ["governance_owner"],
}


def _load(name: str, default):
    path = ROOT / name
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _readiness_by_key(readiness: dict) -> dict:
    result = {}
    for row in readiness.get("results", []) or []:
        if not isinstance(row, dict):
            continue
        event_id = str(row.get("event_id") or "")
        action_id = str(row.get("action_id") or "")
        if event_id and action_id:
            result[(event_id, action_id)] = row
    return result


def _readiness_by_event(readiness: dict) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for row in readiness.get("results", []) or []:
        if not isinstance(row, dict):
            continue
        event_id = str(row.get("event_id") or "")
        if event_id:
            result.setdefault(event_id, []).append(row)
    return result


def _resolve_readiness(item: dict, by_key: dict, by_event: dict[str, list[dict]]) -> dict | None:
    event_id = str(item.get("event_id") or "")
    action_id = str(item.get("action_id") or "")
    direct = by_key.get((event_id, action_id))
    if direct:
        return direct
    candidates = by_event.get(event_id, [])
    if len(candidates) == 1:
        return candidates[0]
    return None


def _next_step(item: dict, readiness: dict | None) -> str:
    if readiness:
        deliverables = readiness.get("deliverables") or []
        if deliverables:
            return f"human review: complete {deliverables[0]}"
    reasons = item.get("reasons") or []
    if "human_review" in reasons:
        return "review queue: confirm evidence and disposition"
    if "optimization_backlog" in reasons or "regressed" in reasons:
        return "quality review: inspect module regression and verify fix evidence"
    if "change_impact" in reasons:
        return "impact review: inspect changed downstream judgments"
    return "review context and confirm next action"


def build_owner_view(radar: dict | None = None, readiness: dict | None = None) -> dict:
    radar = _load("daily_risk_radar.json", {}) if radar is None else radar
    readiness = _load("execution_readiness.json", {}) if readiness is None else readiness
    readiness_by_key = _readiness_by_key(readiness)
    readiness_by_event = _readiness_by_event(readiness)

    items = []
    for rank, item in enumerate(radar.get("items", []) or [], start=1):
        if not isinstance(item, dict):
            continue
        event_id = str(item.get("event_id") or "")
        action_id = str(item.get("action_id") or "")
        ready = _resolve_readiness(item, readiness_by_key, readiness_by_event)
        resolved_action = str((ready or {}).get("action_id") or action_id)
        owners = (ready or {}).get("owner_roles") or DEFAULT_OWNER_BY_ACTION.get(resolved_action, ["risk_review_owner"])
        deadline = (ready or {}).get("deadline") or "next_review_cycle"
        items.append({
            "rank": rank,
            "event_id": event_id,
            "action_id": resolved_action or None,
            "title": item.get("title") or event_id,
            "attention_score": int(item.get("attention_score") or 0),
            "urgency": item.get("urgency"),
            "trust_level": item.get("trust_level"),
            "owners": owners,
            "deadline": deadline,
            "next_step": _next_step(item, ready),
            "reasons": item.get("reasons") or [],
            "source": item.get("source"),
            "automation": "advisory_only",
            "approval_boundary": (ready or {}).get("approval_boundary") or "human confirmation required",
        })

    return {
        "version": 1,
        "principle": "负责人视图只组织已有信号，不创建责任、不执行行动、不改变风险判断。",
        "item_count": len(items),
        "items": items[:30],
    }


def main() -> None:
    result = build_owner_view()
    (ROOT / "owner_risk_view.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Owner risk view: {result['item_count']} items")


if __name__ == "__main__":
    main()
