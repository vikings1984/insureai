#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Temporal intelligence: turn events into time-based signals.

Principle: a trend is repeated, corroborated change over time, not one noisy article.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone


def _date(value: str | None):
    try:
        return datetime.fromisoformat((value or '').replace('Z', '+00:00')).astimezone(timezone.utc).date()
    except Exception:
        return None


def _week(value: str | None):
    d = _date(value)
    return d.isocalendar()[:2] if d else None


def build_temporal_intelligence(events: list[dict]) -> dict:
    by_topic = defaultdict(list)
    by_entity = defaultdict(list)
    for event in events:
        topic = event.get('topic') or 'general_insurance'
        by_topic[topic].append(event)
        for entity in event.get('entities') or []:
            by_entity[str(entity).lower()].append(event)

    topic_signals = []
    for topic, rows in by_topic.items():
        recent = [e for e in rows if _date(e.get('published_at')) is not None]
        weeks = defaultdict(int)
        for e in recent:
            weeks[_week(e.get('published_at'))] += 1
        ordered = sorted(weeks.items(), key=lambda x: x[0] or (0, 0))
        counts = [count for _, count in ordered[-6:]]
        current = counts[-1] if counts else 0
        previous = counts[-2] if len(counts) >= 2 else 0
        delta = current - previous
        change_pct = round((current / previous - 1) * 100) if previous else (100 if current else 0)
        multi_source = sum(1 for e in recent if e.get('source_count', 1) > 1)
        high_trust = sum(1 for e in recent if e.get('trust', {}).get('level') == 'high')
        strength = min(100, current * 12 + multi_source * 8 + high_trust * 5 + max(0, delta) * 10)
        if current >= 3 and delta > 0:
            phase = 'accelerating'
        elif current >= 2 and delta == 0:
            phase = 'forming'
        elif delta < 0:
            phase = 'cooling'
        else:
            phase = 'isolated'
        topic_signals.append({'topic': topic, 'phase': phase, 'current_period_count': current, 'previous_period_count': previous, 'change_pct': change_pct, 'signal_strength': strength, 'multi_source_events': multi_source, 'high_trust_events': high_trust, 'event_ids': [e.get('event_id') for e in sorted(recent, key=lambda x: x.get('published_at') or '', reverse=True)[:8]]})

    entity_signals = []
    for entity, rows in by_entity.items():
        recent = sorted(rows, key=lambda e: e.get('published_at') or '', reverse=True)[:8]
        source_mentions = sum(int(e.get('source_count') or 0) for e in recent)
        types = len({e.get('event_type') for e in recent})
        active = len(recent)
        momentum = min(100, active * 10 + types * 8 + source_mentions * 2)
        entity_signals.append({'entity': entity, 'event_count': active, 'event_type_count': types, 'source_mentions': source_mentions, 'momentum': momentum, 'latest_event_id': recent[0].get('event_id') if recent else None, 'latest_published_at': recent[0].get('published_at') if recent else None})

    topic_signals.sort(key=lambda x: x['signal_strength'], reverse=True)
    entity_signals.sort(key=lambda x: x['momentum'], reverse=True)
    return {'version': 1, 'principle': '趋势来自时间上的重复、确认与加速度，而非单条新闻', 'topic_signals': topic_signals[:30], 'entity_momentum': entity_signals[:50]}
