#!/usr/bin/env python3
"""P2.5 Personal Memory — 把「用户关注过什么、判断过什么」沉淀成个人记忆层。

附件轨迹 Knowledge Graph → **Personal Memory** → Role-based Second Brain →
Multi-agent Intelligence。本模块是第二棒：图谱回答「世界发生了什么、谁和谁有关」，
个人记忆回答「**这个人**盯过谁、判过什么、还欠哪些判断」。

设计纪律（最重要的一条）
------------------------
**观察（observation）与结论（conclusion）必须分开。**

当前真实数据非常薄：p2_state.json 里 feedback=[]、monitoring=[]，只有 1 条 Watchlist；
review_queue 里只有 11 条已落决策，且 11 条的 urgency 全是 `watch`、决策对象**不带时间戳**。
在这种样本上直接输出「用户偏好 X」就是编造。所以本模块：

* 任何分布一律先作为 `observations` 如实给出，并附 `sample_size`；
* 只有当 `sample_size >= MIN_SAMPLE_FOR_CONCLUSION` 时才写 `conclusions`；
* 不足时 `conclusions` 为空数组，并给出 `conclusion_blocked`（差多少、要什么）；
* 推不出的维度写进 `gaps`，带 `reason` 与 `unblock`（解锁条件），不静默省略。

另有一条硬边界：**不伪造时间线**。决策对象没有时间戳，因此记忆条目按 event_id 组织，
不声称任何先后顺序；事件时间只取自图谱 Event 节点的 published_at，并明确标注它是
「事件发布时间」而非「决策时间」。

数据来源（全部为既有 artifact，本模块不生产新事实）
--------------------------------------------------
* p2_state.json      : watchlists / feedback / monitoring
* review_queue.json  : 每条含 decision（已决）或 decision=null（待决）
* p2_daily_brief.json: 简报条目，含 watchlist_matches 与 entities
* knowledge_graph.json: Event 节点的 **name 即 event_id**（已核验 100/100 命中），
                        据此把事件接到 Company 实体上，派生「关注主体」

用法
----
    python3 p2_personal_memory.py [--out p2_personal_memory.json] [--validate-only]
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
OUTPUT_PATH = ROOT / "p2_personal_memory.json"

VERSION = "p2.5-v1.0"

# 低于这个样本量只出观察、不出结论。
# 为什么是 30：11 条已决决策里单一 action 就占了 6 条，任何比例都会被单条决策大幅晃动；
# 30 是能把「某类 action 占比」的置信区间压到 ±18pp 以内的保守下限。
MIN_SAMPLE_FOR_CONCLUSION = 30

# 参与「关注主体」派生的关系：Event --PARTICIPATES_IN--> Company
ENTITY_RELATIONS = ("PARTICIPATES_IN",)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load(path: Path) -> dict:
    """读 artifact；不存在时抛明确错误（fail-closed，不静默产出残缺记忆）。"""
    if not path.exists():
        raise FileNotFoundError(f"缺少输入 artifact: {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def _top(counter: Counter, n: int) -> list[dict]:
    """Counter → [{key, count}]，同票按 key 升序，保证输出可复现。"""
    return [{"key": k, "count": c} for k, c in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[:n]]


def _dist(items: list[dict], field: str) -> dict[str, int]:
    return dict(Counter(i.get(field) for i in items if i.get(field) is not None))


# --------------------------------------------------------------------------
# 图谱索引：event_id → 事件的实体邻居与发布时间
# --------------------------------------------------------------------------
def build_event_index(graph: dict) -> dict[str, dict]:
    """Event 节点的 name 就是 review_queue / daily_brief 里的 event_id（已核验 100/100）。

    只取一跳、且只取 ENTITY_RELATIONS 指定的关系——不做多跳扩散，
    避免把「同 Event 同 Claim」这类弱关联也算成用户关注过某主体。
    """
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    by_id = {n["id"]: n for n in nodes}

    neighbors: dict[str, list[tuple[str, str]]] = {}
    for e in edges:
        neighbors.setdefault(e["source"], []).append((e["target"], e["relationship"]))
        neighbors.setdefault(e["target"], []).append((e["source"], e["relationship"]))

    index: dict[str, dict] = {}
    for n in nodes:
        if n.get("type") != "Event":
            continue
        event_id = n.get("name")
        if not event_id:
            continue
        entities: list[str] = []
        for tid, rel in neighbors.get(n["id"], []):
            if rel not in ENTITY_RELATIONS:
                continue
            target = by_id.get(tid)
            if target and target.get("name"):
                entities.append(target["name"])
        index[event_id] = {
            "topic": n.get("topic"),
            # published_at 是**事件发布时间**，不是用户看到或决策的时间，勿混用
            "published_at": n.get("published_at"),
            "entities": sorted(set(entities)),
        }
    return index


# --------------------------------------------------------------------------
# 关注清单：定义（来自 state）+ 实际命中（来自 brief）
# --------------------------------------------------------------------------
def watchlist_profile(
    watchlists: list[dict],
    brief_items: list[dict],
) -> dict[str, Any]:
    enabled = [w for w in watchlists if w.get("enabled") is not False]
    per: list[dict] = []
    hit_topics: Counter = Counter()
    hit_entities: Counter = Counter()
    hit_event_ids: set[str] = set()

    for w in enabled:
        wid = w.get("id")
        matched = [e for e in brief_items if wid in (e.get("watchlist_matches") or [])]
        for e in matched:
            if e.get("topic"):
                hit_topics[e["topic"]] += 1
            for ent in e.get("entities") or []:
                hit_entities[ent] += 1
            if e.get("event_id"):
                hit_event_ids.add(e["event_id"])
        per.append(
            {
                "id": wid,
                "name": w.get("name") or wid,
                "topics": w.get("topics") or [],
                "keywords": w.get("keywords") or [],
                "priority_boost": w.get("priority_boost"),
                "updated_at": w.get("updated_at"),
                # 以下为派生事实：命中数来自 brief 的 watchlist_matches，非推测
                "hit_count": len(matched),
                "hit_topics": _dist(matched, "topic"),
                "hit_terms": _top(Counter(ent for e in matched for ent in (e.get("entities") or [])), 8),
            }
        )

    return {
        "enabled_count": len(enabled),
        "items": per,
        "total_hits": sum(p["hit_count"] for p in per),
        "distinct_hit_events": len(hit_event_ids),
        "top_topics": _top(hit_topics, 8),
        # 命名说明：这里叫 terms 不叫 entities —— 它们来自 brief 的 entities 字段，
        # 是**抽取出的原始词**（含 "ai" 这类关键词碎片），未经归一化。
        # 真正的图谱实体在 entity_affinity 里，两者不可混为一谈。
        "top_terms": _top(hit_entities, 10),
        "hit_event_ids": sorted(hit_event_ids),
    }


# --------------------------------------------------------------------------
# 决策画像：观察与结论分离
# --------------------------------------------------------------------------
def _norm_decision_record(item: dict) -> dict:
    """把复核队列条目或账本条目统一为决策记录。

    - 复核队列条目：decision 嵌套在 item["decision"] 中。
    - 账本条目（decisions_ledger.json）：本身就是决策记录（无嵌套 decision）。
    """
    dec = item.get("decision") or {}
    if not dec and ("urgency" in item or "decided_at" in item):
        dec = item
    return {
        "event_id": item.get("event_id"),
        "topic": item.get("topic"),
        "event_type": item.get("event_type"),
        "urgency": dec.get("urgency"),
        "action": dec.get("action"),
        "decided_at": dec.get("decided_at"),
    }


def decision_profile(records: list[dict]) -> dict[str, Any]:
    n = len(records)
    has_time = any(r.get("decided_at") for r in records)
    observations = {
        "sample_size": n,
        "by_urgency": _dist(records, "urgency"),
        "by_action": _dist(records, "action"),
        "by_topic": _dist(records, "topic"),
        "by_event_type": _dist(records, "event_type"),
        "has_decided_at": has_time,
    }

    if n == 0:
        return {
            "observations": observations,
            "timeline": [],
            "conclusions": [],
            "conclusion_blocked": {
                "reason": "尚无任何已落决策",
                "need": f"累计 {MIN_SAMPLE_FOR_CONCLUSION} 条决策后开始输出偏好结论",
            },
        }
    if n < MIN_SAMPLE_FOR_CONCLUSION:
        return {
            "observations": observations,
            "timeline": _decision_timeline(records) if has_time else [],
            "conclusions": [],
            "conclusion_blocked": {
                "reason": f"样本仅 {n} 条，低于 {MIN_SAMPLE_FOR_CONCLUSION} 条阈值；"
                f"且已落决策的 urgency 取值单一（{sorted(set(observations['by_urgency']))}），无区分度",
                "need": f"再累计 {MIN_SAMPLE_FOR_CONCLUSION - n} 条真实决策（来自决策账本，不伪造）",
            },
        }

    conclusions: list[dict] = []
    urgency = observations["by_urgency"]
    if urgency:
        top = max(urgency.items(), key=lambda kv: (kv[1], kv[0]))
        conclusions.append(
            {
                "type": "urgency_preference",
                "statement": f"最常采用的处置节奏是 {top[0]}（{top[1]}/{n}）",
                "basis": "决策账本/复核队列的 decision.urgency 分布（真实累计，不伪造）",
            }
        )
    return {
        "observations": observations,
        "timeline": _decision_timeline(records) if has_time else [],
        "conclusions": conclusions,
        "conclusion_blocked": None,
    }


def _decision_timeline(records: list[dict]) -> list[dict]:
    """按 decided_at 升序产出决策时间线（E2 解锁的记忆时间线）。"""
    return sorted(
        (
            {"event_id": r.get("event_id"), "decided_at": r["decided_at"], "urgency": r.get("urgency")}
            for r in records
            if r.get("decided_at")
        ),
        key=lambda x: x["decided_at"],
    )


# --------------------------------------------------------------------------
# 关注主体：把事件接到 Company 实体上
# --------------------------------------------------------------------------
def entity_affinity(
    event_index: dict[str, dict],
    acted_event_ids: list[str],
    watched_event_ids: list[str],
) -> dict[str, Any]:
    def collect(ids: list[str]) -> Counter:
        c: Counter = Counter()
        for eid in ids:
            for ent in event_index.get(eid, {}).get("entities", []):
                c[ent] += 1
        return c

    acted_c = collect(acted_event_ids)
    watched_c = collect(watched_event_ids)
    both = Counter({k: v for k, v in watched_c.items() if k in acted_c})

    return {
        "basis": "knowledge_graph.json 中 Event --PARTICIPATES_IN--> Company 的一跳邻居（不做多跳扩散）",
        "acted_entities": _top(acted_c, 10),
        "watched_entities": _top(watched_c, 10),
        # 既进过关注清单命中、又有已决决策的主体 —— 个人记忆里最值得记住的一批
        "overlap_entities": _top(both, 10),
        "acted_event_count": len(acted_event_ids),
        "watched_event_count": len(watched_event_ids),
        # 数据质量声明：图谱的 Company 节点存在抽取噪声（把标题片段当成机构名收录）。
        # 本层**不做静默清洗**——那等于用一个自己发明的启发式规则替用户决定真相。
        # 正确做法是在图谱构建侧收紧抽取约束，这里只负责把问题显式暴露出来。
        "quality": {
            "cleaning": "none",
            "caveat": "Company 节点来自上游实体抽取，含标题片段噪声（如把句首状语当成机构名收录），"
            "因此 acted_entities / overlap_entities 中可能出现非机构条目。",
            "where_to_fix": "knowledge_graph.py 的实体抽取侧（本模块的下游清洗只会掩盖问题）",
        },
    }


# --------------------------------------------------------------------------
# 待决积压：还欠哪些判断
# --------------------------------------------------------------------------
def backlog_profile(pending: list[dict]) -> dict[str, Any]:
    return {
        "sample_size": len(pending),
        "by_topic": _dist(pending, "topic"),
        "by_event_type": _dist(pending, "event_type"),
        "by_trust_level": _dist(pending, "trust_level"),
        "top_by_priority": [
            {
                "event_id": i.get("event_id"),
                "title": i.get("title"),
                "priority": i.get("priority"),
                "topic": i.get("topic"),
            }
            for i in sorted(pending, key=lambda x: (-(x.get("priority") or 0), x.get("event_id") or ""))[:10]
        ],
    }


# --------------------------------------------------------------------------
# 缺口：明确写出「推不出什么、为什么、怎么解锁」
# --------------------------------------------------------------------------
def memory_gaps(
    feedback: list[dict],
    monitoring: list[dict],
    sample_size: int,
    has_decided_at: bool,
) -> list[dict]:
    gaps: list[dict] = []

    if not feedback:
        gaps.append(
            {
                "dimension": "反馈偏好（useful/noise/incorrect…）",
                "status": "empty",
                "reason": "p2_state.json 的 feedback 为空数组 —— 尚无任何显式反馈记录",
                "unblock": "在 Human Review（review-ui.html）中对条目给出 label（useful/important/noise/irrelevant/incorrect/acted_on）后自动填充",
            }
        )
    if not monitoring:
        gaps.append(
            {
                "dimension": "持续跟踪偏好（snoozed/resolved）",
                "status": "empty",
                "reason": "p2_state.json 的 monitoring 为空数组 —— 尚无跟踪书签",
                "unblock": "在 Human Review 中对事件启用跟踪（active）或抑制（snoozed/resolved）后自动填充",
            }
        )

    if sample_size < MIN_SAMPLE_FOR_CONCLUSION:
        gaps.append(
            {
                "dimension": "决策偏好结论",
                "status": "insufficient_sample",
                "reason": f"已决决策样本 {sample_size} 条 < 阈值 {MIN_SAMPLE_FOR_CONCLUSION} 条；"
                "结论需 ≥30 条真实决策方可输出（来自决策账本 decisions_ledger.json，不伪造）",
                "unblock": f"日常流水线持续运行使决策账本累计至 ≥{MIN_SAMPLE_FOR_CONCLUSION} 条不同事件",
            }
        )

    # 记忆时间线：仅当决策普遍缺少 decided_at 时才结构性不可得；
    # E2 已为 decision 写入真实 decided_at，故一旦样本带时间戳即解锁。
    if not has_decided_at:
        gaps.append(
            {
                "dimension": "记忆时间线（按决策先后排序）",
                "status": "structurally_unavailable",
                "reason": "decision 对象只有 urgency 与 action 两个字段，没有决策时间戳；"
                "按其他字段排序等于伪造先后顺序",
                "unblock": "在 decision 中记录 decided_at（引擎真实产出时间，非用户决策时间），本模块即产出按时间排序的记忆条目",
            }
        )
    # 上游图谱实体抽取噪声：会污染「关注主体」，但根因不在本层
    gaps.append(
        {
            "dimension": "关注主体准确性",
            "status": "upstream_noise",
            "reason": "knowledge_graph.json 的 Company 节点存在抽取噪声：标题片段被当成机构名收录"
            "（例如从「随着再保险公司/保险公司寻求…」抽出「随着再保险公司」）。"
            "本层不静默清洗，否则等于用启发式规则替用户决定真相。",
            "unblock": "在 knowledge_graph.py 的实体抽取侧收紧约束（如过滤句首状语片段、"
            "限制机构名长度与词性模式），清洗后本层的 acted_entities 会自动变干净",
        }
    )
    return gaps


# --------------------------------------------------------------------------
# 组装
# --------------------------------------------------------------------------
def _load_ledger_records(path: Path) -> list[dict]:
    """读决策账本（decisions_ledger.json）并归一化为决策记录。

    账本缺位不报错——它属于流水线前置环节（CI 中 decision_ledger.py 先于本模块运行）；
    本地单独跑本模块时若无账本，自动回退到复核队列已决条目作为样本，结论纪律不变。
    """
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [_norm_decision_record(e) for e in (data.get("entries") or [])]


def build(
    state: dict,
    queue: dict,
    brief: dict,
    graph: dict | None = None,
    generated_at: str | None = None,
    ledger_path: Path | None = None,
) -> dict[str, Any]:
    watchlists = state.get("watchlists") or []
    feedback = state.get("feedback") or []
    monitoring = state.get("monitoring") or []
    items = queue.get("items") or []
    brief_items = brief.get("brief") or []

    acted_review = [i for i in items if i.get("decision")]
    pending = [i for i in items if not i.get("decision")]

    # 复核队列已决条目（带 rich context：title/topic/event_type/priority/entities 来源）
    review_records = [_norm_decision_record(i) for i in acted_review]

    # 决策账本：跨日按 event_id 去重累计的真实决策，提供**诚实**的样本量。
    # 账本条目只含 {event_id, role, urgency, action, decided_at}；
    # 用复核队列里同 event_id 的 topic/event_type 补全，信息来自同源事件、无损。
    ledger_records = _load_ledger_records(ledger_path or (ROOT / "decisions_ledger.json"))
    review_by_eid = {r["event_id"]: r for r in review_records if r.get("event_id")}
    for rec in ledger_records:
        src = review_by_eid.get(rec.get("event_id"))
        if src:
            rec.setdefault("topic", src.get("topic"))
            rec.setdefault("event_type", src.get("event_type"))

    # 决策画像的样本 = 账本累计（诚实口径）；账本缺位时退回复核队列已决条目。
    records = ledger_records if ledger_records else review_records
    sample_size = len(records)
    has_decided_at = any(r.get("decided_at") for r in records)

    event_index = build_event_index(graph) if graph else {}
    wl = watchlist_profile(watchlists, brief_items)

    return {
        "version": VERSION,
        "generated_at": generated_at or _now(),
        "principle": "只聚合既有 artifact 中的事实；观察与结论分离，样本不足时不出结论，不伪造时间线",
        "sources": {
            "p2_state.json": {"watchlists": len(watchlists), "feedback": len(feedback), "monitoring": len(monitoring)},
            "review_queue.json": {"items": len(items), "decided": len(acted_review), "pending": len(pending)},
            "p2_daily_brief.json": {"brief": len(brief_items)},
            "knowledge_graph.json": {"events_indexed": len(event_index)} if graph else None,
            "decisions_ledger.json": {"distinct_events": sample_size} if ledger_records else None,
        },
        "watchlists": wl,
        "decisions": decision_profile(records),
        "entity_affinity": entity_affinity(
            event_index,
            sorted({i.get("event_id") for i in acted_review if i.get("event_id")}),
            wl["hit_event_ids"],
        ),
        "backlog": backlog_profile(pending),
        "gaps": memory_gaps(feedback, monitoring, sample_size, has_decided_at),
        "memory_entries": [
            {
                "event_id": i.get("event_id"),
                "title": i.get("title"),
                "topic": i.get("topic"),
                "event_type": i.get("event_type"),
                "priority": i.get("priority"),
                "decision": i.get("decision"),
                # E2：decided_at 是引擎真实产出时间（UTC），刻意与 event_published_at 区分
                "decided_at": (i.get("decision") or {}).get("decided_at"),
                # 明确标注这是事件发布时间，不是决策时间
                "event_published_at": event_index.get(i.get("event_id"), {}).get("published_at"),
                "entities": event_index.get(i.get("event_id"), {}).get("entities", []),
            }
            for i in sorted(acted_review, key=lambda x: (-(x.get("priority") or 0), x.get("event_id") or ""))
        ],
    }


def validate(doc: dict) -> None:
    """fail-closed 校验：结构不对就让 CI 红，而不是让页面静默显示空记忆。"""
    assert doc.get("version") == VERSION, f"version 错误: {doc.get('version')}"
    for key in (
        "generated_at",
        "principle",
        "sources",
        "watchlists",
        "decisions",
        "entity_affinity",
        "backlog",
        "gaps",
        "memory_entries",
    ):
        assert key in doc, f"缺少字段: {key}"

    obs = doc["decisions"]["observations"]
    assert isinstance(obs["sample_size"], int) and obs["sample_size"] >= 0, obs
    assert isinstance(obs.get("has_decided_at"), bool), "decisions.observations.has_decided_at 必须为布尔"

    # 核心纪律：样本不足时 conclusions 必须为空，且必须给出阻塞原因
    if obs["sample_size"] < MIN_SAMPLE_FOR_CONCLUSION:
        assert doc["decisions"]["conclusions"] == [], "样本不足却输出了结论"
        assert doc["decisions"]["conclusion_blocked"], "样本不足却未给出阻塞原因"

    # 记忆条目来自复核队列已决事件（含 rich context），其数量必须等于复核队列已决数，
    # 而非账本累计样本量（账本含无 rich context 的引擎决策，两者口径不同、不可混比）。
    decided = (doc["sources"].get("review_queue.json") or {}).get("decided")
    assert decided is not None, "sources.review_queue.json.decided 缺失"
    assert len(doc["memory_entries"]) == decided, "记忆条目数与复核队列已决数不一致"
    for e in doc["memory_entries"]:
        assert e.get("event_id"), f"记忆条目缺少 event_id: {e}"
        assert e.get("decision"), f"记忆条目不应包含未决事件: {e}"

    assert isinstance(doc["gaps"], list) and doc["gaps"], "gaps 不得为空（推不出的维度必须显式记录）"


def run(
    state_path: Path | None = None,
    queue_path: Path | None = None,
    brief_path: Path | None = None,
    graph_path: Path | None = None,
    ledger_path: Path | None = None,
    out_path: Path | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    state = _load(state_path or ROOT / "p2_state.json")
    queue = _load(queue_path or ROOT / "review_queue.json")
    brief = _load(brief_path or ROOT / "p2_daily_brief.json")

    # 图谱是可选输入：缺它只是派不出「关注主体」，其余记忆照常产出
    graph: dict | None = None
    gp = graph_path or ROOT / "knowledge_graph.json"
    if gp.exists():
        graph = json.loads(gp.read_text(encoding="utf-8"))

    doc = build(state, queue, brief, graph, ledger_path=ledger_path or (ROOT / "decisions_ledger.json"))
    validate(doc)
    if persist:
        (out_path or OUTPUT_PATH).write_text(
            json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return doc


def main() -> int:
    parser = argparse.ArgumentParser(description="构建 Personal Memory（个人记忆层）")
    parser.add_argument("--out", default=str(OUTPUT_PATH))
    parser.add_argument("--validate-only", action="store_true", help="只校验已有产物，不重新生成")
    args = parser.parse_args()

    out = Path(args.out)
    if args.validate_only:
        validate(json.loads(out.read_text(encoding="utf-8")))
        d = json.loads(out.read_text(encoding="utf-8"))
        print(
            json.dumps(
                {
                    "sample_size": d["decisions"]["observations"]["sample_size"],
                    "conclusions": len(d["decisions"]["conclusions"]),
                    "gaps": len(d["gaps"]),
                    "memory_entries": len(d["memory_entries"]),
                },
                ensure_ascii=False,
            )
        )
        return 0

    doc = run(out_path=out)
    print(
        f"p2_personal_memory.json 已生成 | "
        f"已决决策 {doc['decisions']['observations']['sample_size']} 条 → "
        f"结论 {len(doc['decisions']['conclusions'])} 条（阈值 {MIN_SAMPLE_FOR_CONCLUSION}）· "
        f"关注主体 {len(doc['entity_affinity']['acted_entities'])} 个 · "
        f"缺口 {len(doc['gaps'])} 项"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
