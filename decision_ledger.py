#!/usr/bin/env python3
"""E2 决策样本累计账本：跨运行按 event_id 去重累积真实决策。

为「决策样本 ≥30」与「决策时间线」提供**诚实**的积累机制：
- 只持久化引擎真实产出的 decision（含 decided_at），绝不伪造时间戳或补样本。
- 同一 event_id 只保留一行（取最新 decided_at 的决策），避免按 8 角色重复计数。
- ≥30 阈值由日常流水线持续运行自然达到；本模块只负责累计，不做结论、不输出偏好。
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
INTEL = ROOT / "intelligence.json"
OUTPUT = ROOT / "decisions_ledger.json"
MIN_SAMPLE = 30
VERSION = "ledger-v1.0"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load() -> dict:
    if not OUTPUT.exists():
        return {"version": VERSION, "entries": [], "updated_at": None}
    try:
        data = json.loads(OUTPUT.read_text(encoding="utf-8"))
    except Exception:
        return {"version": VERSION, "entries": [], "updated_at": None}
    data.setdefault("entries", [])
    return data


def _entry(d: dict) -> dict:
    return {
        "event_id": d.get("event_id"),
        "role": d.get("role"),
        "urgency": d.get("urgency"),
        "action": d.get("action"),
        "decided_at": d.get("decided_at"),
    }


def accumulate(decisions: list[dict], persist: bool = True) -> dict:
    """合并本轮决策到账本（按 event_id 去重，保留最新 decided_at）。"""
    ledger = _load()
    by_id = {e.get("event_id"): e for e in ledger.get("entries", [])}
    added = 0
    for d in decisions:
        eid = d.get("event_id")
        if not eid:
            continue
        new = _entry(d)
        existing = by_id.get(eid)
        if existing is None:
            by_id[eid] = new
            added += 1
        elif (new.get("decided_at") or "") >= (existing.get("decided_at") or ""):
            # 仅当存在更晚的 decided_at 时更新（保留最新一次决策）
            by_id[eid] = new
    entries = list(by_id.values())
    ledger = {"version": VERSION, "entries": entries, "updated_at": _now()}
    if persist:
        OUTPUT.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    distinct = len(entries)
    return {
        "version": VERSION,
        "distinct_events": distinct,
        "added_this_run": added,
        "reached_threshold": distinct >= MIN_SAMPLE,
        "min_sample": MIN_SAMPLE,
    }


def run(persist: bool = True) -> dict:
    intel = json.loads(INTEL.read_text(encoding="utf-8"))
    decisions = intel.get("decisions") or []
    return accumulate(decisions, persist=persist)


def main() -> None:
    parser = argparse.ArgumentParser(description="累计决策样本到账本（按 event_id 去重）")
    parser.add_argument("--no-persist", action="store_true", help="只计算不写文件")
    args = parser.parse_args()
    summary = run(persist=not args.no_persist)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
