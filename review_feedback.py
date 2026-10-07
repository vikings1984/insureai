#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0-1 Review Feedback Channel（Event OS 第八阶段「Decision Learning OS」）。

**为什么这是第八阶段第一优先**：在此之前，反馈闭环在代码层面**根本不存在**——
`review_decision_engine.py` 只输出建议（`suggested_action` / `reason`），
`grep accepted|rejected|feedback` 零命中，人无法在系统内表达「同意/否决/修正」。
于是「建议 → 反馈 → gold → 校准 → 逐步放开自动化」这条链跑不起来，
Decision Learning OS 只有一个「Learning」的名字，没有 Learning 的机制。

本模块补上**反馈采集层**（第八阶段数据飞轮的入口）：

    review_decision.json（建议）
              ↓
    review_feedback.json（本模块：人工反馈账本）
              ↓
    建议准确率报告（按 tier：accept/reject/modify/defer 分布）

**范式复用**：沿用 `scripts/promote_real_v2_candidates.py` 已验证的
「`pending_human` → 人���approve/reject` → 显式 apply；**永不自动验证**」纪律，
不另造一套人工确认口径。

**纪律**：
- 反馈只记录「人怎么判」，**系统不据此自动改变任何 review item 状态**；
- 未登记 = 未知，**不推断、不补默认值**；
- 建议准确率在样本 < MIN_SAMPLE 时`concluded=False`（同项目 P1-4/P1-8 纪律）；
- 本模块**不放开**任何自动处置（阈值校准只出报告，见 P0-4）。

用法::

    python3 review_feedback.py           # 汇总 review_feedback.json 并打印准确率
    python3 review_feedback.py --json
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DECISION = os.path.join(HERE, "review_decision.json")
# 输入账本：人工登记写入（capture 脚本追加 registrations），**本模块只读不覆写**
FEEDBACK = os.path.join(HERE, "review_feedback.json")
# 输出报告：本模块生成的准确率汇总
REPORT = os.path.join(HERE, "review_feedback_report.json")
SUMMARY = os.path.join(HERE, "review_feedback_summary.json")

VERSION = "review-feedback-v1.0"
MIN_SAMPLE = 30
SUMMARY = os.path.join(HERE, "review_feedback_summary.json")

# 人工反馈取值
DECISIONS = {"accept", "reject", "modify", "defer"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read(path: str):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def load_feedback() -> dict:
    doc = _read(FEEDBACK) or {}
    doc.setdefault("registrations", [])
    return doc


def record(feedback: dict, event_id: str, decision: str,
           modified_action: str | None = None, reason: str | None = None,
           at: str | None = None) -> dict:
    """登记一条人工反馈（同event_id 覆盖为最新一条，保留 decision 历史语义）。"""
    if decision not in DECISIONS:
        raise ValueError(f"非法 decision：{decision}（允许 {sorted(DECISIONS)}）")
    row = {
        "event_id": event_id,
        "decision": decision,
        "modified_action": modified_action,
        "reason": reason,
        "at": at or _now(),
    }
    regs = feedback["registrations"]
    for i, r in enumerate(regs):
        if r.get("event_id") == event_id:      # 同一事件以最新登记为准
            regs[i] = row
            break
    else:
        regs.append(row)
    return row


def build(decision_doc: dict | None = None, feedback: dict | None = None) -> dict:
    """把「建议」与「人工反馈」对账，产出按 tier 的建议准确率。"""
    decision_doc = decision_doc if decision_doc is not None else (_read(DECISION) or {})
    feedback = feedback if feedback is not None else load_feedback()
    fb_map = {r.get("event_id"): r for r in (feedback.get("registrations") or [])
              if isinstance(r, dict) and r.get("event_id")}

    # 建议侧索引：event_id -> (tier, suggested_action)
    sugg: dict[str, tuple[str, str]] = {}
    for group in decision_doc.get("presentation") or []:
        for it in group.get("items") or []:
            if it.get("event_id"):
                sugg[it["event_id"]] = (it.get("tier"), it.get("suggested_action"))

    # 对账：只统计「有建议且有反馈」的事件
    by_tier: dict[str, dict[str, int]] = {}
    matched: list[dict] = []
    for eid, fb in fb_map.items():
        if eid not in sugg:
            continue  # 无对应建议（如历史项），不计入准确率
        tier, action = sugg[eid]
        d = fb.get("decision")
        b = by_tier.setdefault(tier, {"accept": 0, "reject": 0, "modify": 0,
                                      "defer": 0, "total": 0})
        if d in DECISIONS:
            b[d] += 1
            b["total"] += 1
        matched.append({
            "event_id": eid, "tier": tier, "suggested_action": action,
            "decision": d, "modified_action": fb.get("modified_action"),
            "reason": fb.get("reason"), "at": fb.get("at"),
        })

    # 准确率 = accept / total（modify 视为部分采纳，不计入分子；defer 表示暂不判）
    metrics: dict[str, dict] = {}
    for tier, b in sorted(by_tier.items()):
        total = b["total"]
        metrics[tier] = {
            "total": total,
            "accept": b["accept"], "reject": b["reject"],
            "modify": b["modify"], "defer": b["defer"],
            "accept_rate": round(b["accept"] / total, 4) if total else None,
            "concluded": total >= MIN_SAMPLE,
        }

    total_fb = sum(m["total"] for m in metrics.values())
    return {
        "version": VERSION,
        "generated_at": _now(),
        "principle": "反馈只记录人怎么判；系统不据此自动改状态、不放开自动化。"
                     "未登记=未知；样本<30 不结论。",
        "meta": {
            "suggestions_available": len(sugg),
            "feedback_registered": len(fb_map),
            "feedback_matched": len(matched),
            "unmatched_feedback": len(fb_map) - len(matched),
            "min_sample": MIN_SAMPLE,
            "concluded": total_fb >= MIN_SAMPLE,
            "auto_action_enabled": False,      # 永不在本阶段放开
            "note": "建议准确率是阈值校准的唯一数据来源（P0-4 只出报告）",
        },
        "by_tier": metrics,
        "records": matched,
        "open_questions": [{
            "dimension": "建议准确率样本量",
            "status": "awaiting_human_input" if total_fb < MIN_SAMPLE else "ok",
            "reason": f"{total_fb} 条已对账（目标 {MIN_SAMPLE} 条才让接受率有结论意义）",
            "unblock": "在 review_feedback.json 持续登记人工反馈",
        }],
    }


def validate(doc: dict) -> None:
    """fail-closed：计数自洽+ 不得声称放开自动处置。"""
    if doc.get("meta", {}).get("auto_action_enabled"):
        raise ValueError("本阶段禁止开启 auto_action_enabled")
    for tid, m in (doc.get("by_tier") or {}).items():
        if m["accept"] + m["reject"] + m["modify"] + m["defer"] != m["total"]:
            raise ValueError(f"tier {tid} 反馈计数不自洽")
        if m["concluded"] and m["total"] < doc["meta"]["min_sample"]:
            raise ValueError(f"tier {tid} 样本不足却标记 concluded")


def main(argv: list[str]) -> int:
    doc = build()
    validate(doc)
    # 落盘：完整报告 + 供阈值校准读取的摘要（**不覆写输入账本 FEEDBACK**）
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")
    summary = {"version": doc["version"], "generated_at": doc["generated_at"],
               "meta": doc["meta"], "by_tier": doc["by_tier"]}
    with open(SUMMARY, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
        f.write("\n")
    if "--json" in argv:
        print(json.dumps(doc, ensure_ascii=False, indent=2))
        return 0
    m = doc["meta"]
    print(f"[review_feedback] suggestions={m['suggestions_available']} "
          f"registered={m['feedback_registered']} matched={m['feedback_matched']} "
          f"concluded={m['concluded']} auto_action={m['auto_action_enabled']}")
    for tier, s in (doc.get("by_tier") or {}).items():
        print(f"  {tier:18} total={s['total']:3d} accept={s['accept']} "
              f"reject={s['reject']} modify={s['modify']} "
              f"accept_rate={s['accept_rate']} concluded={s['concluded']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))