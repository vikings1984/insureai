#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compare module-health snapshots over time without changing live decisions."""
from __future__ import annotations

import json
from pathlib import Path
from contract import ARTIFACT_VERSIONS

ROOT = Path(__file__).resolve().parent
CURRENT = ROOT / "module_health.json"
HISTORY = ROOT / "module_health_history.json"
OUTPUT = ROOT / "module_health_trend.json"


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _snapshot(doc: dict) -> dict[str, dict]:
    rows = doc.get("modules", [])
    if isinstance(rows, dict):
        rows = list(rows.values())
    result: dict[str, dict] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not row.get("module"):
            continue
        result[str(row["module"])] = {
            "error_rate": float(row.get("error_rate") or 0.0),
            "health": row.get("health", "no_signal"),
            "priority": int(row.get("optimization_priority") or 0),
        }
    return result


def build_trend(current: dict | None = None, history: dict | None = None) -> dict:
    current = current if current is not None else _load(CURRENT)
    history = history if history is not None else _load(HISTORY)
    current_rows = _snapshot(current)
    snapshots = history.get("snapshots", []) if isinstance(history, dict) else []
    previous = snapshots[-1].get("modules", {}) if snapshots and isinstance(snapshots[-1], dict) else {}
    if not isinstance(previous, dict):
        previous = {}

    modules = {}
    for module, row in current_rows.items():
        prev = previous.get(module, {}) if isinstance(previous.get(module, {}), dict) else {}
        delta = round(row["error_rate"] - float(prev.get("error_rate") or 0.0), 4) if prev else None
        if delta is None:
            direction = "baseline"
        elif delta >= 0.05:
            direction = "worsening"
        elif delta <= -0.05:
            direction = "improving"
        else:
            direction = "stable"
        modules[module] = {**row, "error_rate_delta": delta, "direction": direction}

    return {
        "version": ARTIFACT_VERSIONS["module_health_trend.json"],
        "principle": "趋势用于资源分配，不直接改变线上评分、决策或紧迫度",
        "baseline_available": bool(previous),
        "modules": modules,
    }


def append_snapshot(current: dict | None = None, history: dict | None = None) -> dict:
    current = current if current is not None else _load(CURRENT)
    history = history if history is not None else _load(HISTORY)
    snapshots = history.get("snapshots", []) if isinstance(history, dict) else []
    if not isinstance(snapshots, list):
        snapshots = []
    snapshots.append({"modules": _snapshot(current)})
    history = {"version": 1, "snapshots": snapshots[-90:]}
    return history


def main() -> None:
    current = _load(CURRENT)
    history = _load(HISTORY)
    trend = build_trend(current, history)
    OUTPUT.write_text(json.dumps(trend, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    history = append_snapshot(current, history)
    HISTORY.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Module health trend: {len(trend['modules'])} modules; baseline={trend['baseline_available']}")


if __name__ == "__main__":
    main()
