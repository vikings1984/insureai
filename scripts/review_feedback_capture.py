#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0-1 人工反馈采集入口（Event OS 第八阶段）。

把「人的判断」从手工编辑 JSON 变成一条命令。**复用**
`scripts/promote_real_v2_candidates.py` 已验证的纪律：
人明确表态（accept/reject/modify/defer）才写入；**永不自动验证**。

写入 `review_feedback.json`（由 review_feedback.py 汇总成建议准确率）。

**边界**：本脚本**只记录人的判断**，绝不改动 review_queue / review_decision 的任何状态；
系统也不会据此自动处置（阈值校准见 P0-4，只出报告）。

用法::

    # 查看待反馈的建议（含事件内容与判断依据）
    python3 scripts/review_feedback_capture.py list
    python3 scripts/review_feedback_capture.py list --tier noise -v --limit 5

    # 登记反馈
    python3 scripts/review_feedback_capture.py accept  evt_xxx  --reason "确需裁决"
    python3 scripts/review_feedback_capture.py reject  evt_xxx  --reason "低价值cluster"
    python3 scripts/review_feedback_capture.py modify  evt_xxx  --to review_change --reason "应改为复核变化"
    python3 scripts/review_feedback_capture.py defer   evt_xxx  --reason "待更多证据"
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import review_feedback as rf  # noqa: E402

DECISION_PATH = os.path.join(ROOT, "review_decision.json")
QUEUE_PATH = os.path.join(ROOT, "review_queue.json")


def _load_json(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _review_items() -> dict:
    """review_queue 的 event_id -> item（提供人工判断所需的上下文）。"""
    doc = _load_json(QUEUE_PATH) or {}
    return {i.get("event_id"): i for i in (doc.get("items") or [])
            if isinstance(i, dict) and i.get("event_id")}


def _load_ledger() -> dict:
    """读取反馈账本；`REVIEW_FEEDBACK_LEDGER` 可重定向（测试/演练隔离）。"""
    path = os.environ.get("REVIEW_FEEDBACK_LEDGER") or rf.FEEDBACK
    if not os.path.exists(path):
        return {"version": "review-feedback-v1.0", "registrations": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"version": "review-feedback-v1.0", "registrations": []}
    doc.setdefault("registrations", [])
    return doc


def _suggestions() -> list[dict]:
    doc = _load_json(DECISION_PATH) or {}
    out = []
    for g in doc.get("presentation") or []:
        for it in g.get("items") or []:
            if it.get("event_id"):
                out.append(it)
    return out


def _fmt_one(idx: int, s: dict, item: dict | None, verbose: bool) -> str:
    """把一条建议渲染成**可供人判断**的形态（含事件内容，不只是 id）。"""
    eid = s.get("event_id")
    head = f"[{idx:3d}] {eid}  [{s.get('tier')}]"
    if not verbose:
        title = (item or {}).get("title") or ""
        return f"{head} {title[:46]}"
    it = item or {}
    reasons = "；".join(
        f"{r.get('type')}" for r in (it.get("reasons") or []) if isinstance(r, dict)
    ) or "-"
    lines = [
        f"{head}",
        f"      标题   : {(it.get('title') or '-')[:70]}",
        f"      建议   : {s.get('suggested_action')}  （{s.get('reason') or '-'}）",
        f"      优先级 : {it.get('priority')}   信任: {it.get('trust_level')}   "
        f"信源数: {it.get('source_count')}   类型: {it.get('event_type') or '-'}",
        f"      触发   : {reasons[:70]}",
    ]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if not argv or argv[0] == "list":
        fb = _load_ledger()
        done = {r.get("event_id") for r in fb.get("registrations") or []}
        tier = None
        if "--tier" in argv:
            tier = argv[argv.index("--tier") + 1]
        verbose = "-v" in argv or "--verbose" in argv
        limit = 20
        if "--limit" in argv:
            try:
                limit = int(argv[argv.index("--limit") + 1])
            except (IndexError, ValueError):
                limit = 20
        rq = _review_items()
        rows = [s for s in _suggestions()
                if s.get("event_id") not in done
                and (tier is None or s.get("tier") == tier)]
        if not rows:
            print("[review_feedback_capture] 无待反馈建议（已全部登记或队列为空）")
            return 0
        print(f"[review_feedback_capture] 待反馈 {len(rows)} 条（已登记 {len(done)} 条）"
              f"{'｜按 tier=' + tier if tier else ''}")
        print("  人工判断后登记："
              "<accept|reject|modify|defer> <event_id> [--to ACTION] [--reason TEXT]\n")
        for n, s in enumerate(rows[:limit], 1):
            print(_fmt_one(n, s, rq.get(s.get("event_id")), verbose))
        if len(rows) > limit:
            print(f"\n  ... 其余 {len(rows)-limit} 条（--limit 调整；-v 看详细依据）")
        return 0

    cmd = argv[0]
    if cmd not in rf.DECISIONS:
        print(f"用法：review_feedback_capture.py list | "
              f"<{'|'.join(sorted(rf.DECISIONS))}> <event_id> [--to ACTION] [--reason TEXT]",
              file=sys.stderr)
        return 2
    if len(argv) < 2:
        print("缺少 event_id", file=sys.stderr)
        return 2
    event_id = argv[1]

    # 校验该event 确实有建议（防止登记无关项）
    known = {s["event_id"] for s in _suggestions()}
    if known and event_id not in known:
        print(f"[warn] {event_id} 不在当前建议列表中，仍将登记（可能为历史项）",
              file=sys.stderr)

    modified = None
    if "--to" in argv:
        modified = argv[argv.index("--to") + 1]
    reason = argv[argv.index("--reason") + 1] if "--reason" in argv else None

    # 账本路径：默认生产文件；`REVIEW_FEEDBACK_LEDGER` 可指向别处（测试/演练隔离用）
    ledger_path = os.environ.get("REVIEW_FEEDBACK_LEDGER") or rf.FEEDBACK
    fb = rf.load_feedback()
    try:
        row = rf.record(fb, event_id, cmd, modified_action=modified, reason=reason)
    except ValueError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 2

    with open(ledger_path, "w", encoding="utf-8") as f:
        json.dump(fb, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"[review_feedback_capture] 已登记：{event_id} -> {cmd}"
          f"{'（modified_action=' + modified + '）' if modified else ''}"
          f"  （仅记录判断，未改任何状态）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))