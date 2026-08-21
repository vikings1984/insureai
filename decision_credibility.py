#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Summarize decision credibility without recalculating or changing decisions."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def _load(name: str, default):
    path = ROOT / name
    if not path.exists():
        return default
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value
    except Exception:
        return default


def build_credibility() -> dict:
    release = _load("release_manifest.json", {})
    stability = _load("decision_stability.json", {})
    availability = _load("evidence_availability.json", {})
    metrics = _load("evaluation_metrics.json", {})

    stability_rows = stability.get("results") or []
    jitter = sum(1 for row in stability_rows if row.get("status") == "jitter")
    unstable = sum(1 for row in stability_rows if row.get("status") in {"jitter", "changed"})

    availability_rows = availability.get("results") or availability.get("items") or []
    low_availability = sum(1 for row in availability_rows if row.get("availability") in {"low", "unavailable"})

    quality_status = release.get("quality_status", "unknown")
    deployment_status = release.get("deployment_status", "unknown")
    macro_quality = metrics.get("macro_quality")

    if quality_status != "passed":
        status = "blocked"
    elif deployment_status not in {"verified", "pending"}:
        status = "caution"
    elif jitter > 0 or low_availability > 0:
        status = "review"
    elif macro_quality is not None and macro_quality < 0.95:
        status = "caution"
    else:
        status = "ready"

    return {
        "version": 1,
        "status": status,
        "principle": "可信度摘要只汇总已有质量信号，不重新评分，也不修改原始决策。",
        "quality": {
            "status": quality_status,
            "macro_quality": macro_quality,
        },
        "deployment": {
            "status": deployment_status,
            "verified": release.get("deployment_verified", False),
        },
        "stability": {
            "jitter_events": jitter,
            "unstable_events": unstable,
            "signal": "stable" if jitter == 0 else "review",
        },
        "evidence": {
            "low_or_unavailable": low_availability,
            "signal": "sufficient" if low_availability == 0 else "review",
        },
        "guardrail": "该摘要不替代承保、投资、合规或管理决策。",
    }


def main() -> None:
    output = build_credibility()
    (ROOT / "decision_credibility.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("Decision credibility:", output["status"])


if __name__ == "__main__":
    main()
