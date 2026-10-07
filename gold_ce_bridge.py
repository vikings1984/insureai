#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0-3 Gold 解耦桥：把**人工 gold**（article 级）桥接到 **CE 级**评估（Event OS 第八阶段）。

## 为什么需要这个桥

第八阶段方案 §3-P0-3 的「解耦要求」：

> `resolution_benchmark` 的 gold 需从 `derived_from_entity_threads` 迁移到**人工标注 event pair**，
> 否则它继续自证。

但两者**粒度不同**，直接接不上：

|来源                | 粒度 | 内容|
|--------------------|------|------|
| `real_v2/gold_real.json` | **article id** | 人工标注的same/different event 对（9 same + 151 different） |
| `identity_resolver`| **canonical_event_id** | 候选合并proposal（同实体线程下的 CE 组） |

因此本模块提供**唯一缺失的那一层**：article → canonical_event_id 映射，
把人工 article 对转换为 CE 对，再交给 `resolution_benchmark` 用**人工 gold**评估 resolver。

映射依据（**只用已有事实，不推断**）：
`intelligence.json` 的每个 event 自带 `article_ids`（该事件由哪些文章支撑），
与 `canonical_events.json` 的 `by_event_id` 一起构成 article → CE 的**可追溯**归属。

诚实性纪律：
- 只映射**确实能追溯**的 article；映射不到的对**跳过并计数**（绝不猜测/就近归并）；
- 报告 `mapped / skipped` 明示覆盖率，不用「猜」出来的映射凑指标；
- 桥接只做**评估口径转换**，不产生任何新的标签，也不改写 gold。

用法::

    python3 gold_ce_bridge.py# 打印桥接摘要
    python3 gold_ce_bridge.py --json      # 输出完整桥接结果
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
GOLD = os.path.join(HERE, "benchmarks", "real_v2", "gold_real.json")
INTEL = os.path.join(HERE, "intelligence.json")
CANONICAL = os.path.join(HERE, "canonical_events.json")
OUTPUT = os.path.join(HERE, "gold_ce_bridge.json")

VERSION = "gold-ce-bridge-v1.0"


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


def build_article_to_ce(intel: dict | None = None,
                       canon: dict | None = None) -> dict[str, str]:
    """article_id -> canonical_event_id（**只收录可追溯的映射**）。

    一个 article 可能支撑多个 event（此时该 article 视为**歧义**，不映射——
    宁可漏评也不给出错误 gold）。
    """
    intel = intel if intel is not None else (_read(INTEL) or {})
    canon = canon if canon is not None else (_read(CANONICAL) or {})
    pool = set((canon.get("canonical_events") or {}).keys())
    by_event_id = canon.get("by_event_id") or {}

    a2c: dict[str, str] = {}
    ambiguous: set[str] = set()
    for ev in intel.get("events") or []:
        if not isinstance(ev, dict):
            continue
        ceid = ev.get("canonical_event_id")
        eid = ev.get("event_id")
        if not ceid or ceid not in pool:
            continue
        if not eid and eid != 0:                      # 无 event_id 不可追溯
            continue
        ceid = by_event_id.get(eid, ceid) or ceid       # 以 registry 为准
        for aid in (ev.get("article_ids") or []):
            key = str(aid)
            if key in a2c and a2c[key] != ceid:
                ambiguous.add(key)                    # 一文章对多事件 → 歧义
            a2c[key] = ceid
    for key in ambiguous:
        a2c.pop(key, None)
    return a2c


def bridge(gold: dict | None = None, a2c: dict | None = None) -> dict:
    gold = gold if gold is not None else (_read(GOLD) or {})
    a2c = a2c if a2c is not None else build_article_to_ce()

    same_pairs = gold.get("same_event_pairs") or []
    diff_pairs = gold.get("different_event_pairs") or []

    def _convert(pairs: list) -> tuple[list, int]:
        out, skipped = [], 0
        for pair in pairs:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                skipped += 1
                continue
            a, b = str(pair[0]), str(pair[1])
            ca, cb = a2c.get(a), a2c.get(b)
            if ca and cb and ca != cb:                # 两端都能追溯且属不同 CE
                out.append([ca, cb])
            else:
                skipped += 1
            continue
        return out, skipped

    same_ce, same_skip = _convert(same_pairs)
    diff_ce, diff_skip = _convert(diff_pairs)

    # 自查：转换后不得出现自反对（a==b）——那是映射错误而非 gold
    same_ce = [p for p in same_ce if p[0] != p[1]]

    return {
        "version": VERSION,
        "generated_at": _now(),
        "principle": "article→CE 只收录可追溯映射；映射不到的对跳过并计数，绝不猜测。"
                     "本模块只做评估口径转换，不产生新标签、不改写 gold。",
        "meta": {
            "gold_source": gold.get("review_status", "unknown"),
            "production_data_never_auto_labeled": gold.get(
                "annotation_policy", {}).get("production_data_never_auto_labeled"),
            "article_map_size": len(a2c),
            "same_pairs_article_level": len(same_pairs),
            "different_pairs_article_level": len(diff_pairs),
            "same_pairs_ce_level": len(same_ce),
            "different_pairs_ce_level": len(diff_ce),
            "skipped_same": same_skip,
            "skipped_different": diff_skip,
            "coverage_note": "skipped = 该 article 无法唯一追溯到某个 CE（缺失或歧义），"
                            "宁可漏评也不猜测",
        },
        "same_event_pairs_ce": same_ce,
        "different_event_pairs_ce": diff_ce,
    }


def main(argv: list[str]) -> int:
    doc = bridge()
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")
    if "--json" in argv:
        print(json.dumps(doc, ensure_ascii=False, indent=2))
        return 0
    m = doc["meta"]
    print(f"[gold_ce_bridge] gold={m['gold_source']} | article→CE 映射 {m['article_map_size']} 条")
    print(f"[gold_ce_bridge] same: article {m['same_pairs_article_level']} → CE {m['same_pairs_ce_level']}"
          f"（跳过 {m['skipped_same']}）")
    print(f"[gold_ce_bridge] different: article {m['different_pairs_article_level']} → CE {m['different_pairs_ce_level']}"
          f"（跳过 {m['skipped_different']}）")
    if doc["meta"]["same_pairs_ce_level"] == 0:
        print("[gold_ce_bridge] 提示：CE 级 same 对为 0，无法据此评recall"
              "（这是**诚实的缺口**，不是 bug）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))