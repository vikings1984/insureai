#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P1-4 Human Review State Machine：人工复核状态机（零依赖）。

review.py 原先只把队列项一律置为 ``pending``，且每次 CI 重跑都会重新生成队列，
导致人工复核进展（已指派 / 已裁决 / 已升级）被覆盖丢失。本模块把复核生命周期
产品化为显式状态机：

状态（STATES）::

    pending ──> assigned ──> in_review ──> approved ──> resolved
       │            │            │             │
       │            │            ├──> rejected ──> resolved
       │            │            ├──> escalated ──┘
       │            │            └──> deferred
       └──> deferred / escalated / rejected

- ``resolved`` 为唯一终态；``approved`` / ``rejected`` 可归档为 ``resolved``，
  也可退回 ``in_review`` 重新裁决（纠错重开）。
- 每次转移都写入审计流（``from`` / ``to`` / ``actor`` / ``reason`` / ``at``），
  非法转移被拒绝且不改变状态（fail-closed，宁可不动也不产生脏状态）。
- 状态持久化在 ``review_state.json``；``sync_items()`` 保证每日重建队列时
  **已有项的状态与历史被继承**，仅新项初始化为 ``pending``。

用法（CLI）::

    python3 review_state.py list [--status pending]
    python3 review_state.py show <item_id>
    python3 review_state.py transition <item_id> <to> --actor vikings --reason "..."
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(HERE, "review_state.json")

STATE_VERSION = "1.0"

PENDING = "pending"
ASSIGNED = "assigned"
IN_REVIEW = "in_review"
APPROVED = "approved"
REJECTED = "rejected"
ESCALATED = "escalated"
DEFERRED = "deferred"
RESOLVED = "resolved"

STATES = (PENDING, ASSIGNED, IN_REVIEW, APPROVED, REJECTED, ESCALATED, DEFERRED, RESOLVED)

# 唯一终态：不可再转移
TERMINAL_STATES = frozenset({RESOLVED})

