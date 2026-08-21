#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Turn module-health trends into a deduplicated engineering optimization backlog."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TREND = ROOT / "module_health_trend.json"
OUTPUT = ROOT / "optimization_backlog.json"

ACTIONS = {
    "event": "review clustering and entity-resolution rules",
    "trust": "review source independence, conflict detection, and evidence weighting",
    "claims": "review claim extraction and evidence matching coverage",
    "temporal": "review date normalization, trend windows, and momentum thresholds",
    "decision": "review urgency guardrails and role-specific action mapping",
    "counterfactual": "review sensitivity checks and dependency attribution",
    "scenario": "review assumption boundaries and scenario evidence grounding",
    "unknown": "triage unclassified review feedback and improve attribution vocabulary",
}


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _priority(row: dict) -> tuple[int, str]:
    direction = row.get("direction")
    health = row.get("health")
    error_rate = float(row.get("error_rate") or 0.0)
    confidence = float(row.get("confidence") or 0.0)
    score = int(row.get("priority") or 0)
    if direction == "worsening":
        score += 25
    if health == "critical":
        score += 15
    if error_rate >= 0.5:
        score += 10
    if confidence < 0.6:
        score -= 5
    return max(0, min(100, score)), direction or "baseline"


def build_backlog(trend: dict | None = None) -> dict:
    trend = trend if trend is not None else _load(TREND)
    items = []
    for module, row in (trend.get("modules", {}) or {}).items():
        if not isinstance(row, dict):
            continue
        direction = row.get("direction")
        if direction not in {"worsening", "baseline"} and row.get("health") not in {"critical", "watch"}:
            continue
        priority, direction = _priority(row)
        fingerprint = hashlib.sha256(
            f"{module}|{direction}|{round(float(row.get('error_rate') or 0.0),4)}".encode("utf-8")
        ).hexdigest()[:16]
        items.append({
            "backlog_id": f"quality-{module}-{fingerprint}",
            "module": module,
            "priority": priority,
            "direction": direction,
            "health": row.get("health", "no_signal"),
            "error_rate": row.get("error_rate", 0.0),
            "error_rate_delta": row.get("error_rate_delta"),
            "optimization_action": ACTIONS.get(module, ACTIONS["unknown"]),
            "source": "module_health_trend",
            "automation": "advisory_only",
            "dedupe_key": f"{module}:{direction}",
        })
    items.sort(key=lambda x: (x["priority"], x["module"]), reverse=True)
    return {
        "version": 1,
        "principle": "质量趋势只生成内部优化建议，不直接改变线上判断或创建外部任务",
        "baseline_available": bool(trend.get("baseline_available")),
        "items": items[:50],
    }


def main() -> None:
    result = build_backlog()
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Optimization backlog: {len(result['items'])} items")


if __name__ == "__main__":
    main()
