#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0-1 Decision → Action → Outcome 回流（Event OS 第七阶段「运营闭环与 Human OS」）。

此前系统的决策链止于"给出建议"：
    Decision → Advisory（decision_stability / credibility / action_triggers / execution_readiness）
但**没有任何回来说明这些建议后来怎么了**——是否被采纳？谁采纳？何时？为何未采纳？结果如何？
缺了这一段，决策质量无法被验证，"学习"也无从谈起。

本模块建立**回流层**（Human OS 的 Decision 侧）：

    decision_ledger（已决，仅真实 decided_at）
              ↓
    decision_outcome.json（本模块）
      ├─ owner / action / deadline   —— 建议侧的落地承诺
      ├─ adopted / adopted_at       —— 是否真被采纳（人工登记）
      ├─ outcome / outcome_at       —— 落地结果（人工登记）
      └─ feedback                   —— 未采纳原因 / 修正意见

**纪律（与全项目一致）**：
- **不伪造**：outcome / adopted 只来自 `decision_outcome_input.json`（人工登记），
  缺失即为 null，绝不用默认值或推断值填充；
- **不自动决策**：本模块只做聚合与统计，不改写任何 decision，不推进任何 pending 项；
- **样本不足不结论**：`adoption_rate` 等结论性指标在样本 < MIN_SAMPLE 时显式标记
  `concluded=False`（同 P1-4/P1-8纪律）；
- **零依赖**：与项目其他模块一致，仅用标准库。

用法::

    python3 decision_outcome.py            # 生成 decision_outcome.json 并打印摘要
    python3 decision_outcome.py --json     # 输出 JSON
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "decisions_ledger.json")
# 人工登记入口（不存在则全部 outcome 为 null —— 这是"诚实"的默认状态）
INPUT = os.path.join(HERE, "decision_outcome_input.json")
OUTPUT = os.path.join(HERE, "decision_outcome.json")

VERSION = "outcome-v1.0"
MIN_SAMPLE = 30

# 采纳状态取值（人工登记）
ADOPTED_STATES = {"adopted", "rejected", "pending"}


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


def _registrations() -> dict[str, dict]:
    """读取人工登记的 outcome / adoption 记录，按 event_id 索引。"""
    doc = _read(INPUT) or {}
    out: dict[str, dict] = {}
    for row in doc.get("registrations") or []:
        if isinstance(row, dict) and row.get("event_id"):
            out[row["event_id"]] = row
    return out


def build(ledger: dict | None = None, regs: dict | None = None) -> dict:
    ledger = ledger if ledger is not None else (_read(LEDGER) or {})
    regs = regs if regs is not None else _registrations()
    entries = ledger.get("entries") or []

    items: list[dict] = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        eid = e.get("event_id")
        if not eid:
            continue
        r = regs.get(eid) or {}
        adopted = r.get("adopted")
        if adopted not in ADOPTED_STATES:
            adopted = None          # 未登记 = 未知，不推断
        items.append({
            "event_id": eid,
            "role": e.get("role"),
            "urgency": e.get("urgency"),
            "action": e.get("action"),
            "decided_at": e.get("decided_at"),
            # —— 落地承诺（登记侧）——
            "owner": r.get("owner"),
            "deadline": r.get("deadline"),
            # —— 采纳（登记侧）——
            "adopted": adopted,
            "adopted_at": r.get("adopted_at"),
            # —— 结果（登记侧）——
            "outcome": r.get("outcome"),
            "outcome_at": r.get("outcome_at"),
            "feedback": r.get("feedback"),
        })

    n = len(items)
    adopted = [i for i in items if i.get("adopted") == "adopted"]
    rejected = [i for i in items if i.get("adopted") == "rejected"]
    registered = [i for i in items if i.get("adopted") is not None]
    with_outcome = [i for i in items if i.get("outcome")]

    decided_n = len(adopted) + len(rejected)
    concluded = decided_n >= MIN_SAMPLE
    adoption_rate = (round(len(adopted) / decided_n, 4)
                     if decided_n else None)

    return {
        "version": VERSION,
        "generated_at": _now(),
        "principle": "Decision → Action → Outcome 回流；outcome/adopted 只来自人工登记，"
                     "缺失即 null（不伪造、不推断）；样本 <30 不结论。",
        "meta": {
            "ledger_entries": n,
            "adoption_registered": len(registered),
            "decided_with_adoption": decided_n,
            "adopted": len(adopted),
            "rejected": len(rejected),
            "with_outcome": len(with_outcome),
            "adoption_rate": adoption_rate,
            "min_sample": MIN_SAMPLE,
            "concluded": concluded,
            "note": "未登记=未知；adoption_rate 仅在 decided_with_adoption>=30 时有意义",
        },
        "items": items,
        "open_questions": [{
            "dimension": "outcome 登记覆盖率",
            "status": "awaiting_human_input" if len(with_outcome) < n else "covered",
            "reason": f"仅 {len(with_outcome)}/{n} 条已决决策有 outcome 登记",
            "unblock": "Human Review 侧持续落 outcome，样本达 30 条后结论性指标才生效",
        }],
    }


def validate(doc: dict) -> None:
    """fail-closed：结构自洽 + 不伪造（outcome 必有 outcome_at）。"""
    items = doc.get("items") or []
    for i in items:
        if i.get("outcome") and not i.get("outcome_at"):
            raise ValueError(f"outcome 缺 outcome_at（疑似伪造）：{i.get('event_id')}")
        if i.get("adopted") and i.get("adopted") not in ADOPTED_STATES:
            raise ValueError(f"非法 adopted 状态：{i.get('adopted')}")
    m = doc.get("meta") or {}
    if m.get("decided_with_adoption") != m.get("adopted", 0) + m.get("rejected", 0):
        raise ValueError("adoption 计数不自洽")
    if m.get("concluded") and m.get("decided_with_adoption", 0) < m.get("min_sample", MIN_SAMPLE):
        raise ValueError("样本不足却标记 concluded")


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
    print(f"[decision_outcome] entries={m['ledger_entries']} "
          f"registered={m['adoption_registered']} adopted={m['adopted']} "
          f"rejected={m['rejected']} with_outcome={m['with_outcome']} "
          f"adoption_rate={m['adoption_rate']} concluded={m['concluded']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
