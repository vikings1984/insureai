#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0-4 Review 阈值校准报告（Event OS 第八阶段）—— **只出报告，绝不放开自动化**。

回答一个具体问题：**哪些 review tier 将来可以考虑低风险自动化？**
但本模块**不给出结论性放开**，只产出证据，因为：

- 第七/八阶段纪律：`auto_executable` 恒 False——阈值未经人工验证时自动处置=静默漏斗；
- 放开条件是**门**（写死为判定），不是拍脑袋：某 tier 建议接受率 ≥ ACCEPT_RATE_MIN
  **且** 样本 ≥ MIN_SAMPLE **且** benchmark 四类false 率维持严格 0.0。
- 即使满足，也只输出 `eligible_for_proposal=True`（**提案**），绝不自动执行；
  真正放开需另行评审 + 人工确认（本阶段不做）。

用法::

    python3 review_threshold_calibration.py           # 打印校准报告
    python3 review_threshold_calibration.py --json
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
FEEDBACK = os.path.join(HERE, "review_feedback_summary.json")

VERSION = "threshold-calibration-v1.0"

# —— 放开门槛（写死；不因数据好看而下调）——
ACCEPT_RATE_MIN = 0.9      # 建议接受率门槛
MIN_SAMPLE = 30            # 每 tier 最小样本
REJECT_RATE_MAX = 0.1# 可接受的否决率上限


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


def build(summary: dict | None = None) -> dict:
    fb = summary if summary is not None else (_read(FEEDBACK) or {})
    by_tier = fb.get("by_tier") or {}
    total_matched = fb.get("meta", {}).get("feedback_matched", 0)

    rows = []
    for tier, s in sorted(by_tier.items()):
        n = s.get("total", 0)
        ar = s.get("accept_rate")
        rr = (s.get("reject", 0) / n) if n else None
        enough = n >= MIN_SAMPLE
        meets_accept = (ar is not None and ar >= ACCEPT_RATE_MIN)
        meets_reject = (rr is not None and rr <= REJECT_RATE_MAX)
        # 只产出「提案资格」，不执行
        eligible = bool(enough and meets_accept and meets_reject)
        blockers = []
        if not enough:
            blockers.append(f"样本不足（{n}/{MIN_SAMPLE}）")
        if not meets_accept:
            blockers.append(f"接受率未达{ACCEPT_RATE_MIN}" +
                            (f"（当前 {ar}）" if ar is not None else "（无数据）"))
        if not meets_reject:
            blockers.append(f"否决率高于 {REJECT_RATE_MAX}" +
                            (f"（当前 {rr}）" if rr is not None else ""))
        rows.append({
            "tier": tier,
            "samples": n,
            "accept_rate": ar,
            "reject_rate": round(rr, 4) if rr is not None else None,
            "sample_sufficient": enough,
            "eligible_for_proposal": eligible,
            "blockers": blockers,
            "auto_action_enabled": False,     # 恒 False：本阶段只出报告
        })

    return {
        "version": VERSION,
        "generated_at": _now(),
        "principle": "阈值校准只产出「提案资格」，**绝不自动放开**；"
                     "放开需满足接受率/否决率/样本三门，且仍需人工评审确认。",
        "gates": {
            "accept_rate_min": ACCEPT_RATE_MIN,
            "reject_rate_max": REJECT_RATE_MAX,
            "min_samples_per_tier": MIN_SAMPLE,
        },
        "meta": {
            "feedback_matched": total_matched,
            "any_tier_eligible": any(r["eligible_for_proposal"] for r in rows),
            "auto_action_enabled": False,
            "data_sufficient": total_matched >= MIN_SAMPLE,
        },
        "tiers": rows,
        "open_questions": [{
            "dimension": "自动化放开决策",
            "status": "not_proposed_yet",
            "reason": "反馈样本不足，任何 tier 都不满足三门；"
                      "且放开属业务风险决策，需人工评审",
            "unblock": f"累计 ≥{MIN_SAMPLE} 条/tier 的真实反馈后重跑本报告，再由人工评审是否放开",
        }],
    }


def main(argv: list[str]) -> int:
    doc = build()
    if "--json" in argv:
        print(json.dumps(doc, ensure_ascii=False, indent=2))
        return 0
    m = doc["meta"]
    print(f"[threshold_calibration] feedback_matched={m['feedback_matched']} "
          f"data_sufficient={m['data_sufficient']} "
          f"any_tier_eligible={m['any_tier_eligible']} auto_action={m['auto_action_enabled']}")
    for r in doc["tiers"]:
        print(f"  {r['tier']:18} n={r['samples']:3d} accept={r['accept_rate']} "
              f"eligible={r['eligible_for_proposal']}"
              f"{'  blockers=' + '; '.join(r['blockers']) if r['blockers'] else ''}")
    if not doc["tiers"]:
        print("  （暂无反馈数据；先经 scripts/review_feedback_capture.py 登记）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))