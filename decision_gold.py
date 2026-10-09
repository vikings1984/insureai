#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B：一次人力两产出 —— Decision Outcome 登记**同时**产出 Decision Gold（第九阶段）。

## 为什么做这个

第八阶段拍板「先不动 resolver，用 30 条 decision 登记顺带产出 Decision gold
（**一次人力两产出**）」。原因（已实测）：
- 人工 gold 显示 resolver 的 `same_pair_agreement = 0.0`（9 对人工确认的同一事件，
  resolver 一组都没归并），但 `wrong_merge_rate = 0.0`（从未误合并）；
- 在 same 样本只有 9 个的情况下**放宽合并阈值等于盲调**；
- 因此优先补**当前最缺的真标签：决策质量**。

## 关键设计：登记 outcome 时顺手问三个问题

人在登记「是否采纳 / 结果如何」时，**本来就持有判断**——顺手记下来成本极低：

| gold 标签            | 问什么                        | 用途                      |
|----------------------|-------------------------------|---------------------------|
| `decision_was_right`  | 这个决策方向对不对？          | Decision Precision        |
| `action_was_right`    | 建议的行动对不对？            | Action Precision          |
| `should_have_acted`   | 更早/更晚/不行动是否更妥？   | Urgency Calibration       |

这三个标签**只来自人工判断**，系统不推断、不填充（沿用全项目「不伪造」纪律）。
它们汇总为 `decision_gold.json`，供 `benchmark` 的 decision 维度使用。

**与 auto-resolve 的关系**：本模块**不改变**任何 review/decision 状态，
只把人的判断固化成 gold。`auto_action_enabled` 恒False。

用法::

    # 登记 outcome（--right-decision / --right-action / --urgency-regret 顺带记 gold）
    python3 scripts/decision_outcome_capture.py outcome evt_x \
        --outcome "已纳入季度讨论" --at 2026-11-15 \
        --right-decision yes --right-actionyes --urgency-regret too_late

    python3 decision_gold.py# 汇总决策 gold 报告
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "decisions_ledger.json")
INPUT = os.path.join(HERE, "decision_outcome_input.json")
OUTPUT = os.path.join(HERE, "decision_gold.json")

VERSION = "decision-gold-v1.0"
MIN_SAMPLE = 30

# 人工可填的 gold 标签及合法值
GOLD_FIELDS = {
    "decision_was_right": {"yes", "no", "partial"},       # 决策方向是否正确
    "action_was_right": {"yes", "no", "partial"},         # 建议行动是否正确
    "urgency_regret": {"none", "too_early", "too_late", "should_not_act"},
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def build(input_doc: dict | None = None, ledger: dict | None = None) -> dict:
    """把 outcome 登记中顺带记录的人工判断，汇总为 Decision Gold。"""
    inp = input_doc if input_doc is not None else (_read(INPUT) or {})
    led = ledger if ledger is not None else (_read(LEDGER) or {})
    ledger_by_id = {e.get("event_id"): e for e in (led.get("entries") or [])
                    if isinstance(e, dict)}

    items = []
    counts = {k: 0 for k in GOLD_FIELDS}
    for r in inp.get("registrations") or []:
        if not isinstance(r, dict):
            continue
        eid = r.get("event_id")
        if not eid:
            continue
        # 只统计**人工真的填了** gold 标签的条目；未填=未知，不推断
        gold_labels = {k: r.get(k) for k in GOLD_FIELDS if r.get(k) in GOLD_FIELDS[k]}
        if not gold_labels:
            continue
        for k in gold_labels:
            counts[k] += 1
        src = ledger_by_id.get(eid, {})
        items.append({
            "event_id": eid,
            "role": src.get("role"),
            "urgency": src.get("urgency"),# 系统给的动作（被评判对象）
            "action": src.get("action"),
            "decided_at": src.get("decided_at"),
            "adopted": r.get("adopted"),
            "outcome": r.get("outcome"),
            "outcome_at": r.get("outcome_at"),
            "gold": gold_labels,
            "labeled_at": r.get("outcome_at") or r.get("at"),
        })

    labeled = len(items)

    def _rate(field: str, good: tuple) -> float | None:
        vals = [i["gold"].get(field) for i in items if i["gold"].get(field)]
        if not vals:
            return None
        return round(sum(1 for v in vals if v in good) / len(vals), 4)

    return {
        "version": VERSION,
        "generated_at": _now(),
        "principle": "一次人力两产出：登记 outcome 时顺带记录决策质量判断。"
                     "gold 标签**只来自人工**，未填=未知（不推断）；本模块不改任何业务状态。",
        "meta": {
            "labeled_samples": labeled,
            "per_field_counts": counts,
            "min_sample": MIN_SAMPLE,
            "concluded": labeled >= MIN_SAMPLE,
            "auto_action_enabled": False,      # 恒 False：本模块不放开自动化
            "note": "样本达 30 条后decision/action/urgency 三个维度才有结论意义",
        },
        "metrics": {
            # 决策正确率（只算明确 yes/no，partial 不计入分子）
            "decision_precision": _rate("decision_was_right", ("yes",)),
            "action_precision": _rate("action_was_right", ("yes",)),
            # urgency 分布：用于校准「是否太早/太晚/本不该行动」
            "urgency_regret_counts": {
                v: sum(1 for i in items if i["gold"].get("urgency_regret") == v)
                for v in sorted(GOLD_FIELDS["urgency_regret"])
            },
        },
        "items": items,
        "open_questions": [{
            "dimension": "决策 gold 样本量",
            "status": "awaiting_human_input" if labeled < MIN_SAMPLE else "ok",
            "reason": f"{labeled}/{MIN_SAMPLE} 条已带 gold 标注",
            "unblock": "用 scripts/decision_outcome_capture.py outcome --right-decision ... 登记",
        }],
    }


def validate(doc: dict) -> None:
    """fail-closed：不得声称放开自动化；标注值必须合法。"""
    if doc.get("meta", {}).get("auto_action_enabled"):
        raise ValueError("本模块禁止开启 auto_action_enabled")
    for it in doc.get("items") or []:
        for k, v in (it.get("gold") or {}).items():
            if k not in GOLD_FIELDS:
                raise ValueError(f"未知 gold 字段：{k}")
            if v not in GOLD_FIELDS[k]:
                raise ValueError(f"非法 gold 值：{k}={v}")


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
    print(f"[decision_gold] labeled_samples={m['labeled_samples']} concluded={m['concluded']} "
          f"auto_action={m['auto_action_enabled']}")
    print(f"  per_field: {json.dumps(m['per_field_counts'], ensure_ascii=False)}")
    mm = doc["metrics"]
    print(f"  decision_precision={mm['decision_precision']} action_precision={mm['action_precision']}")
    print(f"  urgency_regret: {json.dumps(mm['urgency_regret_counts'], ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))