#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0-2 Semantic Change Precision Benchmark（Event OS 第五阶段「真实业务精度验证」）。

第四阶段 P0-A 已证明「跨日 baseline 重建不掩盖真实变化」（回归测试），但那是**结构性**
断言（用合成 fixture 验证 change 告警数），**不是对人工 gold 的精度度量**。

本模块把 Semantic Alert 的跨日变化检出升级为**可度量的精度基准**：
- 从 gold 文件（``tests/gold/semantic_change_gold.json``）读取多日场景，逐日驱动
  ``semantic_alert.build``（以次日快照为 baseline）；
- 把每个「昨天→今天」转换与 gold 的 ``expect_change`` / ``expect_types`` 比对；
- 产出 change 检出的 **precision / recall / F1 / FP / FN**，作为「重要变化不漏、
  不重要变化不冒充」的真实度量。

gold 场景可由人工持续补充（真实生产多日样本）；当前为 seed 合成场景。
Day1 为 seed（无 baseline，按设计不产 change），不计入指标。

用法::

    python3 semantic_change_benchmark.py            # 跑基准并打印摘要
    python3 semantic_change_benchmark.py --json     # 输出 JSON
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

from semantic_alert import build, current_snapshot, validate

HERE = os.path.dirname(os.path.abspath(__file__))
GOLD_PATH = os.path.join(HERE, "tests", "gold", "semantic_change_gold.json")

VERSION = "1.0"


def _events(eid: str, evidence: int, trust: int = 70) -> list[dict]:
    return [{
        "event_id": eid, "title": "CE", "topic": "acquisition",
        "trust": {"level": "medium", "score": trust},
        "evidence": [{"x": i} for i in range(evidence)],
        "claims": {"proposition_count": 0},
        "review_required": False,
    }]


def _lifecycle(ceid: str, eid: str, stage: str, status=None) -> list[dict]:
    return [{"canonical_event_id": ceid, "stage": stage, "status": status,
             "identity_key": eid, "title": "CE"}]


def _brief(eid: str) -> list[dict]:
    return [{"event_id": eid, "daily_priority": 50, "watchlist_matches": False}]


def _inputs(day: dict):
    eid = day["eid"]
    ceid = day["ceid"]
    ev = _events(eid, int(day.get("evidence", 1)), int(day.get("trust", 70)))
    lc = _lifecycle(ceid, eid, day.get("stage", "rumor"), day.get("status"))
    return ev, lc, _brief(eid), {eid: ceid}


def _snapshot(day: dict) -> dict:
    ev, lc, br, cm = _inputs(day)
    return current_snapshot(ev, lc, [], br, cm)


def _run_day(day: dict, baseline) -> dict:
    ev, lc, br, cm = _inputs(day)
    doc = build(ev, lc, [], br, baseline=baseline, ceid_map=cm)
    validate(doc)  # 硬约束：无 diff 不得产 change 类
    return doc


def _p_r_f1(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "tp": tp, "fp": fp, "fn": fn, "tn": 0,
    }


def run_benchmark(gold_path: str | None = None) -> dict:
    path = gold_path or GOLD_PATH
    if not os.path.exists(path):
        return {"available": False, "note": f"gold 不存在：{path}"}
    try:
        with open(path, "r", encoding="utf-8") as f:
            gold = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return {"available": False, "note": f"gold 读取失败：{e}"}

    tp = fp = fn = tn = 0
    details: list[dict] = []
    type_hits = type_total = 0

    for sc in gold.get("scenarios") or []:
        days = sc.get("days") or []
        prev_snap = None
        for i, day in enumerate(days):
            is_seed = (i == 0)
            doc = _run_day(day, baseline=prev_snap)
            produced = [a for a in doc.get("semantic_alerts", [])
                        if a.get("basis") == "delta"]  # 只看 change 类
            # 记录本 CE 当日产出的 change 类型
            ptypes = {a.get("type") for a in produced}
            expect_change = bool(day.get("expect_change"))
            expect_types = set(day.get("expect_types") or [])

            if is_seed:
                # seed 日按设计不产 change，不计入指标
                details.append({"scenario": sc.get("name"), "day": day.get("day"),
                                "seed": True, "produced_types": sorted(ptypes)})
            else:
                got_change = len(produced) > 0
                if expect_change and got_change:
                    tp += 1
                    outcome = "tp"
                elif expect_change and not got_change:
                    fn += 1
                    outcome = "fn"
                elif (not expect_change) and got_change:
                    fp += 1
                    outcome = "fp"
                else:
                    tn += 1
                    outcome = "tn"
                # 类型命中（仅对正例）
                if expect_change and expect_types:
                    type_total += len(expect_types)
                    type_hits += len(expect_types & ptypes)
                details.append({"scenario": sc.get("name"), "day": day.get("day"),
                                "outcome": outcome, "expect_change": expect_change,
                                "produced_types": sorted(ptypes),
                                "expect_types": sorted(expect_types)})
            prev_snap = _snapshot(day)

    metrics = _p_r_f1(tp, fp, fn)
    metrics["tn"] = tn
    metrics["type_accuracy"] = round(type_hits / type_total, 4) if type_total else None
    return {
        "available": True,
        "version": VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "gold_status": gold.get("status", "unknown"),
        "gold_source": gold.get("source", "unknown"),
        "metrics": metrics,
        "details": details,
    }


def main(argv: list[str]) -> int:
    out = run_benchmark()
    if "--json" in argv:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if out.get("available") else 1
    if not out.get("available"):
        print(f"[semantic_change_benchmark] {out.get('note')}")
        return 1
    m = out["metrics"]
    print(f"[semantic_change_benchmark] gold={out['gold_status']}/{out['gold_source']} "
          f"precision={m['precision']} recall={m['recall']} f1={m['f1']} "
          f"(tp={m['tp']} fp={m['fp']} fn={m['fn']} tn={m['tn']} "
          f"type_acc={m['type_accuracy']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
