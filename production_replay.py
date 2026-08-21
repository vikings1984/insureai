#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Replay production news through the deterministic intelligence pipeline.

第一性原理：真实生产数据上的稳定性比手工案例更能发现回归；缺少生产数据时必须显式报告 unavailable，绝不伪造通过。
"""
from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from intelligence import build

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data.json"
SEED = 20260821
MAX_ITEMS = 500


def _load_news() -> list[dict]:
    raw = json.loads(DATA.read_text(encoding="utf-8"))
    rows = raw.get("news", []) if isinstance(raw, dict) else []
    return rows if isinstance(rows, list) else []


def _sample(rows: list[dict], limit: int = MAX_ITEMS) -> list[dict]:
    if len(rows) <= limit:
        return list(rows)
    buckets: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        key = str(row.get("research_topic") or row.get("topic") or "general")
        buckets[key].append(row)
    rng = random.Random(SEED)
    selected: list[dict] = []
    topics = sorted(buckets)
    while len(selected) < limit and topics:
        progressed = False
        for topic in topics:
            pool = buckets[topic]
            if not pool:
                continue
            selected.append(pool.pop(rng.randrange(len(pool))))
            progressed = True
            if len(selected) >= limit:
                break
        if not progressed:
            break
    return selected


def _partition(events: list[dict]) -> dict[str, tuple[str, ...]]:
    out: dict[str, list[str]] = defaultdict(list)
    for event in events:
        event_key = event.get("event_id") or ""
        for article_id in event.get("article_ids", []) or []:
            out[str(article_id)].append(str(event_key))
    return {k: tuple(sorted(v)) for k, v in out.items()}


def _integrity(events: list[dict], sample_ids: set[str]) -> dict:
    event_ids = [str(e.get("event_id")) for e in events]
    duplicate_event_ids = len(event_ids) - len(set(event_ids))
    seen_articles: list[str] = []
    for event in events:
        seen_articles.extend(str(x) for x in event.get("article_ids", []) or [])
    duplicate_article_assignments = len(seen_articles) - len(set(seen_articles))
    covered = len(set(seen_articles) & sample_ids)
    return {
        "duplicate_event_ids": duplicate_event_ids,
        "duplicate_article_assignments": duplicate_article_assignments,
        "article_coverage": round(covered / len(sample_ids), 4) if sample_ids else 0,
    }


def run_replay() -> dict:
    rows = _load_news()
    if not rows:
        return {
            "status": "unavailable",
            "reason": "data.json contains no news items; replay requires real production data",
            "input_count": 0,
            "sample_count": 0,
            "quality": None,
        }

    sample = _sample(rows)
    first = build({"news": sample})
    shuffled = list(sample)
    random.Random(SEED).shuffle(shuffled)
    second = build({"news": shuffled})

    first_partition = _partition(first.get("events", []))
    second_partition = _partition(second.get("events", []))
    stable_ids = set(first_partition) & set(second_partition)
    stable = sum(1 for key in stable_ids if first_partition[key] == second_partition[key])
    stability = round(stable / len(stable_ids), 4) if stable_ids else 0

    integrity = _integrity(first.get("events", []), {str(x.get("id")) for x in sample})
    source_counts = Counter(str(x.get("source_name") or "unknown") for x in sample)

    return {
        "status": "ok",
        "input_count": len(rows),
        "sample_count": len(sample),
        "event_count": len(first.get("events", [])),
        "quality": {
            "replay_stability": stability,
            "event_integrity": integrity,
            "source_diversity": len(source_counts),
            "top_source_share": round(max(source_counts.values()) / len(sample), 4) if sample else 0,
        },
    }


if __name__ == "__main__":
    result = run_replay()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] in {"ok", "unavailable"} else 1)
