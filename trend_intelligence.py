#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Trend intelligence layer: event clusters as the radar statistics unit.

P1-1 TRD-1（v1.5 路线图）：topic 内相似事件聚为 event cluster，cluster 作为
radar 的统计单元。相似度复用 intelligence._event_similarity（同一判定口径，
避免两套聚类漂移）。本模块读取 intelligence.json，产出独立工件 radar.json：
topic_trends（含动力学与解释）+ event_clusters 明细 + cluster 与 topic 的关联。

第一性原理：趋势不是文章计数，而是"同一件事被反复确认"和"多件事同时发生"
的区分——cluster 单元让统计可追溯到事件列表。
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from contract import ARTIFACT_VERSIONS
from intelligence import _event_similarity
from radar import TOPIC_LABELS

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "intelligence.json"
OUTPUT = ROOT / "radar.json"

CLUSTER_SIMILARITY = 0.45
WINDOW_DAYS = 30
MAX_CLUSTERS = 24


def _ts(value):
    try:
        return datetime.fromisoformat((value or "").replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def build_event_clusters(events, now=None, similarity=CLUSTER_SIMILARITY, window_days=WINDOW_DAYS, limit=MAX_CLUSTERS):
    """把 30 天窗口内同 topic 的相似事件聚为 cluster（代表元贪心法）。

    代表元取组内最早事件（时间最旧），保证 cluster_id 与代表标题稳定。
    """
    now = now or datetime.now(timezone.utc)
    horizon = now.timestamp() - window_days * 86400
    by_topic = defaultdict(list)
    for event in events:
        topic = event.get("topic")
        if not topic:
            continue
        if _ts(event.get("published_at")).timestamp() < horizon:
            continue
        by_topic[topic].append(event)

    clusters = []
    for topic in sorted(by_topic):
        rows = sorted(by_topic[topic], key=lambda e: _ts(e.get("published_at")))
        groups = []
        for event in rows:
            matched = None
            best = 0.0
            for group in groups:
                score = _event_similarity(event, group["rep"])
                if score >= similarity and score > best:
                    matched, best = group, score
            if matched:
                matched["events"].append(event)
            else:
                groups.append({"rep": event, "events": [event]})
        for group in groups:
            clusters.append({"topic": topic, "rep": group["rep"], "events": group["events"]})

    result = []
    for index, cluster in enumerate(clusters):
        events_in = sorted(cluster["events"], key=lambda e: _ts(e.get("published_at")), reverse=True)
        rep = cluster["rep"]
        entities = defaultdict(int)
        for event in events_in:
            for entity in event.get("entities") or []:
                name = str(entity).strip()
                if len(name) >= 2:
                    entities[name] += 1
        domains = set()
        for event in events_in:
            for row in event.get("evidence") or []:
                domain = str(row.get("domain") or "").lower().strip()
                if domain:
                    domains.add(domain.removeprefix("www."))
        active_days = {_ts(e.get("published_at")).date() for e in events_in}
        persistence = 0
        if active_days:
            day = max(active_days)
            while day in active_days and persistence < window_days:
                persistence += 1
                day -= timedelta(days=1)
        result.append({
            "cluster_id": f"tc_{cluster['topic']}_{index:03d}",
            "topic": cluster["topic"],
            "topic_label": TOPIC_LABELS.get(cluster["topic"], cluster["topic"]),
            "title": rep.get("title"),
            "event_ids": [e.get("event_id") for e in events_in],
            "event_count": len(events_in),
            "core_entities": [name for name, _ in sorted(entities.items(), key=lambda x: (-x[1], x[0]))[:5]],
            "source_domains": sorted(domains),
            "source_diversity": len(domains),
            "first_seen": _ts(events_in[-1].get("published_at")).isoformat(),
            "last_seen": _ts(events_in[0].get("published_at")).isoformat(),
            "persistence": persistence,
        })

    result.sort(key=lambda c: (c["event_count"], c["source_diversity"], c["persistence"]), reverse=True)
    return result


def attach_cluster_ids(topic_trends, clusters, window_days=WINDOW_DAYS):
    """给每条 topic_trend 关联 7 天内活跃的 cluster_id（可追溯单元）。

    关联用全量 cluster；明细输出由调用方截断，避免 top-N 截断
    拉低 topic 级别的 cluster 覆盖率。
    """
    now = datetime.now(timezone.utc)
    horizon = now.timestamp() - 7 * 86400
    by_topic = defaultdict(list)
    for cluster in clusters:
        if _ts(cluster["last_seen"]).timestamp() >= horizon:
            by_topic[cluster["topic"]].append(cluster["cluster_id"])
    trends = []
    for trend in topic_trends:
        trend["cluster_ids"] = by_topic.get(trend.get("topic"), [])
        trends.append(trend)
    return trends


def build_trend_intelligence(intelligence: dict, now=None) -> dict:
    events = intelligence.get("events") or []
    radar = intelligence.get("radar") or {}
    clusters = build_event_clusters(events, now=now)
    trends = attach_cluster_ids(radar.get("topic_trends") or [], clusters)
    version = ARTIFACT_VERSIONS["radar.json"]
    return {
        "version": version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "principle": "趋势动力学只描述已发生的事件分布；cluster 是 radar 的统计单元，每条趋势可追溯到事件列表",
        "topic_trends": trends,
        "event_clusters": clusters[:MAX_CLUSTERS],
        "stats": {
            "clusters": len(clusters),
            "clustered_events": sum(c["event_count"] for c in clusters),
            "active_clusters": sum(1 for c in clusters if c["cluster_id"] in {cid for t in trends for cid in t["cluster_ids"]}),
            "trending_topics": sum(1 for t in trends if t.get("direction") == "rising"),
            "rising_with_why": sum(1 for t in trends if t.get("direction") == "rising" and t.get("why")),
        },
    }


def main() -> None:
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    result = build_trend_intelligence(data)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    stats = result["stats"]
    print(f"Trend intelligence: {stats['clusters']} clusters / {stats['clustered_events']} events / {stats['trending_topics']} rising topics")


if __name__ == "__main__":
    main()
