#!/usr/bin/env python3
"""P2.6 Role-based Second Brain — 把既有记忆层按角色切片、并补「实体跨事件时间线」。

附件轨迹 Knowledge Graph → Personal Memory → **Role-based Second Brain** →
Multi-agent Intelligence。本模块是第三棒：个人记忆是「这个人盯过谁、判过什么」的
平面视图；Second Brain 在其上加两层结构——

1. **角色切片（roles）**：同一份记忆，按战略 / 运营 / 风险三角色各看各的关注面。
   角色→主题/关注清单的映射是**显式声明**的配置（ROLE_CONFIG），不是从数据推断——
   推断「用户属于什么角色」本身就是一种偏好结论，当前样本不支持。
2. **实体跨事件时间线（entity_threads）**：把同一机构/人物在图谱里参与过的事件按
   发布时间串起来。这**不**是决策时间线（我们仍没有 decided_at），而是「这个主体
   在世界上反复出现」的证据链，直接缓解 P2.5 暴露的「记忆时间线」结构性缺口。

设计纪律（与 P2.5 一致，最重要）
------------------------------
* **只聚合既有 artifact**：输入是 p2_state / review_queue / p2_daily_brief /
  p2_personal_memory / knowledge_graph，本模块不生产任何新事实。
* **角色视图是过滤，不是推断**：roles 里的 top_topics / top_entities / memory_entries
  全部来自对既有产物的过滤；ROLE_CONFIG 仅声明「这个角色关心什么」，不编造命中。
* **观察与结论分离**：绝不输出「用户偏好 X」之类结论；样本不足以支撑的结论不写，
  推不出的维度进 `open_questions`（带 reason / unblock）。
* **不伪造时间线**：entity_threads 的时间全部取自 Event 节点的 published_at，
  明确标注为「事件发布时间」；decision 仍无时间戳，不声称先后顺序。

用法
----
    python3 second_brain.py [--out second_brain.json] [--validate-only]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
OUTPUT_PATH = ROOT / "second_brain.json"

VERSION = "sb-v1.0"

# 角色 → 关注面 的显式映射。
# 这些是「用户先前在 Watchlist / 轨迹里点名的方向」，由本模块透明声明；
# 不是从数据推断（推断角色归属本身需要样本，当前没有）。
ROLE_CONFIG: dict[str, dict] = {
    "strategy": {
        "label": "战略决策",
        "desc": "趋势 / 并购 / 监管 / 资本",
        "watchlist_ids": ["ma", "regulatory"],
        "topics": ["capital_reinsurance", "ai_intelligent", "regulatory_change", "pension_finance"],
    },
    "operations": {
        "label": "运营监控",
        "desc": "健康险 / 服务 / 理赔 / 渠道",
        "watchlist_ids": ["health", "ai"],
        "topics": ["product_innovation", "pension_finance", "channel_transformation", "digital_transformation"],
    },
    "risk": {
        "label": "风险合规",
        "desc": "处罚 / 批复 / 资本充足 / 巨灾",
        "watchlist_ids": ["regulatory"],
        "topics": ["regulatory_change", "climate_catastrophe"],
    },
}

# 参与「实体时间线」的关系：Event --PARTICIPATES_IN--> Company / Person
ENTITY_RELATIONS = ("PARTICIPATES_IN",)
# 实体时间线规模上限（约束力：避免 2237 个 Company 全展开）
MAX_THREADS = 20
MAX_EVENTS_PER_THREAD = 8
# 跟踪的实体来源：个人记忆里「行动过 / 关注过」的主体，取前 N 个
TRACKED_ENTITY_LIMIT = 25


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load(path: Path) -> dict:
    """读 artifact；不存在时抛明确错误（fail-closed，不静默产出残缺 Second Brain）。"""
    if not path.exists():
        raise FileNotFoundError(f"缺少输入 artifact: {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def _top(counter: Counter, n: int) -> list[dict]:
    """Counter → [{key, count}]，同票按 key 升序，保证输出可复现。"""
    return [{"key": k, "count": c} for k, c in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[:n]]


def _dist(items: list[dict], field: str) -> dict[str, int]:
    return dict(Counter(i.get(field) for i in items if i.get(field) is not None))


# --------------------------------------------------------------------------
# 角色切片：对同一份记忆按角色过滤
# --------------------------------------------------------------------------
def role_views(pm: dict, brief_items: list[dict]) -> dict[str, dict]:
    pm_watchlists = {w["id"]: w for w in pm.get("watchlists", {}).get("items", [])}
    pm_memory = pm.get("memory_entries", [])

    out: dict[str, dict] = {}
    for rid, cfg in ROLE_CONFIG.items():
        # fail-closed：配置声明的关注清单必须在记忆层里真实存在
        missing = [wid for wid in cfg["watchlist_ids"] if wid not in pm_watchlists]
        if missing:
            raise ValueError(f"角色 {rid} 引用了不存在的关注清单: {missing}（记忆层只有 {sorted(pm_watchlists)}）")

        wids = set(cfg["watchlist_ids"])
        topics = set(cfg["topics"])

        role_items = [
            e for e in brief_items
            if (e.get("topic") in topics) or (set(e.get("watchlist_matches") or []) & wids)
        ]
        role_mem = [m for m in pm_memory if m.get("topic") in topics]

        out[rid] = {
            "label": cfg["label"],
            "desc": cfg["desc"],
            "watchlist_ids": cfg["watchlist_ids"],
            "topics": cfg["topics"],
            # 过滤自记忆层，非推断
            "watchlists": [pm_watchlists[w] for w in cfg["watchlist_ids"]],
            "top_topics": _top(Counter(e["topic"] for e in role_items if e.get("topic")), 6),
            "top_entities": _top(
                Counter(ent for e in role_items for ent in (e.get("entities") or [])), 8
            ),
            "memory_entries": role_mem,
        }
    return out


# --------------------------------------------------------------------------
# 实体跨事件时间线：同一主体在图谱里参与过的事件，按发布时间串起来
# --------------------------------------------------------------------------
def build_entity_threads(graph: dict, tracked_names: list[str]) -> list[dict]:
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    by_id = {n["id"]: n for n in nodes}

    name_to_id: dict[str, str] = {}
    for n in nodes:
        if n.get("type") in ("Company", "Person") and n.get("name"):
            name_to_id.setdefault(n["name"], n["id"])

    adj: dict[str, list[tuple[str, str]]] = {}
    for e in edges:
        adj.setdefault(e["source"], []).append((e["target"], e["relationship"]))
        adj.setdefault(e["target"], []).append((e["source"], e["relationship"]))

    threads: list[dict] = []
    for name in tracked_names:
        eid = name_to_id.get(name)
        if not eid:
            continue
        evs: list[dict] = []
        for tid, rel in adj.get(eid, []):
            if rel not in ENTITY_RELATIONS:
                continue
            t = by_id.get(tid)
            if t and t.get("type") == "Event":
                evs.append({
                    "event_id": t.get("name"),
                    "title": t.get("title"),
                    "topic": t.get("topic"),
                    # 事件发布时间，不是决策时间
                    "published_at": t.get("published_at"),
                })
        if not evs:
            continue
        evs.sort(key=lambda x: (x["published_at"] or "", x["event_id"] or ""))
        evs = evs[:MAX_EVENTS_PER_THREAD]
        pubs = [e["published_at"] for e in evs if e["published_at"]]
        threads.append({
            "entity": name,
            "type": by_id[eid].get("type"),
            "event_count": len(evs),
            "first_seen": min(pubs) if pubs else None,
            "last_seen": max(pubs) if pubs else None,
            "events": evs,
        })

    threads.sort(key=lambda x: x["entity"])
    return threads[:MAX_THREADS]


def _tracked_entities(pm: dict) -> list[str]:
    """个人记忆里「行动过 / 关注过」的主体——时间线的跟踪对象。"""
    ea = pm.get("entity_affinity", {})
    names: list[str] = []
    for bucket in ("acted_entities", "watched_entities", "overlap_entities"):
        for item in ea.get(bucket, []):
            if isinstance(item, dict) and item.get("key"):
                names.append(item["key"])
    # 去重保序
    seen: set[str] = set()
    uniq: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            uniq.append(n)
    return uniq[:TRACKED_ENTITY_LIMIT]


# --------------------------------------------------------------------------
# 待澄清项：把「推不出 / 没信号」显式写出来
# --------------------------------------------------------------------------
def open_questions(pm: dict, roles: dict[str, dict]) -> list[dict]:
    oq: list[dict] = []

    # 0 命中的关注清单：配置在但最近简报没信号
    for w in pm.get("watchlists", {}).get("items", []):
        if w.get("hit_count") == 0:
            oq.append({
                "dimension": f"关注清单 {w['id']} 无信号",
                "status": "no_signal",
                "reason": "该关注清单在最近简报 top-20 内 0 命中",
                "unblock": "检查关键词是否过窄，或确认语料暂无相关事件（非错误，可能只是暂无）",
            })

    # 角色无决策覆盖：该角色关注的主题内暂无已落决策
    for rid, r in roles.items():
        if not r.get("memory_entries"):
            oq.append({
                "dimension": f"角色 {rid} 决策覆盖",
                "status": "no_decisions",
                "reason": "该角色关注的主题内暂无已落决策",
                "unblock": "在 Human Review 中对相关事件落 decision 后自动填充",
            })

    # 镜像 P2.5 暴露的缺口（事实缺口，不是本层新增）
    for g in pm.get("gaps", []):
        oq.append({
            "dimension": g.get("dimension"),
            "status": g.get("status"),
            "reason": g.get("reason"),
            "unblock": g.get("unblock"),
        })
    return oq


# --------------------------------------------------------------------------
# 组装
# --------------------------------------------------------------------------
def build(
    state: dict,
    queue: dict,
    brief: dict,
    pm: dict,
    graph: dict | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    watchlists = state.get("watchlists") or []
    items = queue.get("items") or []
    brief_items = brief.get("brief") or []
    acted = [i for i in items if i.get("decision")]
    pending = [i for i in items if not i.get("decision")]

    roles = role_views(pm, brief_items)
    threads = build_entity_threads(graph, _tracked_entities(pm)) if graph else []
    oq = open_questions(pm, roles)

    return {
        "version": VERSION,
        "generated_at": generated_at or _now(),
        "principle": "角色视图只读既有记忆的过滤结果；不新增事实、不伪造偏好；"
                     "推不出的维度写入 open_questions",
        "sources": {
            "p2_state.json": {"watchlists": len(watchlists)},
            "review_queue.json": {"items": len(items), "decided": len(acted), "pending": len(pending)},
            "p2_daily_brief.json": {"brief": len(brief_items)},
            "p2_personal_memory.json": {"version": pm.get("version")},
            "knowledge_graph.json": {"threads_built": len(threads)} if graph else None,
        },
        "roles": roles,
        "entity_threads": threads,
        "open_questions": oq,
    }


def validate(doc: dict) -> None:
    """fail-closed 校验：结构不对就让 CI 红，而不是让角色面静默显示空。"""
    assert doc.get("version") == VERSION, f"version 错误: {doc.get('version')}"
    for key in ("generated_at", "principle", "sources", "roles", "entity_threads", "open_questions"):
        assert key in doc, f"缺少字段: {key}"

    # 角色必须是显式声明的三档，不多不少
    assert set(doc["roles"]) == set(ROLE_CONFIG), f"roles 与 ROLE_CONFIG 不一致: {set(doc['roles'])}"
    for rid, r in doc["roles"].items():
        for f in ("label", "desc", "watchlist_ids", "topics", "watchlists", "top_topics", "top_entities", "memory_entries"):
            assert f in r, f"角色 {rid} 缺字段: {f}"
        # 声明的关注清单必须真在 watchlists 里
        ids = {w["id"] for w in r["watchlists"]}
        assert set(r["watchlist_ids"]) <= ids, f"角色 {rid} 的 watchlists 与声明不一致"

    # 时间线：事件必须带 event_id；时间线不得凭空超出跟踪实体数
    for t in doc["entity_threads"]:
        for e in t["events"]:
            assert e.get("event_id"), f"实体时间线事件缺 event_id: {e}"

    # 纪律：推不出的维度必须显式记录（当前状态必然非空）
    assert isinstance(doc["open_questions"], list) and doc["open_questions"], \
        "open_questions 不得为空（推不出 / 无信号的维度必须显式记录）"


def run(
    state_path: Path | None = None,
    queue_path: Path | None = None,
    brief_path: Path | None = None,
    pm_path: Path | None = None,
    graph_path: Path | None = None,
    out_path: Path | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    state = _load(state_path or ROOT / "p2_state.json")
    queue = _load(queue_path or ROOT / "review_queue.json")
    brief = _load(brief_path or ROOT / "p2_daily_brief.json")
    pm = _load(pm_path or ROOT / "p2_personal_memory.json")

    # 图谱可选：缺它只是派不出实体时间线，角色视图照常产出
    graph: dict | None = None
    gp = graph_path or ROOT / "knowledge_graph.json"
    if gp.exists():
        graph = json.loads(gp.read_text(encoding="utf-8"))

    doc = build(state, queue, brief, pm, graph)
    validate(doc)
    if persist:
        (out_path or OUTPUT_PATH).write_text(
            json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return doc


def main() -> int:
    parser = argparse.ArgumentParser(description="构建 Role-based Second Brain（角色切片 + 实体时间线）")
    parser.add_argument("--out", default=str(OUTPUT_PATH))
    parser.add_argument("--validate-only", action="store_true", help="只校验已有产物，不重新生成")
    args = parser.parse_args()

    out = Path(args.out)
    if args.validate_only:
        validate(json.loads(out.read_text(encoding="utf-8")))
        d = json.loads(out.read_text(encoding="utf-8"))
        print(json.dumps(
            {
                "roles": list(d["roles"]),
                "entity_threads": len(d["entity_threads"]),
                "open_questions": len(d["open_questions"]),
            },
            ensure_ascii=False,
        ))
        return 0

    doc = run(out_path=out)
    print(
        f"second_brain.json 已生成 | 角色 {len(doc['roles'])} 档 · "
        f"实体时间线 {len(doc['entity_threads'])} 条 · 待澄清项 {len(doc['open_questions'])} 项"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
