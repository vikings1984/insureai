#!/usr/bin/env python3
"""Deterministic benchmark for Event / Claim / Evidence / Decision safety."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from claims import build_claims
from decision import build_decisions
from intelligence import build

ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "benchmarks" / "event_claim_evidence_decision.json"
OUTPUT = ROOT / "benchmark_results.json"

SOURCE_DOMAINS = {
    "Reuters": "reuters.com",
    "Insurance Journal": "insurancejournal.com",
}


def news(row: dict) -> dict:
    source = row["source"]
    domain = SOURCE_DOMAINS.get(source, "benchmark.invalid")
    return {
        "id": row["id"],
        "title": row["title"],
        "summary": row["title"],
        "tags": row.get("tags", ""),
        "source_name": source,
        "source_url": f"https://{domain}/benchmark/{row['id']}",
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
    expected_positive: set[tuple[str, str]] = set()
    different_pairs: set[tuple[str, str]] = set()
    for case in fixtures:
        for pair in case.get("same_event_pairs", []):
            expected_positive.add(tuple(sorted(pair)))
        for pair in case.get("different_event_pairs", []):
            different_pairs.add(tuple(sorted(pair)))
    # Evaluate each case in isolation: cross-case duplicated headlines must not
    # collide in a single build and pollute the merge metrics.
    actual: set[tuple[str, str]] = set()
    for case in fixtures:
        rows = [news(x) for x in case["articles"]]
        result = build({"news": rows})
        for event in result.get("events", []):
            ids = [str(x) for x in event.get("article_ids") or []]
            for i, left in enumerate(ids):
                for right in ids[i + 1:]:
                    actual.add(tuple(sorted((left, right))))
    return pair_metrics(actual, expected_positive, expected_positive | different_pairs)


def split_benchmark(fixtures: list[dict]) -> dict:
    """False Split 检测：同一事件的不同表述必须合并进同一事件。

    false_split_rate = 漏合并的应合并对 / 全部应合并对；守卫用例（同实体
    不同动作）的误合并计为 false_merge_rate，防止修复假拆分时矫枉过正。
    """
    expected_positive: set[tuple[str, str]] = set()
    different_pairs: set[tuple[str, str]] = set()
    for case in fixtures:
        for pair in case.get("same_event_pairs", []):
            expected_positive.add(tuple(sorted(pair)))
        for pair in case.get("different_event_pairs", []):
            different_pairs.add(tuple(sorted(pair)))
    actual: set[tuple[str, str]] = set()
    for case in fixtures:
        rows = [news(x) for x in case["articles"]]
        result = build({"news": rows})
        for event in result.get("events", []):
            ids = [str(x) for x in event.get("article_ids") or []]
            for i, left in enumerate(ids):
                for right in ids[i + 1:]:
                    actual.add(tuple(sorted((left, right))))
    metrics = pair_metrics(actual, expected_positive, expected_positive | different_pairs)
    metrics["false_split_rate"] = round(
        metrics["false_negative"] / len(expected_positive), 4
    ) if expected_positive else 0.0
    return metrics


def claim_benchmark(fixtures: list[dict]) -> dict:
    positive_case = next(x for x in fixtures if x["id"] == "claim_cross_checked_001")
    single_case = next(x for x in fixtures if x["id"] == "claim_single_source_001")
    positive = build_claims([news(x) for x in positive_case["articles"]], positive_case["event"])
    single = build_claims([news(x) for x in single_case["articles"]], single_case["event"])
    amount_positive = next(c for c in positive["claims"] if c.get("claim_type") == "transaction_amount")
    amount_single = next(c for c in single["claims"] if c.get("claim_type") == "transaction_amount")
    cross_checked_correct = amount_positive.get("verification_status") == positive_case["expected"]["numeric_status"]
    single_source_correct = amount_single.get("verification_status") == single_case["expected"]["numeric_status"]
    single_source_unsafe = amount_single.get("verification_status") == "cross_checked"
    proposition_ok = len([c for c in positive["claims"] if c.get("claim_type") != "event_summary"]) >= 3
    return {
        "cross_check_accuracy": 1.0 if cross_checked_correct else 0.0,
        "single_source_state_accuracy": 1.0 if single_source_correct else 0.0,
        "single_source_false_cross_check_rate": 1.0 if single_source_unsafe else 0.0,
        "proposition_extraction_accuracy": 1.0 if proposition_ok else 0.0,
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
        cases.append({"id": case["id"], "urgency": row.get("urgency"), "human_review_required": actual_review})
    forbidden_total = sum(1 for case in fixtures if case["expected"].get("forbid_urgency") == "now")
    return {
        "unsafe_now_rate": round(unsafe_now / forbidden_total, 4) if forbidden_total else 0.0,
        "human_review_recall": round(review_true_positive / review_expected, 4) if review_expected else 1.0,
        "cases": cases,
    }


def funnel_benchmark(artifact_path: Path | None = None) -> dict:
    """P0-B Decision Funnel precision 门（第四阶段「生产验证」）。

    直接校验生产产物 decisions_pending.json 的 decision_ready 契约：每个 decision_ready
    ceid 必须能在 funnel 中找到、meets_six=True、且 six_detail.single_src_regulatory=False
    （无单源监管/评级 bypass）。产物缺失则 graceful skip（available=False），不阻断流水线；
    出现假阳性则 precision<1.0，触发 safety 失败。
    """
    path = artifact_path or (ROOT / "decisions_pending.json")
    if not path.exists():
        return {"available": False, "decision_ready_precision": 1.0,
                "decision_ready_count": 0, "human_override_rate": "n/a", "false_positives": [],
                "note": "decisions_pending.json 未生成，跳过 precision 校验"}
    doc = json.loads(path.read_text(encoding="utf-8"))
    meta = doc.get("meta") or {}
    dr_ceids = set(meta.get("decision_ready_ceids") or [])
    funnel = doc.get("funnel") or {}
    items: dict[str, dict] = {}
    for tier in ("now", "soon", "watch"):
        for it in (funnel.get(tier) or []):
            items[it.get("canonical_event_id")] = it
    false_positives: list[dict] = []
    for ceid in dr_ceids:
        it = items.get(ceid)
        if it is None:
            false_positives.append({"canonical_event_id": ceid, "reason": "decision_ready 但不在 funnel 中"})
            continue
        detail = it.get("six_detail") or {}
        if not it.get("meets_six"):
            false_positives.append({"canonical_event_id": ceid, "reason": "meets_six=False"})
        elif detail.get("single_src_regulatory"):
            false_positives.append({"canonical_event_id": ceid, "reason": "单源监管/评级 bypass"})
    precision = 1.0 - (len(false_positives) / len(dr_ceids)) if dr_ceids else 1.0
    return {
        "available": True,
        "decision_ready_count": len(dr_ceids),
        "decision_ready_precision": round(precision, 4),
        # 真实业务精度层（P0-3，第五阶段）：由 decision_funnel 从 decision_ready_gold.json 回填；
        # seed 阶段仅作报告维度，不进 safety 门（避免用未确认的 seed 标注卡 CI）。
        "human_override_rate": meta.get("human_override_rate", "n/a"),
        "gold_precision": meta.get("gold_precision", "n/a"),
        "gold_labeled": meta.get("gold_labeled", 0),
        "gold_status": meta.get("gold_status", "absent"),
        "false_positives": false_positives,
    }


def main() -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    event = event_benchmark(data["event_cases"])
    split = split_benchmark(data.get("split_cases", []))
    claim = claim_benchmark(data["claim_cases"])
    decision = decision_benchmark(data["decision_cases"])
    funnel = funnel_benchmark()
    safety_pass = (
        decision["unsafe_now_rate"] == 0.0
        and claim["single_source_false_cross_check_rate"] == 0.0
        and event["false_merge_rate"] == 0.0
        and split["false_split_rate"] == 0.0
        and split["false_merge_rate"] == 0.0
        and (funnel.get("available") is False or funnel["decision_ready_precision"] == 1.0)
    )
    macro = round((event["precision"] + event["recall"] + (1 - event["false_merge_rate"]) + (1 - split["false_split_rate"]) + claim["cross_check_accuracy"] + claim["single_source_state_accuracy"] + (1 - claim["single_source_false_cross_check_rate"]) + (1 - decision["unsafe_now_rate"]) + decision["human_review_recall"]) / 9, 4)
    result = {"version": 2, "benchmark": "insureai_core_benchmark", "macro_quality": macro, "safety_pass": safety_pass, "event": event, "split": split, "claim_evidence": claim, "decision": decision, "funnel": funnel}
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # P0-6 Quality Registry：把本次 benchmark 结果固化为该 commit 的质量档案
    # （quality/<commit>.json + quality/index.json + quality/latest.json）。
    # 归档失败绝不影响 benchmark 本身的通过/失败判定，故全程 try/except。
    try:
        import quality_registry
        recorded = quality_registry.record(result)
        print(f"[quality] recorded commit {recorded} -> quality/{recorded}.json", file=sys.stderr)
    except Exception as e:
        print(f"[quality] 归档跳过（不影响 benchmark）: {e}", file=sys.stderr)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not safety_pass or macro < 0.95:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