# 合法转移表（from -> 允许的 to 集合）；不在表中的转移一律拒绝
TRANSITIONS = {
    PENDING: {ASSIGNED, IN_REVIEW, DEFERRED, ESCALATED, REJECTED},
    ASSIGNED: {IN_REVIEW, PENDING, DEFERRED, ESCALATED},
    IN_REVIEW: {APPROVED, REJECTED, ESCALATED, DEFERRED},
    ESCALATED: {ASSIGNED, IN_REVIEW, APPROVED, REJECTED},
    DEFERRED: {PENDING, ASSIGNED, IN_REVIEW},
    APPROVED: {RESOLVED, IN_REVIEW},
    REJECTED: {RESOLVED, IN_REVIEW},
    RESOLVED: set(),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def can_transition(src: str, dst: str) -> bool:
    """判定 src -> dst 是否为合法转移。未知状态一律不可转移。"""
    if src not in STATES or dst not in STATES:
        return False
    return dst in TRANSITIONS.get(src, set())


def allowed_transitions(src: str) -> set[str]:
    return set(TRANSITIONS.get(src, set()))


def new_state() -> dict:
    return {"version": STATE_VERSION, "items": {}}


def load_state(path: str | None = None) -> dict:
    p = path or STATE_PATH
    if not os.path.exists(p):
        return new_state()
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return new_state()
    if not isinstance(data, dict) or not isinstance(data.get("items"), dict):
        return new_state()
    data.setdefault("version", STATE_VERSION)
    return data


def save_state(state: dict, path: str | None = None) -> None:
    p = path or STATE_PATH
    with open(p, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")


def init_item(status: str = PENDING, at: str | None = None) -> dict:
    return {
        "status": status,
        "history": [],
        "created_at": at or _now(),
        "updated_at": at or _now(),
    }


def sync_items(state: dict, items: list[dict], at: str | None = None) -> dict:
    """把队列项与已有状态合并：新项初始化为 pending，已有项保留状态与历史。

    同时把真实 status / 最近一次更新时间写回每个 item，供 UI 与下游消费。
    这是「每日重建队列不丢人工进展」的关键。
    """
    now = at or _now()
    items_map = state.setdefault("items", {})
    for item in items:
        item_id = str(item.get("event_id") or item.get("id") or "").strip()
        if not item_id:
            continue
        rec = items_map.get(item_id)
        if not isinstance(rec, dict):
            rec = init_item(PENDING, now)
            items_map[item_id] = rec
        rec.setdefault("status", PENDING)
        if rec["status"] not in STATES:
            rec["status"] = PENDING
        rec.setdefault("history", [])
        rec.setdefault("created_at", now)
        rec.setdefault("updated_at", now)
        # 写回队列项
        item["status"] = rec["status"]
        item["review_updated_at"] = rec.get("updated_at")
        item["review_history_count"] = len(rec.get("history", []))
    return state


def transition(state: dict, item_id: str, to: str, actor: str = "",
               reason: str = "", at: str | None = None) -> tuple[bool, str]:
    """执行一次状态转移。返回 (ok, error)；非法转移不改变状态（fail-closed）。"""
    item_id = str(item_id or "").strip()
    if not item_id:
        return False, "missing_item_id"
    if to not in STATES:
        return False, f"unknown_state:{to}"
    items_map = state.setdefault("items", {})
    rec = items_map.get(item_id)
    if rec is None:
        return False, "item_not_found"
    src = rec.get("status", PENDING)
    if not can_transition(src, to):
        allowed = sorted(allowed_transitions(src))
        return False, (
            f"illegal_transition:{src}->{to}"
            + (f" (allowed: {','.join(allowed) or 'none, terminal'})")
        )
    now = at or _now()
    rec.setdefault("history", []).append({
        "from": src,
        "to": to,
        "actor": actor or "",
        "reason": reason or "",
        "at": now,
    })
    rec["status"] = to
    rec["updated_at"] = now
    rec["last_actor"] = actor or ""
    return True, ""


def apply_transition(item_id: str, to: str, actor: str = "", reason: str = "",
                     path: str | None = None) -> tuple[bool, str]:
    """load -> transition -> save 的便捷封装（仅在成功时落盘）。"""
    state = load_state(path)
    ok, err = transition(state, item_id, to, actor, reason)
    if ok:
        save_state(state, path)
    return ok, err


def status_of(state: dict, item_id: str) -> str:
    rec = state.get("items", {}).get(str(item_id))
    return rec.get("status", PENDING) if isinstance(rec, dict) else PENDING


def history_of(state: dict, item_id: str) -> list[dict]:
    rec = state.get("items", {}).get(str(item_id))
    return list(rec.get("history", [])) if isinstance(rec, dict) else []


def items_with_status(state: dict, status: str) -> list[str]:
    """返回处于指定状态的 item_id 列表（保持稳定顺序）。"""
    return [k for k, v in state.get("items", {}).items()
            if isinstance(v, dict) and v.get("status") == status]


def approved_reviews(state: dict) -> list[str]:
    """已通过或已闭环的复核项（供后续 promote 到回归语料）。"""
    return [k for k, v in state.get("items", {}).items()
            if isinstance(v, dict) and v.get("status") in {APPROVED, RESOLVED}]


def main(argv: list[str]) -> int:
    if not argv or argv[0] == "list":
        status = None
        if "--status" in argv:
            idx = argv.index("--status")
            if idx + 1 < len(argv):
                status = argv[idx + 1]
        state = load_state()
        rows = []
        for item_id, rec in state.get("items", {}).items():
            if status and rec.get("status") != status:
                continue
            rows.append({
                "item_id": item_id,
                "status": rec.get("status"),
                "updated_at": rec.get("updated_at"),
                "transitions": len(rec.get("history", [])),
            })
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    if argv[0] == "show":
        if len(argv) < 2:
            print("usage: review_state.py show <item_id>", file=sys.stderr)
            return 2
        state = load_state()
        print(json.dumps({
            "item_id": argv[1],
            "status": status_of(state, argv[1]),
            "history": history_of(state, argv[1]),
        }, ensure_ascii=False, indent=2))
        return 0
    if argv[0] == "transition":
        if len(argv) < 3:
            print("usage: review_state.py transition <item_id> <to> [--actor X] [--reason Y]",
                  file=sys.stderr)
            return 2
        item_id, to = argv[1], argv[2]
        actor, reason = "", ""
        for flag, key in (("--actor", "actor"), ("--reason", "reason")):
            if flag in argv:
                idx = argv.index(flag)
                if idx + 1 < len(argv):
                    if key == "actor":
                        actor = argv[idx + 1]
                    else:
                        reason = argv[idx + 1]
        ok, err = apply_transition(item_id, to, actor, reason)
        if not ok:
            print(f"REFUSED: {err}", file=sys.stderr)
            return 1
        print(f"OK: {item_id} -> {to}")
        return 0
    print("usage: review_state.py [list|show|transition] ...", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
