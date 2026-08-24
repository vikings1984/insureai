#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Attribute human-review feedback to the most likely intelligence layer."""
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path
from contract import ARTIFACT_VERSIONS

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "feedback_attribution.json"
LABELS = ROOT / "review_labels.json"
QUEUE = ROOT / "review_queue.json"

MODULES = ("event", "trust", "claims", "temporal", "decision", "counterfactual", "scenario")

KEYWORDS = {
    "event": {"event_cluster", "wrong_event", "entity", "cluster"},
    "trust": {"conflict", "trust", "source", "cross_check", "credibility"},
    "claims": {"evidence", "claim", "unsupported", "coverage", "fact"},
    "temporal": {"trend", "temporal", "momentum", "phase", "acceleration"},
    "decision": {"decision", "urgency", "action", "recommendation"},
    "counterfactual": {"counterfactual", "fragility", "sensitivity"},
    "scenario": {"scenario", "assumption", "robust_action"},
}


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _labels_case_map(doc: dict) -> list[dict]:
    cases = doc.get("labels") or doc.get("cases") or doc.get("items") or []
    return cases if isinstance(cases, list) else []


def _reason_types(case: dict) -> set[str]:
    values = set()
    for reason in case.get("reasons", []) or []:
        if isinstance(reason, dict):
            values.add(str(reason.get("type", "")).lower())
    for key in ("label", "error_type", "reason", "root_cause"):
        value = case.get(key)
        if value:
            values.add(str(value).lower())
    return values


def attribute_case(case: dict) -> dict:
    scores = Counter()
    for token in _reason_types(case):
        for module, vocabulary in KEYWORDS.items():
            if token in vocabulary or any(part in token for part in vocabulary):
                scores[module] += 1
    if not scores:
        return {"module": "unknown", "confidence": 0.0, "evidence": []}
    ranked = scores.most_common()
    top = ranked[0][1]
    second = ranked[1][1] if len(ranked) > 1 else 0
    confidence = round(min(1.0, 0.6 + 0.2 * max(0, top - second)), 2)
    return {"module": ranked[0][0], "confidence": confidence, "evidence": sorted(_reason_types(case))}


def build_attribution(labels: dict | None = None, queue: dict | None = None) -> dict:
    labels = labels or _load(LABELS)
    queue = queue or _load(QUEUE)
    cases = _labels_case_map(labels)
    queue_items = {str(x.get("event_id")): x for x in queue.get("items", []) if x.get("event_id")}
    rows = []
    module_counts = Counter()
    for case in cases:
        event_id = str(case.get("event_id") or "")
        attributed = attribute_case(case)
        if attributed["module"] == "unknown":
            q = queue_items.get(event_id)
            if q:
                synthetic = {"reasons": q.get("reasons", [])}
                attributed = attribute_case(synthetic)
        rows.append({"event_id": event_id, **attributed})
        module_counts[attributed["module"]] += 1
    total = len(rows)
    modules = {}
    for module in (*MODULES, "unknown"):
        count = module_counts.get(module, 0)
        modules[module] = {"error_count": count, "error_rate": round(count / total, 4) if total else 0.0}
    return {
        "version": ARTIFACT_VERSIONS["feedback_attribution.json"],
        "principle": "人工纠错首先归因，再决定是否调整规则；本层不直接改变线上评分",
        "reviewed_count": total,
        "cases": rows,
        "modules": modules,
    }


def main() -> None:
    result = build_attribution()
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Feedback attribution: {result['reviewed_count']} reviewed cases")


if __name__ == "__main__":
    main()
