#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate the real release artifacts at the point of publication.

第一性原理：发布质量不是多个漂亮数字的平均值，而是端到端信息链路没有出现
不可接受的断裂。核心安全/溯源条件采用 non-compensatory gate：任何关键不变量失败，
整体即失败。

This gate reads the generated production artifacts rather than synthetic benchmark fixtures.
Synthetic regression metrics remain useful, but they must not be the only signal deciding whether
real output is safe to publish.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent

REQUIRED_ARTIFACTS = (
    "data.json",
    "intelligence.json",
    "decision_stability.json",
    "decision_credibility.json",
    "evidence_availability.json",
    "owner_risk_view.json",
)

VALID_CREDIBILITY = {"ready", "review", "caution", "blocked", "unknown"}


def _load(root: Path, name: str):
    path = root / name
    if not path.exists():
        raise ValueError(f"missing artifact: {name}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid json artifact: {name}: {exc}") from exc


def _check_news(data: dict) -> dict:
    rows = data.get("news") if isinstance(data, dict) else None
    if not isinstance(rows, list) or not rows:
        return {"name": "news_present", "passed": False, "detail": "data.json.news must be a non-empty list"}
    ids = [str(row.get("id")) for row in rows]
    duplicate_ids = len(ids) - len(set(ids))
    malformed_dates = 0
    missing_urls = 0
    for row in rows:
        if not row.get("published_at"):
            malformed_dates += 1
        parsed = urlparse(str(row.get("source_url") or ""))
        if not (parsed.scheme in {"http", "https"} and parsed.netloc):
            missing_urls += 1
    passed = duplicate_ids == 0 and malformed_dates == 0 and missing_urls == 0
    return {
        "name": "news_integrity",
        "passed": passed,
        "detail": {
            "count": len(rows),
            "duplicate_ids": duplicate_ids,
            "missing_or_invalid_dates": malformed_dates,
            "missing_or_invalid_urls": missing_urls,
        },
    }


def _check_lineage(data: dict, intelligence: dict) -> dict:
    news = data.get("news") if isinstance(data, dict) else []
    events = intelligence.get("events") if isinstance(intelligence, dict) else None
    if not isinstance(news, list) or not isinstance(events, list) or not events:
        return {"name": "lineage", "passed": False, "detail": "news and intelligence.events must be populated"}

    expected = [str(row.get("id")) for row in news if row.get("id") is not None]
    assigned = []
    duplicate_event_ids = 0
    seen_event_ids = set()
    for event in events:
        event_id = str(event.get("event_id") or "")
        if event_id in seen_event_ids:
            duplicate_event_ids += 1
        seen_event_ids.add(event_id)
        assigned.extend(str(x) for x in (event.get("article_ids") or []))

    assigned_set = set(assigned)
    expected_set = set(expected)
    duplicate_article_assignments = len(assigned) - len(assigned_set)
    missing_articles = sorted(expected_set - assigned_set)
    orphan_articles = sorted(assigned_set - expected_set)
    passed = duplicate_event_ids == 0 and duplicate_article_assignments == 0 and not missing_articles and not orphan_articles
    return {
        "name": "lineage",
        "passed": passed,
        "detail": {
            "news_count": len(expected),
            "event_count": len(events),
            "duplicate_event_ids": duplicate_event_ids,
            "duplicate_article_assignments": duplicate_article_assignments,
            "missing_articles": missing_articles[:20],
            "orphan_articles": orphan_articles[:20],
        },
    }


def _check_decisions(intelligence: dict) -> dict:
    rows = intelligence.get("decisions") if isinstance(intelligence, dict) else None
    if not isinstance(rows, list) or not rows:
        return {"name": "decision_safety", "passed": False, "detail": "intelligence.json.decisions must be a non-empty list"}

    guardrail_missing = 0
    unsafe_now = 0
    for row in rows:
        if not row.get("guardrail"):
            guardrail_missing += 1
        basis = row.get("basis") or {}
        trust = basis.get("trust_level")
        conflict = bool(basis.get("conflict"))
        if row.get("urgency") == "now" and (trust in {"low", None} or conflict):
            unsafe_now += 1

    passed = guardrail_missing == 0 and unsafe_now == 0
    return {
        "name": "decision_safety",
        "passed": passed,
        "detail": {
            "decision_count": len(rows),
            "missing_guardrails": guardrail_missing,
            "unsafe_now": unsafe_now,
        },
    }


def _check_credibility(credibility: dict) -> dict:
    status = credibility.get("status") if isinstance(credibility, dict) else None
    reasons = credibility.get("reasons") if isinstance(credibility, dict) else None
    passed = status in VALID_CREDIBILITY and isinstance(reasons, list)
    if status == "blocked" and not reasons:
        passed = False
    return {
        "name": "credibility_contract",
        "passed": passed,
        "detail": {"status": status, "reason_count": len(reasons) if isinstance(reasons, list) else 0},
    }


def _check_versions(artifacts: dict) -> dict:
    missing = [name for name, value in artifacts.items() if not isinstance(value, dict) or not value.get("version")]
    return {
        "name": "artifact_versions",
        "passed": not missing,
        "detail": {"missing_versions": missing},
    }


def run_gate(root: Path = ROOT) -> dict:
    artifacts = {name: _load(root, name) for name in REQUIRED_ARTIFACTS}
    checks = [
        _check_news(artifacts["data.json"]),
        _check_lineage(artifacts["data.json"], artifacts["intelligence.json"]),
        _check_decisions(artifacts["intelligence.json"]),
        _check_credibility(artifacts["decision_credibility.json"]),
        _check_versions(artifacts),
    ]
    failed = [x for x in checks if not x["passed"]]
    return {
        "version": 1,
        "status": "passed" if not failed else "failed",
        "principle": "critical release invariants are non-compensatory; one broken safety or lineage invariant blocks publication",
        "checks": checks,
        "failed_checks": [x["name"] for x in failed],
    }


def main() -> int:
    try:
        result = run_gate()
    except ValueError as exc:
        result = {
            "version": 1,
            "status": "failed",
            "principle": "critical release invariants are non-compensatory",
            "checks": [],
            "failed_checks": [str(exc)],
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
