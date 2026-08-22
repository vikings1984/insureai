#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate the real release artifacts at the point of publication."""
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
    "freshness.json",
    "evidence_availability.json",
    "owner_risk_view.json",
)
DERIVED_ARTIFACTS = tuple(x for x in REQUIRED_ARTIFACTS if x != "data.json")
VALID_CREDIBILITY = {"ready", "review", "caution"}


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
    missing_ids = sum(1 for row in rows if not row.get("id"))
    ids = [str(row.get("id")) for row in rows if row.get("id")]
    duplicate_ids = len(ids) - len(set(ids))
    malformed_dates = sum(1 for row in rows if not row.get("published_at"))
    missing_urls = 0
    for row in rows:
        parsed = urlparse(str(row.get("source_url") or ""))
        if not (parsed.scheme in {"http", "https"} and parsed.netloc):
            missing_urls += 1
    passed = missing_ids == 0 and duplicate_ids == 0 and malformed_dates == 0 and missing_urls == 0
    return {
        "name": "news_integrity",
        "passed": passed,
        "detail": {
            "count": len(rows),
            "missing_ids": missing_ids,
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
    missing_event_ids = 0
    seen_event_ids = set()
    for event in events:
        event_id = str(event.get("event_id") or "")
        if not event_id:
            missing_event_ids += 1
        elif event_id in seen_event_ids:
            duplicate_event_ids += 1
        else:
            seen_event_ids.add(event_id)
        assigned.extend(str(x) for x in (event.get("article_ids") or []))

    assigned_set = set(assigned)
    expected_set = set(expected)
    duplicate_article_assignments = len(assigned) - len(assigned_set)
    missing_articles = sorted(expected_set - assigned_set)
    orphan_articles = sorted(assigned_set - expected_set)
    passed = (
        missing_event_ids == 0
        and duplicate_event_ids == 0
        and duplicate_article_assignments == 0
        and not missing_articles
        and not orphan_articles
    )
    return {
        "name": "lineage",
        "passed": passed,
        "detail": {
            "news_count": len(expected),
            "event_count": len(events),
            "missing_event_ids": missing_event_ids,
            "duplicate_event_ids": duplicate_event_ids,
            "duplicate_article_assignments": duplicate_article_assignments,
            "missing_articles": missing_articles[:20],
            "orphan_articles": orphan_articles[:20],
        },
    }


def _check_decisions(intelligence: dict) -> dict:
    rows = intelligence.get("decisions") if isinstance(intelligence, dict) else None
    events = intelligence.get("events") if isinstance(intelligence, dict) else None
    if not isinstance(rows, list) or not rows:
        return {"name": "decision_safety", "passed": False, "detail": "intelligence.json.decisions must be a non-empty list"}

    event_ids = {str(row.get("event_id")) for row in (events or []) if row.get("event_id")}
    missing_event_links = 0
    guardrail_missing = 0
    unsafe_now = 0
    duplicate_decision_ids = 0
    seen_decision_ids = set()
    for row in rows:
        event_id = str(row.get("event_id") or "")
        if not event_id or event_id not in event_ids:
            missing_event_links += 1
        if event_id in seen_decision_ids:
            duplicate_decision_ids += 1
        elif event_id:
            seen_decision_ids.add(event_id)
        if not row.get("guardrail"):
            guardrail_missing += 1
        basis = row.get("basis") or {}
        trust = basis.get("trust_level")
        conflict = bool(basis.get("conflict"))
        if row.get("urgency") == "now" and (trust in {"low", None} or conflict):
            unsafe_now += 1

    passed = missing_event_links == 0 and duplicate_decision_ids == 0 and guardrail_missing == 0 and unsafe_now == 0
    return {
        "name": "decision_safety",
        "passed": passed,
        "detail": {
            "decision_count": len(rows),
            "missing_event_links": missing_event_links,
            "duplicate_decision_ids": duplicate_decision_ids,
            "missing_guardrails": guardrail_missing,
            "unsafe_now": unsafe_now,
        },
    }


def _check_credibility(credibility: dict) -> dict:
    status = credibility.get("status") if isinstance(credibility, dict) else None
    reasons = credibility.get("reasons") if isinstance(credibility, dict) else None
    passed = status in VALID_CREDIBILITY and isinstance(reasons, list)
    return {
        "name": "credibility_contract",
        "passed": passed,
        "detail": {
            "status": status,
            "reason_count": len(reasons) if isinstance(reasons, list) else 0,
            "fail_closed": status not in VALID_CREDIBILITY,
        },
    }


def _check_freshness_binding(freshness: dict, availability: dict) -> dict:
    freshness_status = freshness.get("status") if isinstance(freshness, dict) else None
    freshness_stale = freshness.get("stale") is True if isinstance(freshness, dict) else False
    coverage = freshness.get("date_coverage") if isinstance(freshness, dict) else None
    availability_level = availability.get("level") if isinstance(availability, dict) else None
    availability_status = availability.get("freshness_status") if isinstance(availability, dict) else None
    availability_coverage = availability.get("date_coverage") if isinstance(availability, dict) else None

    allowed_by_freshness = "unavailable" if freshness_status == "unavailable" else "low" if freshness_stale or freshness_status == "undated" or (isinstance(coverage, (int, float)) and coverage < 0.5) else "medium" if isinstance(coverage, (int, float)) and coverage < 0.8 else "high"
    passed = (
        availability_level == allowed_by_freshness
        and availability_status == (freshness_status or "unknown")
        and availability_coverage == coverage
    )
    return {
        "name": "freshness_evidence_binding",
        "passed": passed,
        "detail": {
            "freshness_status": freshness_status,
            "freshness_stale": freshness_stale,
            "freshness_coverage": coverage,
            "availability_level": availability_level,
            "availability_status": availability_status,
            "availability_coverage": availability_coverage,
            "expected_availability_level": allowed_by_freshness,
        },
    }


def _check_versions(artifacts: dict) -> dict:
    missing = [name for name in DERIVED_ARTIFACTS if not isinstance(artifacts[name], dict) or not artifacts[name].get("version")]
    return {"name": "derived_artifact_versions", "passed": not missing, "detail": {"missing_versions": missing}}


def run_gate(root: Path = ROOT) -> dict:
    artifacts = {name: _load(root, name) for name in REQUIRED_ARTIFACTS}
    checks = [
        _check_news(artifacts["data.json"]),
        _check_lineage(artifacts["data.json"], artifacts["intelligence.json"]),
        _check_decisions(artifacts["intelligence.json"]),
        _check_credibility(artifacts["decision_credibility.json"]),
        _check_freshness_binding(artifacts["freshness.json"], artifacts["evidence_availability.json"]),
        _check_versions(artifacts),
    ]
    failed = [x for x in checks if not x["passed"]]
    return {
        "version": 1,
        "status": "passed" if not failed else "failed",
        "principle": "critical release invariants are non-compensatory and derived evidence quality must remain bound to its freshness source",
        "checks": checks,
        "failed_checks": [x["name"] for x in failed],
    }


def main() -> int:
    try:
        result = run_gate()
    except ValueError as exc:
        result = {"version": 1, "status": "failed", "principle": "critical release invariants are non-compensatory", "checks": [], "failed_checks": [str(exc)]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
