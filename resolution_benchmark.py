#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0-1 Canonical Resolution Accuracy Benchmark（Event OS 第五阶段「真实业务精度验证」）。

度量 `identity_resolver` 的**候选合并**质量：对「同域实体线程组」（应被提议合并的
same-domain entity groups）计算 precision / recall / F1，把「语义归并 recall 缺口」
从定性（candidate_merges=0）变成可量化。

口径：
- gold 正例：second_brain.entity_threads 中，≥min_shared 个 CE 且**同 domain** 的组
  （这些理应被提议为候选合并；跨 domain 组是负例，分区门应拒绝）。
- 系统输出：`identity_resolver.propose_merges_from_entity_threads` 的候选（仅 proposal，
  不执行合并，故不触碰 false_merge 硬约束）。
- recall = 被某个 proposal 完整覆盖的 gold 组 / gold 组总数；
  precision = 能对应到 gold 组的 proposal / proposal 总数。

诚实性：若 gold>0 而 proposal==0，本模块给出 root-cause 提示（当前已知：resolver 读
`event_id`，而 second_brain 线程事件只有 `canonical_event_id`，字段名不匹配导致候选恒空）。
修复属独立变更，须保持 false_merge_rate==0，本基准只负责「量化缺口 + 定位根因」。

用法::

    python3 resolution_benchmark.py
    python3 resolution_benchmark.py --json
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import identity_resolver as ir

HERE = os.path.dirname(os.path.abspath(__file__))
GOLD_PATH = os.path.join(HERE, "tests", "gold", "resolution_gold.json")
SECOND_BRAIN = os.path.join(HERE, "second_brain.json")

VERSION = "1.0"
MIN_SHARED = 2


def _load_json(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _ce_domain(cev_id: str, registry: dict) -> str | None:
    try:
        return ir.partition_classify(cev_id, registry).get("domain")
    except Exception:
        return None


def build_gold(threads: list[dict], registry: dict, min_shared: int = MIN_SHARED) -> dict:
    """从实体线程构造 gold：same-domain 组为正例，cross-domain 组为负例。

    线程事件用 canonical_event_id 直接关联 CE（second_brain 的真实字段）。
    """
    positives: list[dict] = []   # 应被提议的同域组
    negatives: list[dict] = []   # 跨域组：分区门应拒绝
    for th in threads or []:
        entity = th.get("entity")
        cev_ids = sorted({ev.get("canonical_event_id")
                          for ev in (th.get("events") or [])
                          if ev.get("canonical_event_id")})
        if not entity or len(cev_ids) < min_shared:
            continue
        domains = {d for d in (_ce_domain(c, registry) for c in cev_ids) if d}
        rec = {"entity": entity, "cev_ids": cev_ids,
               "domains": sorted(domains), "type": th.get("type")}
        if len(domains) == 1:
            positives.append(rec)          # 同域 → 应提议
        elif len(domains) > 1:
            negatives.append(rec)          # 跨域 → 不应提议
    return {"positives": positives, "negatives": negatives}


def run_benchmark(gold_path: str | None = None) -> dict:
    registry = ir.load_registry()
    sb = _load_json(SECOND_BRAIN) or {}
    threads = sb.get("entity_threads") or []

    gold = build_gold(threads, registry)
    # 外部 gold（若提供）可覆盖/追加人工标注；当前以数据派生 gold 为主。
    ext = _load_json(gold_path) if gold_path else None

    # 系统输出：resolver 的候选合并 proposal
    proposals = ir.propose_merges_from_entity_threads(threads, registry, min_shared=MIN_SHARED)
    prop_sets = [set(p.get("canonical_ids") or []) for p in proposals]

    # recall：gold 同域组是否被某个 proposal 完整覆盖
    tp = 0
    fn_groups = []
    for g in gold["positives"]:
        gset = set(g["cev_ids"])
        if any(gset <= ps for ps in prop_sets):
            tp += 1
        else:
            fn_groups.append(g)
    # precision：proposal 是否对应到某个 gold 同域组（子集覆盖）
    fp_props = []
    for p, ps in zip(proposals, prop_sets):
        if not any(ps and ps <= set(g["cev_ids"]) for g in gold["positives"]):
            fp_props.append(p)

    fn = len(fn_groups)
    fp = len(fp_props)
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    diagnosis = None
    if gold["positives"] and not proposals:
        diagnosis = ("存在同域实体线程组（应被提议为候选），但 resolver 产出 0 候选；"
                     "已知根因：propose_merges_from_entity_threads 读 ev['event_id']，"
                     "而 second_brain 线程事件只有 canonical_event_id → 字段名不匹配。"
                     "修复为独立变更，须保持 false_merge_rate==0。")

    out = {
        "available": True,
        "version": VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "gold_source": (ext or {}).get("source", "derived_from_entity_threads"),
        "gold_status": (ext or {}).get("status", "derived"),
        "counts": {
            "entity_threads": len(threads),
            "gold_same_domain_groups": len(gold["positives"]),
            "gold_cross_domain_groups": len(gold["negatives"]),
            "resolver_proposals": len(proposals),
        },
        "metrics": {"precision": round(precision, 4), "recall": round(recall, 4),
                    "f1": round(f1, 4), "tp": tp, "fp": fp, "fn": fn},
        "missed_groups": fn_groups[:10],
        "false_proposals": fp_props[:10],
        "diagnosis": diagnosis,
    }
    return out


def main(argv: list[str]) -> int:
    out = run_benchmark()
    if "--json" in argv:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    m = out["metrics"]
    c = out["counts"]
    print(f"[resolution_benchmark] gold={out['gold_status']}/{out['gold_source']} "
          f"threads={c['entity_threads']} same_domain_groups={c['gold_same_domain_groups']} "
          f"proposals={c['resolver_proposals']} | precision={m['precision']} "
          f"recall={m['recall']} f1={m['f1']} (tp={m['tp']} fp={m['fp']} fn={m['fn']})")
    if out.get("diagnosis"):
        print(f"[resolution_benchmark] 根因提示：{out['diagnosis']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
