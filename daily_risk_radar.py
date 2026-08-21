#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rank existing risk signals for daily human attention; never mutate decisions."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _load(name: str, default):
    path = ROOT / name
    if not path.exists():
        return default
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value
    except Exception:
        return default


def _urgency_score(value: str | None) -> int:
    return {"now": 40, "soon": 25, "watch": 10}.get(value, 0)


def build_radar(credibility=None, intelligence=None, impacts=None, backlog=None, review=None) -> dict:
    credibility = _load("decision_credibility.json", {}) if credibility is None else credibility
    intelligence = _load("intelligence.json", {}) if intelligence is None else intelligence
    impacts = _load("change_impact.json", {}) if impacts is None else impacts
    backlog = _load("optimization_backlog.json", {}) if backlog is None else backlog
    review = _load("review_queue.json", {}) if review is None else review

    credibility_status = credibility.get("status", "unknown")
    credibility_penalty = {"ready": 0, "review": 15, "caution": 20, "blocked": 35}.get(credibility_status, 25)
    impact_events = {str(x.get("event_id")) for x in impacts.get("impacted_events", []) if isinstance(x, dict)}

    candidates = []
    for decision in intelligence.get("decisions", []) or []:
        event_id = str(decision.get("event_id") or "")
        if not event_id:
            continue
        basis = decision.get("basis") or {}
        score = _urgency_score(decision.get("urgency"))
        if event_id in impact_events:
            score += 15
        score -= credibility_penalty
        reasons = []
        if decision.get("urgency") == "now": reasons.append("urgent")
        if event_id in impact_events: reasons.append("change_impact")
        if credibility_status in {"review", "caution", "blocked"}: reasons.append(f"credibility_{credibility_status}")
        candidates.append({
            "event_id": event_id,
            "title": decision.get("title") or event_id,
            "urgency": decision.get("urgency"),
            "trust_level": basis.get("trust_level"),
            "attention_score": max(0, min(100, score)),
            "reasons": reasons,
            "source": "intelligence.json",
        })

    for item in review.get("items", []) or []:
        if not isinstance(item, dict):
            continue
        event_id = str(item.get("event_id") or item.get("id") or "")
        if not event_id:
            continue
        candidates.append({
            "event_id": event_id,
            "title": item.get("title") or event_id,
            "urgency": item.get("urgency"),
            "trust_level": item.get("trust_level"),
            "attention_score": max(0, min(100, int(item.get("priority") or 0) + 20)),
            "reasons": ["human_review"],
            "source": "review_queue.json",
        })

    for item in backlog.get("items", []) or []:
        if not isinstance(item, dict) or item.get("status") not in {"open", "regressed"}:
            continue
        candidates.append({
            "event_id": f"module:{item.get('module', 'unknown')}",
            "title": f"模块质量：{item.get('module', 'unknown')}",
            "urgency": None,
            "trust_level": None,
            "attention_score": max(0, min(100, int(item.get("priority") or 0) + (15 if item.get("status") == "regressed" else 0))),
            "reasons": ["optimization_backlog", item.get("status")],
            "source": "optimization_backlog.json",
        })

    candidates.sort(key=lambda x: (x["attention_score"], x["event_id"]), reverse=True)
    return {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": credibility_status,
        "principle": "雷达只排序已有风险信号，不重新评分、不修改原始决策、不自动执行行动。",
        "items": candidates[:30],
        "summary": {
            "items": len(candidates),
            "top_attention_score": candidates[0]["attention_score"] if candidates else 0,
            "credibility_status": credibility_status,
            "impacted_event_count": len(impact_events),
        },
    }


def main() -> None:
    result = build_radar()
    (ROOT / "daily_risk_radar.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Daily risk radar: {len(result['items'])} items")


if __name__ == "__main__":
    main()
