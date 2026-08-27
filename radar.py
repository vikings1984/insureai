#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Entity and topic radar layer for InsureAI.

第一性原理：监测的最小单位不是文章，而是“谁/什么主题正在发生变化”。
确定性、可解释、无需外部 API。
"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from math import log1p

from contract import ARTIFACT_VERSIONS

TOPIC_LABELS = {
    "ai_intelligent": "AI智能化", "pension_finance": "养老金融",
    "product_innovation": "产品创新", "channel_transformation": "渠道变革",
    "capital_reinsurance": "资本与再保险", "climate_catastrophe": "气候与巨灾",
    "digital_transformation": "数字化转型", "regulatory_change": "监管变革",
}

ENTITY_STOPWORDS = {
    "insurance", "insurer", "insurers", "reinsurance", "news", "journal",
    "company", "group", "insurance journal", "reinsurance news", "artemis",
    "保险", "公司", "集团", "保险业", "保险公司", "行业",
}


def _ts(value):
    try:
        return datetime.fromisoformat((value or "").replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def _entity_score(events):
    score = 0.0
    for e in events:
        base = float(e.get("scores", {}).get("intelligence_score") or 0)
        age_days = max(0.0, (datetime.now(timezone.utc) - _ts(e.get("published_at"))).total_seconds() / 86400)
        recency = max(0.25, 1.0 - age_days / 30.0)
        source_bonus = min(1.25, 1 + max(0, int(e.get("source_count") or 1) - 1) * 0.08)
        score += base * recency * source_bonus
    return score


def build_entity_radar(events, limit=12):
    buckets = defaultdict(list)
    for event in events:
        for entity in event.get("entities") or []:
            name = str(entity).strip()
            if len(name) < 2 or name.lower() in ENTITY_STOPWORDS:
                continue
            buckets[name.lower()].append(event)

    result = []
    now = datetime.now(timezone.utc)
    for entity, evts in buckets.items():
        evts = sorted(evts, key=lambda e: _ts(e.get("published_at")), reverse=True)
        recent7 = [e for e in evts if (now - _ts(e.get("published_at"))).total_seconds() <= 7 * 86400]
        recent30 = [e for e in evts if (now - _ts(e.get("published_at"))).total_seconds() <= 30 * 86400]
        weighted = _entity_score(evts)
        topic_counts = Counter(e.get("topic_label") or "保险行业" for e in evts)
        type_counts = Counter(e.get("event_type") or "industry_update" for e in evts)
        recent_score = round(sum(float(e.get("scores", {}).get("intelligence_score") or 0) for e in recent7) / max(1, len(recent7)))
        result.append({
            "entity": entity,
            "display_name": max((str(x) for e in evts for x in (e.get("entities") or []) if str(x).strip().lower() == entity), key=len, default=entity),
            "event_count_7d": len(recent7),
            "event_count_30d": len(recent30),
            "weighted_activity": round(weighted),
            "recent_intelligence_score": recent_score,
            "top_topics": [x for x, _ in topic_counts.most_common(3)],
            "event_types": [x for x, _ in type_counts.most_common(3)],
            "latest_event": evts[0].get("title"),
            "latest_event_id": evts[0].get("event_id"),
            "confidence": "high" if len(recent30) >= 3 else ("medium" if len(recent30) >= 2 else "low"),
        })
    result.sort(key=lambda x: (x["weighted_activity"], x["event_count_7d"], x["recent_intelligence_score"]), reverse=True)
    return result[:limit]


def _event_domains(event) -> set:
    domains = set()
    for row in event.get("evidence") or []:
        domain = str(row.get("domain") or "").lower().strip()
        if domain:
            domains.add(domain.removeprefix("www."))
    return domains


def _topic_dynamics(topic_events, now):
    """TRD-2: velocity / acceleration / persistence / source_diversity。

    velocity 为最近 7 天事件数相对前 7 天的变化率；acceleration 为 velocity
    相对再前一个 7 天窗口的变化；persistence 为从最新事件日往前连续有
    事件的天数；source_diversity 为 7 天窗口内的独立域数。
    """
    windows = [[] for _ in range(3)]
    for event in topic_events:
        ts = _ts(event.get("published_at")).timestamp()
        age_days = (now.timestamp() - ts) / 86400
        if 0 <= age_days < 7:
            windows[0].append(event)
        elif 7 <= age_days < 14:
            windows[1].append(event)
        elif 14 <= age_days < 21:
            windows[2].append(event)
    n0, n1, n2 = (len(w) for w in windows)
    velocity = round((n0 - n1) / max(1, n1), 3)
    previous_velocity = round((n1 - n2) / max(1, n2), 3)
    acceleration = round(velocity - previous_velocity, 3)

    active_days = {_ts(e.get("published_at")).date() for e in topic_events}
    persistence = 0
    if active_days:
        day = max(active_days)
        while day in active_days and persistence < 30:
            persistence += 1
            day -= timedelta(days=1)

    domains = set()
    for event in windows[0]:
        domains |= _event_domains(event)
    return {
        "velocity": velocity,
        "acceleration": acceleration,
        "persistence": persistence,
        "source_diversity": len(domains),
        "active_domains": sorted(domains)[:8],
    }


def _trend_why(topic_events, dynamics):
    """TRD-3: 每条趋势附四要素解释，供 UI 直接渲染且可追溯到事件列表。"""
    now = datetime.now(timezone.utc)
    recent = [e for e in topic_events if (now - _ts(e.get("published_at"))).total_seconds() <= 7 * 86400]
    entities = Counter()
    for event in recent:
        for entity in event.get("entities") or []:
            name = str(entity).strip()
            if len(name) >= 2 and name.lower() not in ENTITY_STOPWORDS:
                entities[name] += 1
    domains = set()
    for event in recent:
        domains |= _event_domains(event)
    return {
        "independent_events": len(recent),
        "sources": len(domains),
        "days": dynamics["persistence"],
        "core_entities": [name for name, _ in entities.most_common(3)],
        "event_ids": [e.get("event_id") for e in sorted(recent, key=lambda x: _ts(x.get("published_at")), reverse=True)[:10]],
    }


def build_topic_trends(events, limit=8):
    now = datetime.now(timezone.utc)
    current_start = now.timestamp() - 7 * 86400
    previous_start = now.timestamp() - 14 * 86400
    buckets = defaultdict(lambda: {"current": [], "previous": [], "all": []})
    for event in events:
        topic = event.get("topic")
        if not topic:
            continue
        ts = _ts(event.get("published_at")).timestamp()
        buckets[topic]["all"].append(event)
        if ts >= current_start:
            buckets[topic]["current"].append(event)
        elif ts >= previous_start:
            buckets[topic]["previous"].append(event)

    result = []
    for topic, bucket in buckets.items():
        cur = bucket["current"]
        prev = bucket["previous"]
        current_strength = sum(float(e.get("scores", {}).get("intelligence_score") or 0) for e in cur)
        previous_strength = sum(float(e.get("scores", {}).get("intelligence_score") or 0) for e in prev)
        # 事件强度按事件数归一化，减少单一高分事件对趋势的支配。
        cur_avg = current_strength / max(1, len(cur))
        prev_avg = previous_strength / max(1, len(prev))
        cur_signal = len(cur) * max(1, cur_avg)
        prev_signal = len(prev) * max(1, prev_avg)
        if not cur and not prev:
            continue
        delta = (cur_signal - prev_signal) / max(60.0, prev_signal)
        if not prev:
            direction = "rising" if cur else "stable"
            strength = min(100, round(50 + min(50, len(cur) * 10)))
        elif delta >= 0.25:
            direction = "rising"
            strength = min(100, round(50 + delta * 100))
        elif delta <= -0.25:
            direction = "falling"
            strength = min(100, round(50 + abs(delta) * 100))
        else:
            direction = "stable"
            strength = max(25, min(75, round(65 - abs(delta) * 40)))
        confidence = "low" if len(cur) + len(prev) < 3 else ("medium" if len(cur) + len(prev) < 6 else "high")
        dynamics = _topic_dynamics(bucket["all"], now)
        why = _trend_why(bucket["all"], dynamics)
        result.append({
            "topic": topic,
            "topic_label": TOPIC_LABELS.get(topic, topic),
            "current_7d_events": len(cur),
            "previous_7d_events": len(prev),
            "current_signal": round(cur_signal),
            "previous_signal": round(prev_signal),
            "delta": round(delta, 3),
            "direction": direction,
            "strength": strength,
            "confidence": confidence,
            "velocity": dynamics["velocity"],
            "acceleration": dynamics["acceleration"],
            "persistence": dynamics["persistence"],
            "source_diversity": dynamics["source_diversity"],
            "why": why,
        })
    order = {"rising": 0, "stable": 1, "falling": 2}
    result.sort(key=lambda x: (order.get(x["direction"], 3), -x["strength"], -abs(x["delta"])))
    return result[:limit]


def build_radar(events):
    entities = build_entity_radar(events)
    trends = build_topic_trends(events)
    return {
        "version": ARTIFACT_VERSIONS["radar.json"],
        "entity_radar": entities,
        "topic_trends": trends,
        "principle": "监测谁正在发生变化，以及哪些主题正在形成趋势；趋势动力学（velocity/acceleration/persistence）只描述已发生的事件分布",
        "stats": {
            "entities": len(entities),
            "trending_topics": sum(1 for x in trends if x["direction"] == "rising"),
        },
    }
