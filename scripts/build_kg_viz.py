#!/usr/bin/env python3
"""Knowledge Graph 可视化预采样 —— 把 6MB 的全量图谱压成可即时渲染的子图。

为什么需要这一步
----------------
knowledge_graph.json 目前约 6MB（9805 节点 / 13132 关系）。让浏览器直接抓全量
再在前端做采样，首屏要等数兆字节下载+解析；而力导向布局在千节点以上无论性能
还是可读性都会塌掉。所以把「采样」前移到构建期：本脚本产出一个几百 KB 的
kg_viz.json，页面只抓它。

采样策略（诚实说明边界）
------------------------
* **种子 BFS 扩张**（默认 800 节点 / 60 种子 / 每层每节点最多 6 个邻居）。
  为什么不用「纯按度取 Top-N」：实测那样只留下 555 条边——高节点的邻居多为
  低度的 Evidence/Claim，全被切在采样外，画出来是一盘散沙而不是一张图。
  改为先按度取种子、再逐层把邻居带进来，才能在预算内保住**连通性与边密度**。
* **排除 Topic 枢纽节点**：Topic 只有 8 个，但度高达 420/329/224…。它们会把
  所有事件吸成一团，力导向图失去结构。Topic 改为**节点属性**（topic）保留，
  页面按 Topic 过滤时用的是属性而非连线，过滤后的图反而更清晰。
* 未进入采样的邻居只报**数量**（hidden），不谎报存在。页面显示「+N 个未采样邻居」。

Topic 归属推导
--------------
Event 节点自带 topic 字段。其余节点（Company/Person/Claim/Evidence/Product/
Regulation）通过邻接的 Event 的 topic、或 ABOUT 边直连的 Topic 节点，取出现
次数最多的 topic 作为归属；推不出则为 None。**只传播一跳**，不做多跳扩散，
避免把弱关联也算成归属。

输出 kg_viz.json 结构
---------------------
    version / generated_at
    source      : 全量图谱的 stats 快照（用于页面显示「采样自 X/Y」）
    sampling    : method / limit / node_count / edge_count / excluded_types
    types       : 采样内的节点类型计数
    relationships : 采样内的关系计数
    topics      : 采样内的 topic 计数
    full        : 全量图谱的类型与关系计数（页面图例用）
    nodes       : [{id,name,type,topic,deg,hidden, ...类型专属字段}]
    edges       : [{source,target,relationship,confidence}]

用法
----
    python3 scripts/build_kg_viz.py [--limit 800] [--graph knowledge_graph.json]
             [--out kg_viz.json] [--validate-only]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
GRAPH_PATH = ROOT / "knowledge_graph.json"
OUTPUT_PATH = ROOT / "kg_viz.json"

VERSION = "kg-viz-v1.0"
DEFAULT_LIMIT = 800
DEFAULT_SEEDS = 60    # 种子数：先按度取这些枢纽
DEFAULT_BRANCH = 6    # 每层每个节点最多贡献的邻居数
# Topic 是超级枢纽：进布局会把所有事件吸成一团，故只作属性、不进节点集。
EXCLUDED_TYPES = ("Topic",)

# 类型专属字段：只有这些字段会被带进产物，避免整节点搬运导致体积膨胀。
TYPE_FIELDS: dict[str, tuple[str, ...]] = {
    "Event": ("title", "trust"),
    "Claim": ("claim_text", "claim_type", "verification_status", "confidence"),
    "Evidence": ("source_name", "domain", "published_at"),
    "Company": (),
    "Person": (),
    "Product": ("raw", "semantic_type"),
    "Regulation": ("raw", "semantic_type"),
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def compute_degree(nodes: list[dict], edges: list[dict]) -> dict[str, int]:
    """全量图谱的度（不区分入/出，因为本图谱的关系语义本就双向可读）。"""
    deg: dict[str, int] = defaultdict(int)
    for e in edges:
        deg[e["source"]] += 1
        deg[e["target"]] += 1
    # 孤立节点也要出现在度表里，否则采样时会漏掉它们（度 0）。
    for n in nodes:
        deg.setdefault(n["id"], 0)
    return dict(deg)


def derive_topics(nodes: list[dict], edges: list[dict]) -> dict[str, str | None]:
    """把 Event 的 topic 传播给一跳邻居；推不出则 None。

    两条来源：① 邻接 Event 节点自带的 topic；② 该节点经 ABOUT 边直连的 Topic 节点。
    冲突时取出现次数最多的；次数相同取字典序最小的，保证结果可复现。
    """
    by_id = {n["id"]: n for n in nodes}
    topic_name = {n["id"]: n["name"] for n in nodes if n.get("type") == "Topic"}
    votes: dict[str, Counter] = defaultdict(Counter)

    for e in edges:
        src, dst, rel = e["source"], e["target"], e["relationship"]
        if rel == "ABOUT" and dst in topic_name:
            votes[src][topic_name[dst]] += 1
            continue
        # 其余关系：若一端是 Event 且带 topic，则把 topic 投给另一端
        for a, b in ((src, dst), (dst, src)):
            node = by_id.get(a)
            if node and node.get("type") == "Event" and node.get("topic"):
                votes[b][node["topic"]] += 1

    topics: dict[str, str | None] = {}
    for n in nodes:
        own = n.get("topic") if n.get("type") == "Event" else None
        if own:
            topics[n["id"]] = own
            continue
        counts = votes.get(n["id"])
        if counts:
            # 次数降序、名称升序 → 同票时结果稳定
            topics[n["id"]] = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        else:
            topics[n["id"]] = None
    return topics


def pick_seeds(
    nodes: list[dict],
    degree: dict[str, int],
    topics: dict[str, str | None],
    seeds: int,
    allowed,
) -> list[str]:
    """按 Topic 轮流取种子，保证每个 Topic 都有代表。

    为什么不能「纯按度取 Top-K 种子」：真实图谱里 capital_reinsurance 与
    ai_intelligent 主导了高度节点，纯按度会把 60 个种子几乎全给这两个 Topic，
    导致 pension_finance 之类的_topic 在采样里只剩个位数节点，页面按 Topic 过滤时
    几乎是空图。改为按 Topic 分组后轮流取（round-robin），组内仍按度降序。
    """
    groups: dict[str, list[str]] = defaultdict(list)
    for n in nodes:
        nid = n["id"]
        if not allowed(nid):
            continue
        groups[topics.get(nid) or "∅"].append(nid)
    for members in groups.values():
        members.sort(key=lambda nid: (-degree.get(nid, 0), nid))

    # Topic 按「组内最高度」降序排队，保证轮取顺序可复现
    order = sorted(groups.keys(), key=lambda t: (-degree.get(groups[t][0], 0), t))
    picked: list[str] = []
    idx = 0
    while len(picked) < seeds:
        added = False
        for t in order:
            if idx < len(groups[t]):
                picked.append(groups[t][idx])
                added = True
                if len(picked) >= seeds:
                    break
        if not added:
            break
        idx += 1
    return picked


def select_ids(
    nodes: list[dict],
    edges: list[dict],
    degree: dict[str, int],
    topics: dict[str, str | None],
    limit: int,
    seeds: int = DEFAULT_SEEDS,
    branch: int = DEFAULT_BRANCH,
) -> set[str]:
    """种子 BFS 扩张选点：先按 Topic 分散取种子，再逐层带邻居，保住连通与边密度。

    * 每层每个节点最多贡献 branch 个邻居（默认 6），避免单个枢纽吃掉整份预算，
      也让多个种子公平地长出各自的邻域。
    * 邻居按（度降序，id 升序）排序，同预算内优先保留更重要的邻居，结果可复现。
    """
    by_id = {n["id"]: n for n in nodes}
    allowed = lambda nid: by_id.get(nid, {}).get("type") not in EXCLUDED_TYPES  # noqa: E731

    adj: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        adj[e["source"]].append(e["target"])
        adj[e["target"]].append(e["source"])

    # 种子数不能超过预算，否则 limit < seeds 时 kept 一开始就会突破上限
    frontier: list[str] = pick_seeds(nodes, degree, topics, seeds, allowed)[:limit]
    kept: set[str] = set(frontier)

    while frontier and len(kept) < limit:
        nxt: list[str] = []
        for nid in frontier:
            neighbors = sorted(adj.get(nid, []), key=lambda x: (-degree.get(x, 0), x))
            taken = 0
            for nb in neighbors:
                if taken >= branch:
                    break
                if nb in kept or not allowed(nb):
                    continue
                if len(kept) >= limit:
                    return kept
                kept.add(nb)
                nxt.append(nb)
                taken += 1
        frontier = nxt
    return kept


def sample_nodes(
    nodes: list[dict],
    degree: dict[str, int],
    topics: dict[str, str | None],
    limit: int,
    kept: set[str],
) -> list[dict]:
    """把选中的 id 渲染成产物节点（同度按 id 升序，保证输出顺序可复现）。"""
    picked = [n for n in nodes if n["id"] in kept]
    picked.sort(key=lambda n: (-degree.get(n["id"], 0), n["id"]))

    out: list[dict] = []
    for n in picked:
        nid = n["id"]
        ntype = n.get("type", "Unknown")
        row: dict[str, Any] = {
            "id": nid,
            "name": n.get("name", nid),
            "type": ntype,
            "topic": topics.get(nid),
            "deg": degree.get(nid, 0),
            # hidden 在选边之后回填：未进入采样的邻居数量
            "hidden": 0,
        }
        for field in TYPE_FIELDS.get(ntype, ()):
            if field in n:
                row[field] = n[field]
        out.append(row)
    return out


def build(
    graph: dict,
    limit: int = DEFAULT_LIMIT,
    seeds: int = DEFAULT_SEEDS,
    branch: int = DEFAULT_BRANCH,
    generated_at: str | None = None,
) -> dict[str, Any]:
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    if not nodes:
        raise ValueError("knowledge_graph.json 无节点，拒绝产出空可视化产物")

    degree = compute_degree(nodes, edges)
    topics = derive_topics(nodes, edges)
    kept = select_ids(nodes, edges, degree, topics, limit, seeds=seeds, branch=branch)
    picked_nodes = sample_nodes(nodes, degree, topics, limit, kept)

    picked_edges = [
        {
            "source": e["source"],
            "target": e["target"],
            "relationship": e["relationship"],
            "confidence": e.get("confidence"),
        }
        for e in edges
        if e["source"] in kept and e["target"] in kept
    ]

    # 回填未采样邻居数：全量度 − 采样内度
    inner_deg: dict[str, int] = defaultdict(int)
    for e in picked_edges:
        inner_deg[e["source"]] += 1
        inner_deg[e["target"]] += 1
    for row in picked_nodes:
        row["hidden"] = max(0, row["deg"] - inner_deg.get(row["id"], 0))

    stats = graph.get("stats", {})
    return {
        "version": VERSION,
        "generated_at": generated_at or _now(),
        "source": {
            "version": graph.get("version"),
            "node_count": stats.get("node_count", len(nodes)),
            "edge_count": stats.get("edge_count", len(edges)),
            "latest_event_at": stats.get("latest_event_at"),
        },
        "sampling": {
            "method": "seed_bfs",
            "limit": limit,
            "seeds": seeds,
            "branch": branch,
            "node_count": len(picked_nodes),
            "edge_count": len(picked_edges),
            "excluded_types": list(EXCLUDED_TYPES),
            "note": "Topic 为超级枢纽（度 420/329/224…），仅作节点属性，不进布局",
        },
        "types": dict(Counter(r["type"] for r in picked_nodes)),
        "relationships": dict(Counter(e["relationship"] for e in picked_edges)),
        "topics": dict(Counter(r["topic"] for r in picked_nodes if r["topic"])),
        "full": {
            "types": dict(Counter(n.get("type") for n in nodes)),
            "relationships": dict(Counter(e["relationship"] for e in edges)),
        },
        "nodes": picked_nodes,
        "edges": picked_edges,
    }


def validate(doc: dict) -> None:
    """fail-closed 校验：产物结构不对就让 CI 红，而不是让页面静默显示空图。"""
    assert doc.get("version") == VERSION, f"version 错误: {doc.get('version')}"
    assert doc["sampling"]["node_count"] > 0, "采样结果为空"
    for key in ("source", "sampling", "types", "relationships", "topics", "full", "nodes", "edges"):
        assert key in doc, f"缺少字段: {key}"

    ids = {n["id"] for n in doc["nodes"]}
    assert len(ids) == len(doc["nodes"]), "节点 id 重复"
    for e in doc["edges"]:
        assert e["source"] in ids, f"边指向不存在的节点: {e['source']}"
        assert e["target"] in ids, f"边指向不存在的节点: {e['target']}"
        assert e["confidence"] is None or 0 <= e["confidence"] <= 1, f"confidence 越界: {e}"
    for n in doc["nodes"]:
        assert n["type"] not in EXCLUDED_TYPES, f"被排除的类型不应出现: {n['type']}"
        assert isinstance(n["deg"], int) and n["deg"] >= 0, n
        assert isinstance(n["hidden"], int) and n["hidden"] >= 0, n


def main() -> int:
    parser = argparse.ArgumentParser(description="构建 Knowledge Graph 可视化预采样产物")
    parser.add_argument("--graph", default=str(GRAPH_PATH))
    parser.add_argument("--out", default=str(OUTPUT_PATH))
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--seeds", type=int, default=DEFAULT_SEEDS)
    parser.add_argument("--branch", type=int, default=DEFAULT_BRANCH)
    parser.add_argument("--validate-only", action="store_true", help="只校验已有产物，不重新生成")
    args = parser.parse_args()

    if args.validate_only:
        doc = json.loads(Path(args.out).read_text(encoding="utf-8"))
        validate(doc)
        print(json.dumps(doc["sampling"], ensure_ascii=False))
        return 0

    graph = json.loads(Path(args.graph).read_text(encoding="utf-8"))
    doc = build(graph, limit=args.limit, seeds=args.seeds, branch=args.branch)
    validate(doc)
    Path(args.out).write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    s, smp = doc["source"], doc["sampling"]
    size_kb = Path(args.out).stat().st_size / 1024
    print(
        f"kg_viz.json 已生成：{size_kb:.0f}KB | "
        f"采样 {smp['node_count']} 节点 / {smp['edge_count']} 关系 "
        f"（全量 {s['node_count']}/{s['edge_count']}）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
