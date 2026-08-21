#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Detect decision churn without changing the underlying decision."""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
HISTORY = ROOT / "decision_history.json"
OUTPUT = ROOT / "decision_stability.json"
MAX_SNAPSHOTS = 90
WINDOW = 5
RANK = {"watch": 0, "soon": 1, "now": 2}


def _snapshot(decisions: list[dict]) -> dict:
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "decisions": [
            {
                "event_id": d.get("event_id"),
                "urgency": d.get("urgency"),
                "trust_level": (d.get("basis") or {}).get("trust_level"),
                "temporal_phase": (d.get("basis") or {}).get("temporal_phase"),
                "intelligence_score": (d.get("basis") or {}).get("intelligence_score", 0),
            }
            for d in decisions
        ],
    }


def _load_history() -> dict:
    if not HISTORY.exists():
        return {"version": 1, "snapshots": []}
    try:
        data = json.loads(HISTORY.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("snapshots"), list):
            return {"version": 1, "snapshots": []}
        return {"version": 1, "snapshots": data["snapshots"][-MAX_SNAPSHOTS:]}
    except Exception:
        return {"version": 1, "snapshots": []}


def _meaningful_change(previous: dict, current: dict) -> bool:
    score_delta = abs(int(current.get("intelligence_score", 0)) - int(previous.get("intelligence_score", 0)))
    return (
        previous.get("trust_level") != current.get("trust_level")
        or previous.get("temporal_phase") != current.get("temporal_phase")
        or score_delta >= 8
    )


def build_stability(history: dict, current_decisions: list[dict]) -> dict:
    snapshots = list(history.get("snapshots") or [])
    prior = snapshots[-WINDOW + 1 :]
    current = _snapshot(current_decisions)
    event_series: dict[str, list[dict]] = {}
    for snap in prior + [current]:
        for row in snap.get("decisions", []):
            eid = str(row.get("event_id") or "")
            if eid:
                event_series.setdefault(eid, []).append(row)
    results = []
    for event_id, rows in event_series.items():
        changes = sum(1 for a, b in zip(rows, rows[1:]) if a.get("urgency") != b.get("urgency"))
        meaningful = sum(1 for a, b in zip(rows, rows[1:]) if _meaningful_change(a, b))
        oscillating = len(rows) >= 3 and rows[-1].get("urgency") == rows[-3].get("urgency") and rows[-1].get("urgency") != rows[-2].get("urgency")
        churn_rate = round(changes / max(len(rows) - 1, 1), 4)
        if len(rows) < 3:
            status = "baseline"
        elif oscillating and changes >= 2 and meaningful < changes:
            status = "jitter"
        elif changes >= 2 and meaningful >= changes:
            status = "responsive"
        elif changes:
            status = "changed"
        else:
            status = "stable"
        results.append({
            "event_id": event_id,
            "status": status,
            "window": len(rows),
            "urgency_changes": changes,
            "meaningful_changes": meaningful,
            "churn_rate": churn_rate,
            "oscillating": oscillating,
            "note": "稳定性只描述输出变化，不修改原始决策。" if status != "jitter" else "检测到可能由轻微输入波动造成的判断抖动，建议人工复核。",
        })
    return {
        "version": 1,
        "window": WINDOW,
        "principle": "只有与证据/趋势实质变化相匹配的判断变化才视为响应；反复来回切换且缺乏实质证据变化时标记为抖动。",
        "results": sorted(results, key=lambda x: (x["status"] == "jitter", x["churn_rate"]), reverse=True)[:500],
        "current_snapshot": current,
    }


def main() -> None:
    intelligence = json.loads((ROOT / "intelligence.json").read_text(encoding="utf-8"))
    history = _load_history()
    result = build_stability(history, intelligence.get("decisions", []))
    snapshots = (history.get("snapshots") or []) + [result["current_snapshot"]]
    snapshots = snapshots[-MAX_SNAPSHOTS:]
    HISTORY.write_text(json.dumps({"version": 1, "snapshots": snapshots}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Decision stability: {len(result['results'])} events")


if __name__ == "__main__":
    main()
