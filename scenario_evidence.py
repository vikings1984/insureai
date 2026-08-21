#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Annotate scenarios with evidence vulnerability without changing support scores."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCENARIO = ROOT / "scenario.json"
AVAIL = ROOT / "evidence_availability.json"
OUTPUT = ROOT / "scenario_evidence.json"


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _vulnerability(level: str) -> tuple[str, str]:
    if level == "unavailable":
        return "critical", "输入证据不可用，情景推演缺乏当前观测支撑"
    if level == "low":
        return "high", "输入证据质量偏低，情景结论对旧数据更敏感"
    if level == "medium":
        return "medium", "部分输入日期覆盖不足，情景可执行性受限"
    if level == "high":
        return "low", "当前输入证据可用性良好"
    return "unknown", "输入证据可用性未知"


def build_scenario_evidence(scenario: dict, availability: dict) -> dict:
    level = availability.get("level", "unknown")
    vulnerability, reason = _vulnerability(level)
    rows = []
    for row in scenario.get("scenarios", []) if isinstance(scenario.get("scenarios"), list) else []:
        item = dict(row)
        item["evidence_availability"] = level
        item["vulnerability"] = vulnerability
        item["vulnerability_reason"] = reason
        item["execution_readiness"] = "blocked" if vulnerability == "critical" else ("caution" if vulnerability in {"high", "medium"} else "ready")
        item["support_level_original"] = row.get("support_level")
        rows.append(item)
    return {
        "version": 1,
        "principle": "证据质量影响情景可用性，不重写情景原始支持度，也不把情景变成预测概率。",
        "evidence_availability": availability,
        "scenario_count": len(rows),
        "scenarios": rows,
    }


def main() -> None:
    result = build_scenario_evidence(_load(SCENARIO), _load(AVAIL))
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Scenario evidence vulnerability: {result['evidence_availability'].get('level', 'unknown')}")


if __name__ == "__main__":
    main()
