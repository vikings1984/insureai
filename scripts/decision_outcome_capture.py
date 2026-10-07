#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0-2 Decision Outcome 人工登记入口（Event OS 第八阶段）。

现状问题：`decision_outcome.py` 读 `decision_outcome_input.json`，此前**只能手工编辑 JSON**——
这在 35 条量级就容易出错，且无法保证字段纪律。本脚本把登记工具化。

沿用 `scripts/promote_real_v2_candidates.py` 的纪律：人明确表态才写入，**永不自动填值**。
**只记录人的判断与真实结果**，绝不改写决策账本、不推进任何 pending 项。

写入 `decision_outcome_input.json`（由 decision_outcome.py 汇总）。

用法::

    # 查看待登记的已决决策
    python3 scripts/decision_outcome_capture.py list

    # 登记落地承诺（owner / deadline）
    python3 scripts/decision_outcome_capture.py commit evt_xxx --owner 战略部 --deadline 2026-10-31

    # 登记采纳结果
    python3 scripts/decision_outcome_capture.py adopt evt_xxx --at 2026-10-08

    # 登记最终结果（含未采纳原因）
    python3 scripts/decision_outcome_capture.py outcome evt_xxx \
        --outcome "已纳入季度资本配置讨论" --at 2026-11-15 --feedback "建议再加外汇对冲视角"
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import decision_outcome as do  # noqa: E402

LEDGER = os.path.join(ROOT, "decisions_ledger.json")


def _ledger_event_ids() -> list[str]:
    if not os.path.exists(LEDGER):
        return []
    try:
        with open(LEDGER, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    return [e.get("event_id") for e in (doc.get("entries") or [])
            if isinstance(e, dict) and e.get("event_id")]


def _flag(name: str) -> str | None:
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else None


def main(argv: list[str]) -> int:
    if not argv or argv[0] == "list":
        ids = _ledger_event_ids()
        if not ids:
            print("[decision_outcome_capture] 决策账本为空")
            return 0
        print(f"[decision_outcome_capture] 待登记已决决策 {len(ids)} 条：")
        for e in ids[:20]:
            print(f"  {e}")
        if len(ids) > 20:
            print(f"  ... 其余 {len(ids)-20} 条")
        print("  用法：commit/adopt/outcome <event_id> [--owner ...] [--outcome ...]")
        return 0

    cmd = argv[0]
    if cmd not in {"commit", "adopt", "reject", "outcome"}:
        print(f"用法：decision_outcome_capture.py list | commit|adopt|reject|outcome <event_id> "
              f"[--owner X] [--deadline D] [--outcome T] [--at T] [--feedback T]", file=sys.stderr)
        return 2
    if len(argv) < 2:
        print("缺少 event_id", file=sys.stderr)
        return 2
    event_id = argv[1]
    if event_id not in _ledger_event_ids():
        print(f"[warn] {event_id} 不在决策账本中，仍将登记", file=sys.stderr)

    doc = do._read(do.INPUT) or {"version": "outcome-input-v1.0", "registrations": []}
    doc.setdefault("registrations", [])
    # 就地更新：同一 event_id 覆盖，否则追加（保持与review_feedback.record 同一语义）
    row = None
    for r in doc["registrations"]:
        if isinstance(r, dict) and r.get("event_id") == event_id:
            row = r
            break
    if row is None:
        row = {"event_id": event_id}
        doc["registrations"].append(row)

    if cmd == "commit":
        row["owner"] = _flag("--owner")
        row["deadline"] = _flag("--deadline")
    elif cmd in {"adopt", "reject"}:
        row["adopted"] = "adopted" if cmd == "adopt" else "rejected"
        row["adopted_at"] = _flag("--at")
    else:  # outcome
        row["outcome"] = _flag("--outcome")
        row["outcome_at"] = _flag("--at")
        fb = _flag("--feedback")
        if fb:
            row["feedback"] = fb

    with open(do.INPUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"[decision_outcome_capture] 已登记 {cmd}：{event_id}（仅记录真实判断/结果）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))