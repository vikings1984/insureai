#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Promote human review labels into the regression corpus."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LABELS = ROOT / "review_labels.json"
CORPUS = ROOT / "evaluation_cases.json"


def promote() -> int:
    labels = json.loads(LABELS.read_text(encoding="utf-8"))
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    cases = corpus.setdefault("cases", [])
    existing = {c.get("id") for c in cases}
    added = 0
    for review in labels.get("reviews", []):
        review_id = str(review.get("review_id") or "").strip()
        expected = review.get("expected") or {}
        if not review_id or not expected:
            continue
        case_id = f"human.{review_id}.v1"
        if case_id in existing:
            continue
        cases.append({
            "id": case_id,
            "type": expected.get("type", "human_review"),
            "source": "human_review",
            "label": review.get("label", "reviewed"),
            "notes": review.get("notes", ""),
            "expected": {k: v for k, v in expected.items() if k != "type"},
        })
        existing.add(case_id)
        added += 1
    if added:
        corpus["cases"] = cases
        CORPUS.write_text(json.dumps(corpus, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Promoted {added} human review cases")
    return added


if __name__ == "__main__":
    raise SystemExit(0 if LABELS.exists() and promote() >= 0 else 1)
