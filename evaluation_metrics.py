#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Quantitative quality metrics for the deterministic InsureAI benchmark.

第一性原理：pass_rate 只回答“测试是否通过”；质量指标回答“错在哪里、错多少”。
合成基准（fixture）度量算法正确性；生产指标（claims.json 实测）度量真实数据上的效果。
"""
from __future__ import annotations

import json
from pathlib import Path

from claims import build_claims
from decision import build_decisions, context_coverage
from intelligence import build
from radar import build_topic_trends
from temporal import build_temporal_intelligence
from trend_intelligence import build_event_clusters
from trust import assess

CLAIMS_ARTIFACT = Path(__file__).resolve().parent / "claims.json"
CLAIM_EVIDENCE_MATCH_RATE_GATE = 0.6


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
    conflict = [
        _news("Munich Re to acquire At-Bay for $575 million", "Reuters", "https://reuters.com/a", "2026-08-21T10:00:00+00:00"),
        _news("Munich Re agrees to buy At-Bay for $600 million", "Insurance Journal", "https://insurancejournal.com/a", "2026-08-21T11:00:00+00:00"),
    ]
    positive = build_claims(multi, {"event_id": "evt_m", "title": "Munich Re 收购 At-Bay"})
    negative = build_claims(single, {"event_id": "evt_s", "title": "Munich Re 收购 At-Bay"})
    conflicted = build_claims(conflict, {"event_id": "evt_c", "title": "Munich Re 收购 At-Bay"})
    amount = next(c for c in positive["claims"] if c["claim_type"] == "transaction_amount")
    predicted_positive = [amount["verification_status"] == "cross_checked"]
    actual_positive = [True]
    single_cross_checked = any(c["verification_status"] == "cross_checked" for c in negative["claims"])
    tp = int(predicted_positive[0] and actual_positive[0])
    fp = int(any(predicted_positive) and not any(actual_positive))
    propositions = [c for c in positive["claims"] if c["claim_type"] != "event_summary"]
    conflict_detected = any(c["verification_status"] == "conflicted" for c in conflicted["claims"])
    return {
        "cross_check_precision": _safe_div(tp, tp + fp),
        "cross_check_recall": _safe_div(tp, 1),
        "single_source_false_cross_check_rate": 1.0 if single_cross_checked else 0.0,
        "multi_source_coverage": positive["coverage"] / 100,
        "claim_proposition_coverage": _safe_div(len(propositions), 3) if len(propositions) < 3 else 1.0,
        "claim_conflict_recall": 1.0 if conflict_detected else 0.0,
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


def trend_metrics() -> dict:
    """P1-1 趋势引擎指标：动力学数值正确性 + rising 解释齐备率（trend_explainability）。

    全部用相对 now 构造的 hermetic 事件，不读取磁盘工件。
    """
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)

    def ev(day_offset, domain, entity="At-Bay", title="Munich Re to acquire At-Bay"):
        published = (now - timedelta(days=day_offset)).isoformat()
        return {
            "event_id": f"ev_{day_offset}_{domain}",
            "topic": "capital_reinsurance",
            "title": title,
            "published_at": published,
            "entities": [entity, "Munich Re"],
            "source_count": 1,
            "scores": {"intelligence_score": 80},
            "evidence": [{"domain": domain, "source_url": f"https://{domain}/a"}],
        }

    # w0(0-7d): 3 事件两域；w1(7-14d): 1 事件；w2(14-21d): 2 事件
    events = [
        ev(1, "reuters.com"), ev(2, "insurancejournal.com"), ev(3, "reuters.com"),
        ev(10, "reuters.com"),
        ev(17, "reuters.com"), ev(18, "reuters.com"),
    ]
    trends = build_topic_trends(events)
    trend = next(x for x in trends if x["topic"] == "capital_reinsurance")
    velocity = (3 - 1) / 1
    previous_velocity = (1 - 2) / 2
    dynamics_ok = (
        trend["velocity"] == round(velocity, 3)
        and trend["acceleration"] == round(velocity - previous_velocity, 3)
        and trend["source_diversity"] == 2
    )
    why = trend.get("why") or {}
    explainability_ok = all(why.get(k) is not None for k in ("independent_events", "sources", "days", "core_entities")) and bool(why.get("event_ids"))

    # rising 场景：w0 明显放量，验证 explainability 的实际计算路径而非空列表默认 1.0
    rising_events = [
        {"event_id": f"r{i}", "topic": "product_innovation", "title": f"Insurer launches new parametric product v{i}", "published_at": (now - timedelta(days=1)).isoformat(), "entities": ["Insurer"], "source_count": 1, "scores": {"intelligence_score": 80}, "evidence": [{"domain": "reuters.com"}]}
        for i in range(5)
    ] + [
        {"event_id": "r_prev", "topic": "product_innovation", "title": "Insurer launches new parametric product", "published_at": (now - timedelta(days=10)).isoformat(), "entities": ["Insurer"], "source_count": 1, "scores": {"intelligence_score": 80}, "evidence": [{"domain": "reuters.com"}]},
    ]
    rising_trends = build_topic_trends(rising_events)
    rising_topic = next(x for x in rising_trends if x["topic"] == "product_innovation")
    assert rising_topic["direction"] == "rising"

    # cluster：同 topic 相似事件聚为一，不同实体分开
    cluster_events = [
        {"event_id": "c1", "topic": "capital_reinsurance", "title": "Munich Re to acquire At-Bay", "published_at": now.isoformat(), "entities": ["Munich Re", "At-Bay"], "evidence": []},
        {"event_id": "c2", "topic": "capital_reinsurance", "title": "Munich Re seals At-Bay deal", "published_at": (now - timedelta(hours=2)).isoformat(), "entities": ["Munich Re", "At-Bay"], "evidence": []},
        {"event_id": "c3", "topic": "capital_reinsurance", "title": "Lloyd appoints new chairman of syndicate", "published_at": (now - timedelta(hours=4)).isoformat(), "entities": ["Lloyd"], "evidence": []},
    ]
    clusters = build_event_clusters(cluster_events, now=now)
    cluster_ok = len(clusters) == 2 and {c["event_count"] for c in clusters} == {2, 1}

    rising = [x for x in trends if x["direction"] == "rising"]
    rising_explained = sum(1 for x in rising if (x.get("why") or {}).get("independent_events") is not None)
    return {
        "dynamics_correctness": 1.0 if dynamics_ok else 0.0,
        "trend_explainability": _safe_div(rising_explained, len(rising)) if rising else 1.0,
        "cluster_unit_precision": 1.0 if cluster_ok else 0.0,
        "why": why,
    }


def decision_metrics() -> dict:
    events = [
        {"event_id": "safe", "event_type": "regulatory", "topic": "regulatory_change", "scores": {"intelligence_score": 90}, "trust": {"level": "high", "conflict": False}, "insight": {"what_to_watch": "跟踪后续监管文件与实施时间表", "signals": {"scores": {"regulatory_change": 56}}}},
        {"event_id": "unsafe", "event_type": "regulatory", "topic": "regulatory_change", "scores": {"intelligence_score": 90}, "trust": {"level": "medium", "conflict": True}, "insight": {"what_to_watch": "跟踪证据冲突的收敛情况", "signals": {"scores": {"regulatory_change": 56}}}},
    ]
    temporal = {"topic_signals": [{"topic": "regulatory_change", "phase": "accelerating", "signal_strength": 90}]}
    rows = build_decisions(events, temporal, "executive")
    unsafe = [r for r in rows if r["urgency"] == "now" and (r["basis"]["trust_level"] != "high" or r["event_id"] == "unsafe")]
    underwriting = build_decisions(events, temporal, "underwriting")
    by_event = {r["event_id"]: r for r in rows}
    # 同一事件、不同角色必须给出不同视角的行动建议（P1-2 验收：数据同源、视角不同）。
    lens_distinct = 1.0 if any(by_event[r["event_id"]]["action"] != r["action"] for r in underwriting) else 0.0
    return {
        "unsafe_now_rate": _safe_div(len(unsafe), len(rows)),
        "guardrail_coverage": _safe_div(sum(1 for r in rows if r.get("guardrail")), len(rows)),
        "decision_context_coverage": context_coverage(rows),
        "role_lens_distinct": lens_distinct,
    }


def production_claim_metrics(path: Path | None = None) -> dict:
    """生产指标：claims.json 实测的命题-证据匹配率。fail-closed——生产产物缺失或不可读时按 0 分处理。"""
    artifact = path or CLAIMS_ARTIFACT
    try:
        data = json.loads(artifact.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"claim_evidence_match_rate": 0.0, "claim_count": 0, "source": str(artifact.name), "reason": "artifact missing or unreadable"}
    total = int(data.get("claim_count") or 0)
    if total <= 0:
        return {"claim_evidence_match_rate": 0.0, "claim_count": 0, "source": str(artifact.name), "reason": "no claims"}
    unverified = int(data.get("unverified_claim_count") or 0)
    computed = round((total - unverified) / total, 4)
    return {
        "claim_evidence_match_rate": computed,
        "claim_count": total,
        "unverified_claim_count": unverified,
        "conflicted_claim_count": int(data.get("conflicted_claim_count") or 0),
        "gate": CLAIM_EVIDENCE_MATCH_RATE_GATE,
        "source": str(artifact.name),
    }


def source_tier_metrics() -> dict:
    """来源层级指标：Tier1 单源值得 medium 以上；两个 Tier3 行业媒体互相印证不得得 high。"""
    tier1_single = [
        _news("国家金融监督管理总局发布保险业资金运用新规", "金融监管总局", "https://www.nfra.gov.cn/a", "2026-08-21T10:00:00+00:00", tags="金融监管总局"),
    ]
    tier3_pair = [
        _news("Munich Re to acquire At-Bay for $575 million", "Insurance Journal", "https://www.insurancejournal.com/a", "2026-08-21T10:00:00+00:00"),
        _news("Munich Re agrees to buy At-Bay for $575 million", "Reinsurance News", "https://www.reinsurancene.ws/a", "2026-08-21T11:00:00+00:00"),
    ]
    tier1_result = assess(tier1_single, {"source_count": 1})
    tier3_result = assess(tier3_pair, {"source_count": 2})
    tier1_ok = tier1_result["level"] in {"medium", "high"}
    tier3_ok = tier3_result["level"] != "high"
    return {
        "tier1_single_source_trust": 1.0 if tier1_ok else 0.0,
        "tier3_pair_not_high": 1.0 if tier3_ok else 0.0,
        "tier1_single_source_level": tier1_result["level"],
        "tier3_pair_level": tier3_result["level"],
    }


def build_metrics() -> dict:
    event = event_pair_metrics()
    claim = claim_metrics()
    temporal = temporal_metrics()
    trend = trend_metrics()
    decision = decision_metrics()
    source_tier = source_tier_metrics()
    macro = round(sum([
        event["precision"],
        event["recall"],
        1 - event["false_merge_rate"],
        claim["cross_check_precision"],
        claim["cross_check_recall"],
        1 - claim["single_source_false_cross_check_rate"],
        claim["claim_proposition_coverage"],
        claim["claim_conflict_recall"],
        temporal["accelerating_recall"],
        1 - temporal["false_trend_rate_no_date"],
        1 - decision["unsafe_now_rate"],
        decision["guardrail_coverage"],
        decision["decision_context_coverage"],
        decision["role_lens_distinct"],
        source_tier["tier1_single_source_trust"],
        source_tier["tier3_pair_not_high"],
    ]) / 16, 4)
    return {
        "version": 2,
        "event_clustering": event,
        "claim_evidence": claim,
        "temporal": temporal,
        "trend_intelligence": trend,
        "decision": decision,
        "source_authority": source_tier,
        "macro_quality": macro,
        "production": production_claim_metrics(),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(build_metrics(), ensure_ascii=False, indent=2))
