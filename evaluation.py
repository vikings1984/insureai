#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic evaluation suite for the InsureAI intelligence pipeline.

第一性原理：优化系统必须先能测量，才能知道优化是否真的有效。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from claims import build_claims
from decision import build_decisions
from intelligence import build
from temporal import build_temporal_intelligence


@dataclass(frozen=True)
class EvalResult:
    name: str
    passed: bool
    detail: str


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


def _case_event_clustering() -> EvalResult:
    rows = [
        _news("Munich Re to acquire At-Bay for $575 million", "Reuters", "https://reuters.com/a", "2026-08-21T10:00:00+00:00"),
        _news("Munich Re agrees to buy At-Bay for $575 million", "Insurance Journal", "https://insurancejournal.com/a", "2026-08-21T11:00:00+00:00"),
        _news("Munich Re appoints new CFO", "Reuters", "https://reuters.com/b", "2026-08-21T12:00:00+00:00", tags="Munich Re", score=72, topic="digital_transformation"),
    ]
    result = build({"news": rows})
    sizes = sorted(e["article_count"] for e in result["events"])
    passed = sizes == [1, 2]
    return EvalResult("event_clustering", passed, f"event sizes={sizes}")


def _case_claims() -> EvalResult:
    rows = [
        _news("Munich Re to acquire At-Bay for $575 million", "Reuters", "https://reuters.com/a", "2026-08-21T10:00:00+00:00"),
        _news("Munich Re agrees to buy At-Bay for $575 million", "Insurance Journal", "https://insurancejournal.com/a", "2026-08-21T11:00:00+00:00"),
    ]
    event = {"event_id": "evt_eval", "title": "Munich Re 收购 At-Bay"}
    result = build_claims(rows, event)
    numeric = next(c for c in result["claims"] if c["type"] == "numeric")
    passed = result["coverage"] == 100 and numeric["status"] == "cross_checked"
    return EvalResult("claim_evidence", passed, f"coverage={result['coverage']} numeric={numeric['status']}")


def _case_temporal() -> EvalResult:
    def e(day, topic="ai_intelligent"):
        return {"event_id": day, "topic": topic, "published_at": f"2026-08-{day:02d}T10:00:00+00:00", "entities": ["example"], "source_count": 2, "event_type": "product", "trust": {"level": "high"}}
    rows = [e(10), e(17), e(18), e(19)]
    result = build_temporal_intelligence(rows)
    signal = next(x for x in result["topic_signals"] if x["topic"] == "ai_intelligent")
    passed = signal["phase"] == "accelerating" and signal["current_period_count"] == 3 and signal["previous_period_count"] == 1
    return EvalResult("temporal_signal", passed, f"phase={signal['phase']} current={signal['current_period_count']} previous={signal['previous_period_count']}")


def _case_decision_guardrail() -> EvalResult:
    events = [{
        "event_id": "evt_decision",
        "event_type": "regulatory",
        "topic": "regulatory_change",
        "scores": {"intelligence_score": 90},
        "trust": {"level": "high", "conflict": False},
    }]
    temporal = {"topic_signals": [{"topic": "regulatory_change", "phase": "accelerating", "signal_strength": 90}]}
    result = build_decisions(events, temporal, "executive")
    row = result[0]
    passed = row["urgency"] == "now" and bool(row["guardrail"])
    return EvalResult("decision_guardrail", passed, f"urgency={row['urgency']}")


def run_evaluation() -> list[EvalResult]:
    cases: list[Callable[[], EvalResult]] = [_case_event_clustering, _case_claims, _case_temporal, _case_decision_guardrail]
    return [case() for case in cases]


def summary(results: list[EvalResult]) -> dict:
    passed = sum(r.passed for r in results)
    total = len(results)
    return {"passed": passed, "total": total, "pass_rate": round(passed / total, 3) if total else 0, "results": [r.__dict__ for r in results]}


if __name__ == "__main__":
    import json
    result = summary(run_evaluation())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["passed"] == result["total"] else 1)
