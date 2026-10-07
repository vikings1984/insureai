#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0-2 Review Decision Engine（Event OS 第七阶段「运营闭环与 Human OS」）。

问题：observability 的压缩分级已能算出「100 条 pending 里只有 22 条真正需要人判断」，
但**系统只做到"告诉你在哪"**——用户仍要手动翻 100 条，压缩没有变成减负。

本模块把压缩分级升级为**可运营的处置建议**，采用**三段式**（而非 auto-resolve）：

    ① 分层呈现：decision 级置顶、noise 默认折叠（呈现层，不改状态）
    ② 建议处置：每条给出「建议动作 + 触发理由」（建议层，**不改状态**）
    ③ 人工执行：人确认后才改状态，记录 resolved_by=human（执行层，人才改状态）

**为什么不 auto-resolve（重要纪律）**：
- 分档依据是启发式阈值（COMPRESS_* / priority≥50），**这些阈值本身未经人工验证**；
- 「按阈值判为低优先」≠「确认无价值」。保险场景中一条慢燃风险被自动 resolved
  会形成**静默漏斗**（不确定性被隐藏而非被解决）；
- 决策回流（decision_outcome）尚未积累样本，无法验证 auto-resolve 的正确率。
  **在没有 ground truth 时自动处置 = 把不确定性变成不可见。**

因此本模块**只出建议、不改任何 review item 状态**，与项目「不伪造、不自动决策」纪律一致。

用法::

    python3 review_decision_engine.py           # 生成 review_decision.json
    python3 review_decision_engine.py --json    # 输出 JSON
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
QUEUE = os.path.join(HERE, "review_queue.json")
OUTPUT = os.path.join(HERE, "review_decision.json")

VERSION = "review-decision-v1.0"

# 建议动作（均为「建议」，执行需人工）
SUGGEST_ACTIONS = {
    "decision_required": {"suggested_action": "human_decide", "auto_executable": False,
                          "label": "需人工裁决"},
    "material_change": {"suggested_action": "review_change", "auto_executable": False,
                        "label": "复核实质变化"},
    "relevant": {"suggested_action": "review_low_priority", "auto_executable": False,
                 "label": "一般关注"},
    "noise": {"suggested_action": "suggest_archive", "auto_executable": False,
              "label": "建议归档（低优先级 cluster）"},
}


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


def _tier_of(item: dict) -> str:
    """与 observability 同一套分档口径（保持一致，避免两处判定漂移）。"""
    from observability import (COMPRESS_DECISION_REASONS, COMPRESS_MATERIAL_REASONS,
                               COMPRESS_RELEVANT_PRIORITY, _f)
    reasons = {r.get("type") for r in (item.get("reasons") or []) if isinstance(r, dict)}
    if reasons & COMPRESS_DECISION_REASONS:
        return "decision_required"
    if (reasons & COMPRESS_MATERIAL_REASONS) or item.get("change_impact") is not None:
        return "material_change"
    if (_f(item.get("priority")) >= COMPRESS_RELEVANT_PRIORITY
            or item.get("trust_level") == "high"):
        return "relevant"
    return "noise"


def _reason_text(item: dict) -> str:
    """人可读的触发理由（说明为什么给出这个建议）。"""
    reasons = [r.get("type") for r in (item.get("reasons") or []) if isinstance(r, dict)]
    if "conflict" in reasons or "claim_conflict" in reasons:
        return "命中冲突类 reason（conflict/claim_conflict）——需人工裁决"
    if "change_impact" in reasons or item.get("change_impact") is not None:
        return "存在实质变化影响（change_impact）"
    return f"优先级 {item.get('priority')}／信任 {item.get('trust_level')}；无冲突/变化信号"


def build(queue: dict | None = None) -> dict:
    queue = queue if queue is not None else (_read(QUEUE) or {})
    items = [i for i in (queue.get("items") or []) if isinstance(i, dict)]
    pending = [i for i in items if (i.get("status") or "pending") == "pending"]

    buckets: dict[str, list[dict]] = {k: [] for k in SUGGEST_ACTIONS}
    for it in pending:
        tier = _tier_of(it)
        spec = SUGGEST_ACTIONS[tier]
        buckets[tier].append({
            "event_id": it.get("event_id"),
            "title": (it.get("title") or "")[:80],
            "tier": tier,
            "tier_label": spec["label"],
            "priority": it.get("priority"),
            "suggested_action": spec["suggested_action"],
            "auto_executable": spec["auto_executable"],   # 恒 False —— 不自动处置
            "reason": _reason_text(it),
            "status": it.get("status"),                    # 现状：未被本模块改变
        })

    # ① 呈现顺序：decision 置顶 → material → relevant → noise（noise 折叠）
    ordered_tiers = ["decision_required", "material_change", "relevant", "noise"]
    presentation = []
    for t in ordered_tiers:
        rows = sorted(buckets[t], key=lambda r: -(r.get("priority") or 0))
        presentation.append({
            "tier": t,
            "label": SUGGEST_ACTIONS[t]["label"],
            "count": len(rows),
            "default_collapsed": t == "noise",   # ① noise 默认折叠
            "items": rows,
        })

    human_load = len(buckets["decision_required"]) + len(buckets["material_change"])
    return {
        "version": VERSION,
        "generated_at": _now(),
        "principle": "三段式收敛：分层呈现(不改状态) + 建议处置(不改状态) + 人工执行(人才改状态)。"
                     "不做 auto-resolve——阈值未经人工验证，无 ground truth 时自动处置=静默漏斗。",
        "meta": {
            "queue_items": len(items),
            "pending": len(pending),
            "human_load": human_load,
            "auto_resolve_enabled": False,   # 显式声明：本阶段不做自动处置
            "note": "所有建议 auto_executable=False；状态变更须由 Human Review 侧人工执行",
        },
        "presentation": presentation,
        "open_questions": [{
            "dimension": "建议采纳率",
            "status": "awaiting_human_input",
            "reason": "尚无人工采纳/驳回记录，无法验证建议正确率",
            "unblock": "人工执行建议后回填采纳结果，样本积累再评估是否值得进一步自动化",
        }],
    }


def validate(doc: dict) -> None:
    """fail-closed：建议不得声称可自动执行；分层总数须自洽。"""
    for group in doc.get("presentation") or []:
        if group.get("count") != len(group.get("items") or []):
            raise ValueError(f"分层计数不自洽：{group.get('tier')}")
        for it in group.get("items") or []:
            if it.get("auto_executable"):
                raise ValueError("本阶段禁止 auto_executable（阈值未经验证）")
    meta = doc.get("meta") or {}
    if meta.get("auto_resolve_enabled"):
        raise ValueError("auto_resolve 必须为 False")


def main(argv: list[str]) -> int:
    doc = build()
    validate(doc)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")
    if "--json" in argv:
        print(json.dumps(doc, ensure_ascii=False, indent=2))
        return 0
    m = doc["meta"]
    print(f"[review_decision] pending={m['pending']} human_load={m['human_load']} "
          f"auto_resolve={m['auto_resolve_enabled']}")
    for g in doc["presentation"]:
        print(f"  {g['tier']:18} {g['count']:3d}  {g['label']}"
              f"{'  [默认折叠]' if g['default_collapsed'] else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))