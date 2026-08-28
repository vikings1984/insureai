#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Preset queries over the traceable knowledge graph (P1-3 KG-2).

Query layer only -- it reads knowledge_graph.json and never rebuilds it.
The 90-day window anchors on the graph's own ``latest_event_at`` so the
answer is reproducible regardless of when the query runs.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GRAPH = ROOT / "knowledge_graph.json"
DEFAULT_WINDOW_DAYS = 90


def _parse(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None


def _load_graph(graph: dict | None) -> dict:
    if graph is not None:
        return graph
    if not GRAPH.exists():
        return {"nodes": [], "edges": [], "stats": {}}
    return json.loads(GRAPH.read_text(encoding="utf-8"))


def _adjacency(graph: dict) -> tuple[dict, dict]:
    nodes = {n["id"]: n for n in graph.get("nodes", [])}
    by_name: dict[str, list[dict]] = {}
    for node in nodes.values():
        by_name.setdefault((node.get("name") or "").strip().lower(), []).append(node)
    neighbors: dict[str, list[tuple[dict, dict]]] = {}
    for edge in graph.get("edges", []):
        src, dst = edge.get("source"), edge.get("target")
        if src in nodes and dst in nodes:
            neighbors.setdefault(src, []).append((edge, nodes[dst]))
            neighbors.setdefault(dst, []).append((edge, nodes[src]))
    return by_name, neighbors


def _window(graph: dict, days: int, now: datetime | None) -> tuple[datetime, datetime]:
    end = now or _parse((graph.get("stats") or {}).get("latest_event_at")) or datetime.now().astimezone()
    return end - timedelta(days=days), end


def entity_recent(graph: dict | None = None, entity_name: str = "", days: int = DEFAULT_WINDOW_DAYS, now: datetime | None = None) -> dict:
    """Preset query 1: 某实体最近 N 天发生了什么（entity -> adjacent Event/Claim）."""
    graph = _load_graph(graph)
    by_name, neighbors = _adjacency(graph)
    start, end = _window(graph, days, now)
    matched = by_name.get((entity_name or "").strip().lower(), [])
    events: list[dict] = []
    claims: list[dict] = []
    seen_events: set[str] = set()
    for node in matched:
        for _edge, other in neighbors.get(node["id"], []):
            if other["type"] == "Event":
                ts = _parse(other.get("published_at"))
                if ts and start <= ts <= end:
                    events.append({"event_id": other["name"], "title": other.get("title"), "topic": other.get("topic"),
                                   "published_at": other.get("published_at"), "trust": (other.get("trust") or {}).get("level"),
                                   "evidence_status": other.get("evidence_status"), "source_count": other.get("source_count")})
                    seen_events.add(other["id"])
            elif other["type"] == "Claim":
                # Claim 无时间戳：经 INVOLVES 回到所属 Event 取时间。
                event_at = None
                for _c_edge, c_other in neighbors.get(other["id"], []):
                    if c_other["type"] == "Event":
                        event_at = c_other.get("published_at")
                        break
                ts = _parse(event_at)
                if ts and start <= ts <= end:
                    claims.append({"claim_id": other["name"], "claim_text": other.get("claim_text"),
                                   "claim_type": other.get("claim_type"), "verification_status": other.get("verification_status"),
                                   "confidence": other.get("confidence"), "published_at": event_at})
    events.sort(key=lambda x: x["published_at"] or "", reverse=True)
    claims.sort(key=lambda x: x["published_at"] or "", reverse=True)
    return {
        "query": "entity_recent",
        "entity": entity_name,
        "matched_types": sorted({n["type"] for n in matched}),
        "days": days,
        "window": [start.isoformat(), end.isoformat()],
        "events": events,
        "claims": claims,
        "total": len(events) + len(claims),
    }


def topic_crossover(graph: dict | None = None, topics: list[str] | None = None) -> dict:
    """Preset query 2: 哪些主体同时布局多个 Topic（Topic x Entity 交叉）."""
    graph = _load_graph(graph)
    topics = [t for t in (topics or []) if t]
    by_name, neighbors = _adjacency(graph)
    wanted = {t.lower() for t in topics}
    entities: list[dict] = []
    if len(wanted) < 2:
        return {"query": "topic_crossover", "topics": topics, "entities": [], "note": "至少提供 2 个 topic 才能交叉"}
    for node in graph.get("nodes", []):
        if node["type"] not in {"Company", "Person"}:
            continue
        shared: dict[str, list[dict]] = {}
        for _edge, other in neighbors.get(node["id"], []):
            if other["type"] != "Event":
                continue
            topic = (other.get("topic") or "").strip().lower()
            if topic in wanted:
                shared.setdefault(topic, []).append({"event_id": other["name"], "title": other.get("title"), "published_at": other.get("published_at")})
        if len(shared) == len(wanted):
            entities.append({
                "entity": node["name"],
                "type": node["type"],
                "topics": {topic: sorted(events, key=lambda x: x["published_at"] or "")[-3:] for topic, events in shared.items()},
                "event_count": sum(len(v) for v in shared.values()),
            })
    entities.sort(key=lambda x: -x["event_count"])
    return {"query": "topic_crossover", "topics": topics, "entities": entities[:20], "total": len(entities)}


def neighbors_of(graph: dict | None = None, node_id: str = "") -> dict:
    """KG-1 neighbor expansion: one hop around a node, with edge relationship kept."""
    graph = _load_graph(graph)
    nodes = {n["id"]: n for n in graph.get("nodes", [])}
    _, neighbors = _adjacency(graph)
    center = nodes.get(node_id)
    if not center:
        return {"query": "neighbors", "node_id": node_id, "neighbors": [], "note": "node not found"}
    rows = []
    for edge, other in neighbors.get(node_id, []):
        forward = edge.get("source") == node_id
        rows.append({
            "node_id": other["id"], "name": other.get("name"), "type": other["type"],
            "relationship": edge.get("relationship"),
            "direction": "out" if forward else "in",
            "confidence": edge.get("confidence"),
        })
    rows.sort(key=lambda x: (x["type"], -float(x["confidence"] or 0)))
    return {"query": "neighbors", "node_id": node_id, "node": {"name": center.get("name"), "type": center.get("type")}, "neighbors": rows, "total": len(rows)}


def main() -> None:
    graph = _load_graph(None)
    stats = graph.get("stats") or {}
    print(json.dumps({"stats": stats}, ensure_ascii=False))
    example = entity_recent(graph, "")
    print(json.dumps({"entity_recent": {"entity": example["entity"], "total": example["total"]}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
