#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bounded calibration from explicit human-review labels.

第一性原理：反馈只有在足够样本支持下才应改变系统；校准必须有上限、可审计、可回滚。
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LABELS = ROOT / "review_labels.json"
QUEUE = ROOT / "review_queue.json"
OUTPUT = ROOT / "calibration.json"
MIN_SAMPLES = 3
MAX_MULTIPLIER_SHIFT = 0.10


def _load(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def build_calibration(labels_data: dict | None = None, queue_data: dict | None = None) -> dict:
    labels_data = labels_data if labels_data is not None else _load(LABELS, {"reviews": []})
    queue_data = queue_data if queue_data is not None else _load(QUEUE, {"items": []})
    queue = {str(x.get("event_id")): x for x in queue_data.get("items", []) if x.get("event_id")}

    grouped = defaultdict(lambda: {"reviewed": 0, "false_positive": 0})
    for review in labels_data.get("reviews", []):
        rid = str(review.get("review_id") or "")
        expected = review.get("expected") or {}
        item = queue.get(rid, {})
        decision = item.get("decision") or {}
        event_type = str(expected.get("event_type") or item.get("event_type") or "general")
        if str(expected.get("type") or "") != "decision":
            continue
        predicted = str(decision.get("urgency") or "watch")
        expected_urgency = str(expected.get("urgency") or predicted)
        grouped[event_type]["reviewed"] += 1
        if predicted in {"now", "soon"} and expected_urgency == "watch":
            grouped[event_type]["false_positive"] += 1

    overrides = {}
    audit = []
    for event_type, stats in grouped.items():
        reviewed = stats["reviewed"]
        fp_rate = stats["false_positive"] / reviewed if reviewed else 0.0
        action = "none"
        cap = None
        if reviewed >= MIN_SAMPLES and fp_rate >= 0.75:
            cap = "watch"
            action = "cap_watch"
        elif reviewed >= MIN_SAMPLES and fp_rate >= 0.50:
            cap = "soon"
            action = "cap_soon"
        if cap:
            overrides[event_type] = {"max_urgency": cap, "sample_count": reviewed, "false_positive_rate": round(fp_rate, 4)}
        audit.append({"event_type": event_type, **stats, "false_positive_rate": round(fp_rate, 4), "action": action})

    return {
        "version": 1,
        "status": "active" if overrides else "neutral",
        "policy": {
            "min_samples": MIN_SAMPLES,
            "max_multiplier_shift": MAX_MULTIPLIER_SHIFT,
            "principle": "仅对有足够人工证据支持的决策类型做保守降级，不直接放大任何分数。",
        },
        "overrides": overrides,
        "audit": audit,
    }


def write_calibration() -> dict:
    result = build_calibration()
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(write_calibration(), ensure_ascii=False, indent=2))
