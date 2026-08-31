#!/usr/bin/env python3
"""采样 P1-4.1 真实数据候选（proposed），用于 21→100→300 扩容。

读取生产新闻（data.json），按实体聚类，提炼四个困难维度下的候选簇，写入
`benchmarks/real_v2/candidates.json`，`review_status="proposed"`。

关键约束（与 v1.0 / v2 gold 一致）：
- 本脚本**绝不写入 gold.json**。候选只是建议，需人工审阅后提升（promote）为
  gold.json 中的 validated 条目，才算入基准。
- 只输出元数据与来源 URL，不复制正文。

运行：
  python3 scripts/sample_real_v2_candidates.py
  python3 scripts/sample_real_v2_candidates.py --news data.json --out benchmarks/real_v2/candidates.json --max-per-dimension 15
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

RUMOR_RE = re.compile(
    r"\b(reportedly|reported|eyes|talks|consideration|could|may|preferred target|"
    r"discussions|no certainty|not confirmed|rumou?red|said to|reported target)\b",
    re.I,
)
CONFIRM_RE = re.compile(
    r"\b(to acquire|acquires|acquired|completes|agrees to buy|finaliz|signed|closes|"
    r"completed|agreement|to buy|buys)\b",
    re.I,
)
DENY_RE = re.compile(
    r"\b(denies|denied|dismisses|rejects|rules out|no plans|not in talks|declines)\b",
    re.I,
)
AFFIRM_RE = re.compile(
    r"\b(in talks|to merge|agrees|confirms|advanced talks|near|nears|merger)\b",
    re.I,
)

# 生产数据 tags 经常为空，需从标题回退抽取实体（英文机构名短语）。
TITLE_ENTITY_RE = re.compile(r"\b([A-Z][a-zA-Z0-9&.\-]+(?:\s+[A-Z][a-zA-Z0-9&.\-]+){0,3})\b")
ORG_SUFFIX = re.compile(
    r"(insurance|re|group|bank|holdings|capital|partners|ag|sa|ltd|inc|llc|corp|"
    r"global|financial|technologies|tech|analytics|risk|underwriting|brokerage|markets|"
    r"assurance|mutual|health)$",
    re.I,
)
STOPWORDS = {"the", "a", "an", "in", "on", "of", "for", "to", "and", "as"}


def _title_entities(title: str) -> list[str]:
    out: list[str] = []
    for m in TITLE_ENTITY_RE.finditer(title or ""):
        words = m.group(1).split()
        if words[0].lower() in STOPWORDS:
            words = words[1:]
        if not words:
            continue
        if len(words) == 1 and not ORG_SUFFIX.search(words[0]) and not words[0].isupper():
            continue  # 过滤常见单大写词（非机构后缀、非全大写缩写）
        out.append(" ".join(words).lower())
    return out


def _entities(tags: str, title: str = "") -> list[str]:
    seen: dict[str, None] = {}
    for t in (tags or "").split(","):
        t = t.strip().lower()
        if t:
            seen.setdefault(t)
    for e in _title_entities(title):
        seen.setdefault(e)
    return list(seen)


def _signals(text: str) -> set[str]:
    s = set()
    if RUMOR_RE.search(text):
        s.add("rumor")
    if CONFIRM_RE.search(text):
        s.add("confirm")
    if DENY_RE.search(text):
        s.add("deny")
    if AFFIRM_RE.search(text):
        s.add("affirm")
    return s


def _cluster(items: list[dict]) -> dict[str, list[dict]]:
    """按实体集合签名聚类（同实体集合 = 同一事件候选）。"""
    out: dict[frozenset, list[dict]] = defaultdict(list)
    for it in items:
        ents = _entities(it.get("tags", ""), it.get("title", ""))
        if not ents:
            continue
        sig = frozenset(ents)
        out[sig].append(it)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Sample proposed P1-4.1 benchmark candidates from production news")
    parser.add_argument("--news", default=str(ROOT / "data.json"))
    parser.add_argument("--out", default=str(ROOT / "benchmarks" / "real_v2" / "candidates.json"))
    parser.add_argument("--max-per-dimension", type=int, default=15)
    args = parser.parse_args()

    news = json.loads(Path(args.news).read_text(encoding="utf-8")).get("news", [])
    # 索引：primary entity -> 文章列表
    by_primary: dict[str, list[dict]] = defaultdict(list)
    for it in news:
        ents = _entities(it.get("tags", ""), it.get("title", ""))
        if not ents:
            continue
        it["_entities"] = ents
        it["_signals"] = _signals(f"{it.get('title','')} {it.get('summary','')}")
        by_primary[ents[0]].append(it)

    candidates: list[dict] = []
    seen_pairs: set[tuple] = set()
    counts = defaultdict(int)

    def add(primary, dimension, relation, cluster_items, rationale):
        if counts[dimension] >= args.max_per_dimension:
            return
        ids = tuple(sorted(x["id"] for x in cluster_items))
        if ids in seen_pairs:
            return
        seen_pairs.add(ids)
        counts[dimension] += 1
        candidates.append({
            "id": f"cand_{primary.replace(' ', '_')}_{dimension}_{counts[dimension]:02d}",
            "dimension": dimension,
            "proposed_relation": relation,
            "primary_entity": primary,
            "rationale": rationale,
            "needs_human_review": True,
            "review_status": "proposed",
            "article_count": len(cluster_items),
            "articles": [
                {
                    "id": x["id"],
                    "title": x.get("title"),
                    "source_name": x.get("source_name"),
                    "source_url": x.get("source_url"),
                    "published_at": x.get("published_at"),
                    "tags": x.get("tags"),
                    "research_topic": x.get("research_topic"),
                    "signals": sorted(x["_signals"]),
                }
                for x in cluster_items
            ],
        })

    for primary, items in by_primary.items():
        clusters = _cluster(items)
        # 同一 primary 下的不同实体集合 = 不同事件 → 跨集合提出 different_event 对
        sigs = list(clusters.values())
        if len(sigs) >= 2:
            # 取每集合最多 1 篇代表，构造"同公司不同事件"候选
            reps = [c[0] for c in sigs if len(c) >= 1]
            if len(reps) >= 2:
                add(primary, "same_company_diff_event", "different_event", reps[:2],
                    f"同一主体 '{primary}' 出现不同实体集合（不同动作/事件），建议标为不同事件")
        for sig, cluster_items in clusters.items():
            n = len(cluster_items)
            sigs_set = set(sig)
            any_rumor = any("rumor" in x["_signals"] for x in cluster_items)
            any_confirm = any("confirm" in x["_signals"] for x in cluster_items)
            any_deny = any("deny" in x["_signals"] for x in cluster_items)
            any_affirm = any("affirm" in x["_signals"] for x in cluster_items)
            if 3 <= n <= 5:
                add(primary, "multi_source_3_5", "same_event", cluster_items,
                    f"同实体集合被 {n} 个来源覆盖，建议合并为单一事件并交叉验证")
            if any_rumor and any_confirm:
                add(primary, "rumor_to_confirmed", "same_event", cluster_items,
                    "同一事件同时存在'据称/洽谈'与'已确认'报道，建议标为同一事件（rumor→confirmed）")
            if any_deny and any_affirm:
                add(primary, "contradiction", "same_event", cluster_items,
                    "同一事件存在相互冲突报道（否认 vs 确认），建议人工裁决，引擎应保持分离")

    out = {
        "version": "real-v2.0-candidates",
        "generated_from": str(Path(args.news).name),
        "review_status": "proposed",
        "note": "NOT ground truth. Human review required before promotion into gold.json (benchmarks/real_v2/gold.json).",
        "counts": dict(counts),
        "total_candidates": len(candidates),
        "candidates": candidates,
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"counts": dict(counts), "total_candidates": len(candidates),
                      "out": str(args.out)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
