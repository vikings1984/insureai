#!/usr/bin/env python3
"""Deterministic benchmark for Event / Claim / Evidence / Decision safety."""
from __future__ import annotations

import json
from pathlib import Path

from claims import build_claims
from decision import build_decisions
from intelligence import build

ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "benchmarks" / "event_claim_evidence_decision.json"
OUTPUT = ROOT / "benchmark_results.json"


def news(row: dict) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "summary": row["title"],
        "tags": row.get("tags", ""),
        "source_name": row["source"],
        "source_url": f"https://benchmark.invalid/{row['id']}",
        "published_at": row.get("published_at", "2026-08-21T10:00:00+00:00"),
        "date_verified": True,
        "source_authority": 90,
        "ai_score": 88,
        "research_topic": row.get("topic", "capital_reinsurance"),
    }


def pair_metrics(actual: set[tuple[str, str]], expected_positive: set[tuple[str, str]], all_pairs: set[tuple[str, str]]) -> dict:
    tp = len(actual & expected_positive)
    fp = len(actual - expected_positive)
    fn = len(expected_positive - actual)
    tn = len(all_pairs - actual - expected_positive)
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    false_merge_rate = fp / (fp + tn) if fp + tn else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4), "false_merge_rate": round(false_merge_rate, 4), "true_positive": tp, "false_positive": fp, "false_negative": fn}


def event_benchmark(fixtures: list[dict]) -> dict:
    rows = []
    expected_positive: set[tuple[str, str]] = set()
    different_pairs: set[tuple[str, str]] = set()
    for case in fixtures:
        rows.extend(news(x) for x in case["articles"])
        for pair in case.get("same_event_pairs", []):
            expected_positive.add(tuple(sorted(pair)))
        for pair in case.get("different_event_pairs", []):
            different_pairs.add(tuple(sorted(pair)))
    result = build({"news": rows})
    actual: set[tuple[str, str]] = set()
    for event in result.get("events", []):
        ids = [str(x) for x in event.get("article_ids") or []]
        for i, left in enumerate(ids):
            for right in ids[i + 1:]:
                actual.add(tuple(sorted((left, right))))
    return pair_metrics(actual, expected_positive, expected_positive | different_pairs)


def claim_benchmark(fixtures: list[dict]) -> dict:
    positive_case = next(x for x in fixtures if x["id"] == "claim_cross_checked_001")
    single_case = next(x for x in fixtures if x["id"] == "claim_single_source_001")
    positive = build_claims([news(x) for x in positive_case["articles"]], positive_case["event"])
    single = build_claims([news(x) for x in single_case["articles"]], single_case["event"])
    numeric_positive = next(c for c in positive["claims"] if c.get("type") == "numeric")
    numeric_single = next(c for c in single["claims"] if c.get("type") == "numeric")
    cross_checked_correct = numeric_positive.get("status") == positive_case["expected"]["numeric_status"]
    single_source_correct = numeric_single.get("status") == single_case["expected"]["numeric_status"]
    single_source_unsafe = numeric_single.get("status") == "cross_checked"
    return {
        "cross_check_accuracy": 1.0 if cross_checked_correct else 0.0,
        "single_source_state_accuracy": 1.0 if single_source_correct else 0.0,
        "single_source_false_cross_check_rate": 1.0 if single_source_unsafe else 0.0,
        "multi_source_coverage": round(float(positive.get("coverage", 0)) / 100, 4),
    }


def decision_benchmark(fixtures: list[dict]) -> dict:
    cases = []
    unsafe_now = 0
    review_true_positive = 0
    review_expected = 0
    for case in fixtures:
        row = build_decisions([case["event"]], case["temporal"], "executive")[0]
        forbidden_now = case["expected"].get("forbid_urgency") == "now"
        is_now = row.get("urgency") == "now"
        unsafe_now += int(forbidden_now and is_now)
        expected_review = case["expected"].get("require_human_review") is True
        actual_review = bool(row.get("human_review_required"))
        review_expected += int(expected_review)
        review_true_positive += int(expected_review and actual_review)
        cases.append({
            "id": case["id"],
            "urgency": row.get("urgency"),
            "human_review_required": actual_review,
        })
    forbidden_total = sum(1 for case in fixtures if case["expected"].get("forbid_urgency") == "now")
    return {
        "unsafe_now_rate": round(unsafe_now / forbidden_total, 4) if forbidden_total else 0.0,
        "human_review_recall": round(review_true_positive / review_expected, 4) if review_expected else 1.0,
        "cases": cases,
    }


def main() -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    event = event_benchmark(data["event_cases"])
    claim = claim_benchmark(data["claim_cases"])
    decision = decision_benchmark(data["decision_cases"])
    safety_pass = (
        decision["unsafe_now_rate"] == 0.0
        and claim["single_source_false_cross_check_rate"] == 0.0
        and event["false_merge_rate"] == 0.0
    )
    macro = round((event["precision"] + event["recall"] + (1 - event["false_merge_rate"]) + claim["cross_check_accuracy"] + claim["single_source_state_accuracy"] + (1 - claim["single_source_false_cross_check_rate"]) + (1 - decision["unsafe_now_rate"]) + decision["human_review_recall"]) / 8, 4)
    result = {"version": 1, "benchmark": "insureai_core_benchmark", "macro_quality": macro, "safety_pass": safety_pass, "event": event, "claim_evidence": claim, "decision": decision}
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not safety_pass or macro < 0.95:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
