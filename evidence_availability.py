#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Translate input freshness into evidence-availability metadata without changing business decisions."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRESHNESS = ROOT / "freshness.json"
OUTPUT = ROOT / "evidence_availability.json"


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def build_availability(freshness: dict) -> dict:
    status = freshness.get("status")
    coverage = float(freshness.get("date_coverage") or 0.0)
    stale = freshness.get("stale") is True

    if status == "unavailable":
        level, reason = "unavailable", "输入数据缺失，不能把缺失观测当作证据充足"
    elif stale:
        level, reason = "low", "输入数据超过新鲜度阈值，当前证据可能已滞后"
    elif status == "undated" or coverage < 0.5:
        level, reason = "low", "日期覆盖不足，无法可靠判断时间有效性"
    elif coverage < 0.8:
        level, reason = "medium", "部分输入缺少可验证日期"
    else:
        level, reason = "high", "输入数据具备足够日期覆盖且未被判定为过期"

    return {
        "version": 1,
        "level": level,
        "reason": reason,
        "freshness_status": status or "unknown",
        "date_coverage": round(coverage, 4),
        "stale": stale,
        "principle": "证据可用性只描述输入质量；不直接改变事实、Trust、Decision 或 Urgency",
    }


def main() -> None:
    result = build_availability(_load(FRESHNESS))
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Evidence availability: level={result['level']}")


if __name__ == "__main__":
    main()
