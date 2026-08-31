#!/usr/bin/env python3
"""P1-4 real-data annotation benchmark.

This benchmark is intentionally separate from the synthetic core benchmark.
It evaluates the current deterministic engine against a small, hand-labeled
corpus of real public insurance-industry articles. The corpus stores metadata
and provenance URLs, not article bodies.

Gate philosophy:
- real-data quality is reported separately from the synthetic v1.0 gate;
- no production artifact is used as expected truth;
- a single source may never become cross_checked;
- explicit different-event pairs must never be merged;
- expected same-event pairs must not be split.

v1.0 (default) is frozen. Pass --articles/--gold/--out to run the P1-4.1
expansion (benchmarks/real_v2).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from claims import build_claims
from intelligence import build

ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / "benchmarks" / "real_v1" / "articles.json"
GOLD = ROOT / "benchmarks" / "real_v1" / "gold.json"
OUTPUT = ROOT / "real_benchmark_results.json"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _rows(articles: list[dict]) -> list[dict]:
    return [
        {
            **row,
            "summary": row.get("summary") or row["title"],
            "date_verified": True,
            "source_authority": 90,
            "ai_score": 88,
        }
        for row in articles
    ]


def _pairs(events: list[dict]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for event in events:
        ids = [str(x) for x in event.get("article_ids") or []]
        for i, left in enumerate(ids):
            for right in ids[i + 1:]:
                pairs.add(tuple(sorted((left, right))))
    return pairs


def _metrics(actual: set[tuple[str, str]], positive: set[tuple[str, str]], negative: set[tuple[str, str]]) -> dict:
    labeled = positive | negative
    predicted = actual & labeled
    tp = len(predicted & positive)
    fp = len(predicted & negative)
    fn = len(positive - predicted)
    tn = len(negative - predicted)
    return {
        "precision": round(tp / (tp + fp), 4) if tp + fp else 1.0,
        "recall": round(tp / (tp + fn), 4) if tp + fn else 1.0,
        "false_merge_rate": round(fp / (fp + tn), 4) if fp + tn else 0.0,
        "false_split_rate": round(fn / len(positive), 4) if positive else 0.0,
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "true_negative": tn,
    }


def event_metrics(articles: list[dict], gold: dict) -> dict:
    result = build({"news": _rows(articles)})
    actual = _pairs(result.get("events", []))
    positive = {tuple(sorted(x)) for x in gold["same_event_pairs"]}
    negative = {tuple(sorted(x)) for x in gold["different_event_pairs"]}
    metrics = _metrics(actual, positive, negative)
    metrics["article_count"] = len(articles)
    metrics["event_count"] = len(result.get("events", []))
    metrics["annotated_positive_pairs"] = len(positive)
    metrics["annotated_negative_pairs"] = len(negative)
    return metrics


def claim_metrics(articles_by_id: dict[str, dict], gold: dict) -> dict:
    rows = []
    for case in gold["claim_cases"]:
        articles = [articles_by_id[x] for x in case["article_ids"]]
        result = build_claims(_rows(articles), {"event_id": case["id"], "title": case["event_title"]})
        expected = case["expected"]
        matched = [
            c for c in result.get("claims", [])
            if c.get("claim_type") == expected["claim_type"]
        ]
        if not matched:
            rows.append({"id": case["id"], "pass": False, "reason": "expected claim type not extracted"})
            continue
        claim = matched[0]
        value = claim.get("value") or {}
        value_ok = expected.get("normalized_value") is None or value.get("normalized") == expected["normalized_value"]
        status_ok = claim.get("verification_status") == expected["verification_status"]
        rows.append({
            "id": case["id"],
            "pass": bool(value_ok and status_ok),
            "verification_status": claim.get("verification_status"),
            "expected_status": expected["verification_status"],
            "normalized_value": value.get("normalized"),
            "expected_value": expected.get("normalized_value"),
        })
    passed = sum(1 for x in rows if x["pass"])
    single_source = [x for x in rows if x["id"] == "real_claim_atbay_single_source"]
    false_cross_check = 1.0 if single_source and single_source[0].get("verification_status") == "cross_checked" else 0.0
    return {
        "case_count": len(rows),
        "passed": passed,
        "accuracy": round(passed / len(rows), 4) if rows else 0.0,
        "single_source_false_cross_check_rate": false_cross_check,
        "cases": rows,
    }


def run_benchmark(articles_path: Path, gold_path: Path, out_path: Path) -> dict:
    """Run the real-data annotation benchmark against a given corpus+gold.

    v1.0 (default) is frozen; pass real_v2 paths for the P1-4.1 expansion.
    """
    articles_path = articles_path.resolve()
    gold_path = gold_path.resolve()
    out_path = out_path.resolve()
    articles = _load(articles_path)
    gold = _load(gold_path)
    articles_by_id = {x["id"]: x for x in articles}
    event = event_metrics(articles, gold)
    claim = claim_metrics(articles_by_id, gold)
    # Component-aware macro: real-data expansions may carry zero claim cases
    # (claim truth requires human labeling), so exclude claim accuracy from the
    # average rather than letting it pull macro to ~0.67 on event-only quality.
    # Curated v2 has claim cases -> all 6 components, identical to before.
    components = [
        event["precision"],
        event["recall"],
        1 - event["false_merge_rate"],
        1 - event["false_split_rate"],
        1 - claim["single_source_false_cross_check_rate"],
    ]
    if claim["case_count"] > 0:
        components.append(claim["accuracy"])
    macro = round(sum(components) / len(components), 4)
    is_v2 = "v2" in str(gold_path)
    result = {
        "version": gold["version"],
        "benchmark": "insureai_real_data_annotation_v2" if is_v2 else "insureai_real_data_annotation_v1",
        "macro_quality": macro,
        "event": event,
        "claim_evidence": claim,
        "dimension_coverage": gold.get("dimension_coverage", {}),
        "provenance": {
            "corpus": str(articles_path.relative_to(ROOT)),
            "gold": str(gold_path.relative_to(ROOT)),
            "production_data_used": False,
            "article_bodies_stored": False,
        },
    }
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="InsureAI P1-4 real-data annotation benchmark")
    parser.add_argument("--articles", default=str(CORPUS), help="corpus articles.json (default: real_v1)")
    parser.add_argument("--gold", default=str(GOLD), help="gold annotations json (default: real_v1)")
    parser.add_argument("--out", default=str(OUTPUT), help="output results json (default: real_benchmark_results.json)")
    args = parser.parse_args()
    result = run_benchmark(Path(args.articles), Path(args.gold), Path(args.out))
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # P1-4 is a baseline quality report, not yet the production v1.0 gate.
    # Fail only on hard safety regressions; quality target is reported explicitly.
    if result["event"]["false_merge_rate"] != 0.0 or result["event"]["false_split_rate"] != 0.0 or result["claim_evidence"]["single_source_false_cross_check_rate"] != 0.0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
