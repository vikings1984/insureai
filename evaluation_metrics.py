#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Quantitative quality metrics for the deterministic InsureAI benchmark.

第一性原理：pass_rate 只回答“测试是否通过”；质量指标回答“错在哪里、错多少”。
"""
from __future__ import annotations

from claims import build_claims
from decision import build_decisions
from intelligence import build
from temporal import build_temporal_intelligence


def _news(title, source, url, published_at, tags="Munich Re,At-Bay", score=88, topic="capital_reinsurance"):
    return {
        "id": f"{source}-{published_at}",
        "title": title,
        "summary": title,
        "tags": tags,
        "source_name": source,
        "source_url": url,
        "published_at": published_at,
        "date_verified": True,
        "source_authority": 90,
        "ai_score": score,
        "research_topic": topic,
    }


def _pair_set(events: list[dict]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for event in events:
        ids = [str(x) for x in event.get("article_ids") or []]
        for i, left in enumerate(ids):
            for right in ids[i + 1:]:
                pairs.add(tuple(sorted((left, right))))
    return pairs


def _safe_div(num: float, den: float) -> float:
    return round(num / den, 4) if den else 1.0


def event_pair_metrics() -> dict:
    rows = [
        _news("Munich Re to acquire At-Bay for $575 million", "Reuters", "https://reuters.com/a", "2026-08-21T10:00:00+00:00"),
        _news("Munich Re agrees to buy At-Bay for $575 million", "Insurance Journal", "https://insurancejournal.com/a", "2026-08-21T11:00:00+00:00"),
        _news("Munich Re appoints new CFO", "Reuters", "https://reuters.com/b", "2026-08-21T12:00:00+00:00", tags="Munich Re", score=72, topic="digital_transformation"),
    ]
    result = build({"news": rows})
    actual = _pair_set(result["events"])
    ids = [str(x["id"]) for x in rows]
    expected = {tuple(sorted((ids[0], ids[1])))}
    candidate_pairs = {tuple(sorted((ids[i], ids[j]))) for i in range(len(ids)) for j in range(i + 1, len(ids))}
    tp = len(actual & expected)
    fp = len(actual - expected)
    fn = len(expected - actual)
    tn = len(candidate_pairs - actual - expected)
    return {
        "precision": _safe_div(tp, tp + fp),
        "recall": _safe_div(tp, tp + fn),
        "false_merge_rate": _safe_div(fp, fp + tn),
        "true_pairs": len(expected),
        "predicted_pairs": len(actual),
    }


def claim_metrics() -> dict:
    multi = [
        _news("Munich Re to acquire At-Bay for $575 million", "Reuters", "https://reuters.com/a", "2026-08-21T10:00:00+00:00"),
        _news("Munich Re agrees to buy At-Bay for $575 million", "Insurance Journal", "https://insurancejournal.com/a", "2026-08-21T11:00:00+00:00"),
    ]
    single = multi[:1]
    positive = build_claims(multi, {"title": "Munich Re 收购 At-Bay"})
    negative = build_claims(single, {"title": "Munich Re 收购 At-Bay"})
    numeric = next(c for c in positive["claims"] if c["type"] == "numeric")
    predicted_positive = [numeric["status"] == "cross_checked"]
    actual_positive = [True]
    single_cross_checked = any(c["status"] == "cross_checked" for c in negative["claims"])
    tp = int(predicted_positive[0] and actual_positive[0])
    fp = int(any(predicted_positive) and not any(actual_positive))
    return {
        "cross_check_precision": _safe_div(tp, tp + fp),
        "cross_check_recall": _safe_div(tp, 1),
        "single_source_false_cross_check_rate": 1.0 if single_cross_checked else 0.0,
        "multi_source_coverage": positive["coverage"] / 100,
    }


def temporal_metrics() -> dict:
    undated = [{"event_id": "x", "topic": "ai_intelligent", "published_at": "", "entities": ["example"]}]
    no_date = build_temporal_intelligence(undated)

    def e(day):
        return {"event_id": day, "topic": "ai_intelligent", "published_at": f"2026-08-{day:02d}T10:00:00+00:00", "entities": ["example"], "source_count": 2, "event_type": "product", "trust": {"level": "high"}}

    accelerating = build_temporal_intelligence([e(10), e(17), e(18), e(19)])
    signal = next(x for x in accelerating["topic_signals"] if x["topic"] == "ai_intelligent")
    return {
        "false_trend_rate_no_date": 0.0 if not no_date["topic_signals"] else 1.0,
        "accelerating_recall": 1.0 if signal["phase"] == "accelerating" else 0.0,
        "signal_strength": signal["signal_strength"],
    }


def decision_metrics() -> dict:
    events = [
        {"event_id": "safe", "event_type": "regulatory", "topic": "regulatory_change", "scores": {"intelligence_score": 90}, "trust": {"level": "high", "conflict": False}},
        {"event_id": "unsafe", "event_type": "regulatory", "topic": "regulatory_change", "scores": {"intelligence_score": 90}, "trust": {"level": "medium", "conflict": True}},
    ]
    temporal = {"topic_signals": [{"topic": "regulatory_change", "phase": "accelerating", "signal_strength": 90}]}
    rows = build_decisions(events, temporal, "executive")
    unsafe = [r for r in rows if r["urgency"] == "now" and (r["basis"]["trust_level"] != "high" or r["event_id"] == "unsafe")]
    return {
        "unsafe_now_rate": _safe_div(len(unsafe), len(rows)),
        "guardrail_coverage": _safe_div(sum(1 for r in rows if r.get("guardrail")), len(rows)),
    }


def build_metrics() -> dict:
    event = event_pair_metrics()
    claim = claim_metrics()
    temporal = temporal_metrics()
    decision = decision_metrics()
    macro = round(sum([
        event["precision"],
        event["recall"],
        1 - event["false_merge_rate"],
        claim["cross_check_precision"],
        claim["cross_check_recall"],
        1 - claim["single_source_false_cross_check_rate"],
        temporal["accelerating_recall"],
        1 - temporal["false_trend_rate_no_date"],
        1 - decision["unsafe_now_rate"],
        decision["guardrail_coverage"],
    ]) / 10, 4)
    return {
        "version": 1,
        "event_clustering": event,
        "claim_evidence": claim,
        "temporal": temporal,
        "decision": decision,
        "macro_quality": macro,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(build_metrics(), ensure_ascii=False, indent=2))
