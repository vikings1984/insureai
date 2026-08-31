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
    r"assurance|mutual|health|ventures|management|solutions)$",
    re.I,
)
# 标题回退抽取会把通用领域名词（premium/income/reinsurance/capital...）误当实体，
# 污染聚簇与跨篇配对。这里显式排除这些"非机构名"词。
GENERIC_NOUN = re.compile(
    r"^(premium|premiums|income|incomes|reinsurance|capital|fee|fees|agreement|"
    r"agreements|coinsurance|bond|bonds|growth|profit|profits|revenue|revenues|cor|"
    r"underwriting|specialty|exchange|partnership|renewals|net|operating|combined|"
    r"ratio|quarter)$",
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
        if len(words) == 1:
            tok = words[0]
            # 单大写词：仅机构后缀或全大写缩写才算实体；通用名词一律排除
            if GENERIC_NOUN.search(tok):
                continue
            if not ORG_SUFFIX.search(tok) and not tok.isupper():
                continue
            out.append(tok.lower())
        else:
            # 多词短语：若以通用名词结尾则不是机构名
            if GENERIC_NOUN.search(words[-1]):
                continue
            out.append(" ".join(words).lower())
    return out


def _specific_entities(entities: list[str]) -> set[str]:
    """只保留"具体机构名"实体（多词 / 机构后缀 / 全大写缩写），用于跨篇同 deal 配对。"""
    out: set[str] = set()
    for e in entities:
        words = e.split()
        if len(words) >= 2 or ORG_SUFFIX.search(e) or (len(e) <= 6 and e.isupper()):
            out.add(e)
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


def _norm_tokens(text: str) -> set[str]:
    """Normalized content-word tokens for title-overlap (deal/theme) comparison."""
    text = (text or "").lower()
    toks = re.findall(r"[a-z0-9][a-z0-9.&+\-]{2,}", text)
    return {t for t in toks if t not in STOPWORDS}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# 同 deal 的报道标题高度重叠；同公司不同事件（不同任命/收购）重叠很低。
# 用标题 token Jaccard 代替"实体集合签名"，避免把仅共享裸主题词的报道误聚成一簇。
MERGE_THRESH = 0.32


def _cluster(items: list[dict]) -> list[list[dict]]:
    """按标题 token 相似度贪心聚簇（同 deal/主题 = 同一事件候选）。

    旧逻辑按实体集合签名聚簇，而生产数据几乎无 tags、实体抽取退化为裸主题词
    （"ils"/"ai"），导致不同 deal 被误聚成一簇（过聚簇）。改为标题重叠后，
    multi_source 候选才是真正的同事件多源覆盖，rumor 才能找到同 deal 的
    rumor+confirmed 两篇。
    """
    clusters: list[list[dict]] = []
    reps: list[set[str]] = []
    for it in items:
        toks = _norm_tokens(it.get("title", ""))
        best, best_j = None, MERGE_THRESH
        for i, rep in enumerate(reps):
            j = _jaccard(rep, toks)
            if j >= best_j:
                best, best_j = i, j
        if best is not None:
            clusters[best].append(it)
            reps[best] |= toks
        else:
            clusters.append([it])
            reps.append(toks)
    return clusters


def main() -> None:
    parser = argparse.ArgumentParser(description="Sample proposed P1-4.1 benchmark candidates from production news")
    parser.add_argument("--news", default=str(ROOT / "data.json"))
    parser.add_argument("--out", default=str(ROOT / "benchmarks" / "real_v2" / "candidates.json"))
    parser.add_argument("--max-per-dimension", type=int, default=150)
    args = parser.parse_args()

    news = json.loads(Path(args.news).read_text(encoding="utf-8")).get("news", [])
    # 索引：primary entity -> 文章列表
    by_primary: dict[str, list[dict]] = defaultdict(list)
    for it in news:
        ents = _entities(it.get("tags", ""), it.get("title", ""))
        if not ents:
            continue
        it["_entities"] = ents
        it["_specific"] = _specific_entities(ents)
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

    # 跨篇同 deal 判定：两篇共享 >=1 个具体机构名实体（收购方/标的/当事方），
    # 且标题高重叠（同 deal 措辞）。后者用于剔除"泛泛提及同公司的不同事件"误配。
    # 实测（1634 篇快照）：rumor/confirm 几乎只共现于同篇，跨篇同 deal 配对=0，
    # 故 rumor_to_confirmed / contradiction 两维在此数据天然稀疏（逻辑保留，换更大数据即生效）。
    def _share_deal(a: dict, b: dict) -> bool:
        if not (a.get("_specific", set()) & b.get("_specific", set())):
            return False
        rt = _norm_tokens(a.get("title", ""))
        bt = _norm_tokens(b.get("title", ""))
        return _jaccard(rt, bt) >= 0.30

    for primary, items in by_primary.items():
        clusters = _cluster(items)
        for ci, cl in enumerate(clusters):
            for x in cl:
                x["_cluster"] = ci
        cluster_reps = [c for c in clusters if c]
        # 同一主体下不同 deal 簇 = 不同事件 → 跨簇两两组合提 different_event 对
        # （可从一个主体派生多对，扩充候选池；每对都来自不同 deal 簇，必为不同事件）
        if len(cluster_reps) >= 2:
            for i in range(len(cluster_reps)):
                for j in range(i + 1, len(cluster_reps)):
                    add(primary, "same_company_diff_event", "different_event",
                        [cluster_reps[i][0], cluster_reps[j][0]],
                        f"同一主体 '{primary}' 出现不同 deal/主题簇（不同动作/事件），建议标为不同事件")
        # 同一 deal 被 2-5 个来源覆盖 → 真同事件多源候选（放宽到 2 源）
        for cluster_items in clusters:
            n = len(cluster_items)
            if 2 <= n <= 5:
                add(primary, "multi_source_3_5", "same_event", cluster_items,
                    f"同 deal/主题被 {n} 个来源覆盖，建议合并为单一事件并交叉验证")
        # 跨簇 rumor→confirmed / contradiction：同主体、不同簇、共享具体实体。
        # 实测（1634 篇快照）：rumor/confirm/deny/affirm 信号几乎只共现于同篇，
        # 跨篇同 deal 配对=0，故这两维在本数据天然稀疏（逻辑保留，换更大数据即生效）。
        rumor_arts = [x for c in clusters for x in c if "rumor" in x["_signals"]]
        confirm_arts = [x for c in clusters for x in c if "confirm" in x["_signals"]]
        deny_arts = [x for c in clusters for x in c if "deny" in x["_signals"]]
        affirm_arts = [x for c in clusters for x in c if "affirm" in x["_signals"]]
        for r in rumor_arts:
            for c in confirm_arts:
                if r["id"] == c["id"] or r["_cluster"] == c["_cluster"]:
                    continue
                if _share_deal(r, c):
                    add(primary, "rumor_to_confirmed", "same_event", [r, c],
                        "同主体、不同簇、共享具体实体：'据称/洽谈'篇与'已确认'篇，建议标为同一事件（rumor→confirmed）")
        for d in deny_arts:
            for a in affirm_arts:
                if d["id"] == a["id"] or d["_cluster"] == a["_cluster"]:
                    continue
                if _share_deal(d, a):
                    add(primary, "contradiction", "different_event", [d, a],
                        "同主体、不同簇、共享具体实体：'否认'与'确认'冲突报道，建议人工裁决，引擎应保持分离")

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
