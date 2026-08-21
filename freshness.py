#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Measure input-data freshness and temporal coverage without changing live decisions."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data.json"
OUTPUT = ROOT / "freshness.json"
DATE_FIELDS = ("published_at", "published", "pubDate", "date", "timestamp", "created_at", "updated_at")


def _load(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _rows(doc: Any) -> list[dict]:
    if isinstance(doc, list):
        return [x for x in doc if isinstance(x, dict)]
    if isinstance(doc, dict):
        for key in ("items", "articles", "news", "data"):
            value = doc.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def _parse_date(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                dt = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def build_freshness(doc: Any, now: datetime | None = None, stale_after_hours: float = 24.0) -> dict:
    now = now or datetime.now(timezone.utc)
    rows = _rows(doc)
    parsed: list[datetime] = []
    dated = 0
    for row in rows:
        dt = None
        for key in DATE_FIELDS:
            dt = _parse_date(row.get(key))
            if dt:
                break
        if dt:
            dated += 1
            parsed.append(dt)

    if not rows:
        return {
            "version": 1,
            "status": "unavailable",
            "principle": "数据缺失不是新鲜；没有观测值时不制造质量分数",
            "article_count": 0,
            "dated_article_count": 0,
            "date_coverage": 0.0,
            "latest_published_at": None,
            "latest_age_hours": None,
            "stale": None,
        }

    latest = max(parsed) if parsed else None
    age_hours = max(0.0, (now - latest).total_seconds() / 3600.0) if latest else None
    coverage = dated / len(rows)
    return {
        "version": 1,
        "status": "ok" if latest else "undated",
        "principle": "新鲜度只用于判断输入质量，不直接改变线上评分、决策或紧迫度",
        "article_count": len(rows),
        "dated_article_count": dated,
        "date_coverage": round(coverage, 4),
        "latest_published_at": latest.isoformat() if latest else None,
        "latest_age_hours": round(age_hours, 2) if age_hours is not None else None,
        "stale_after_hours": stale_after_hours,
        "stale": bool(age_hours is not None and age_hours > stale_after_hours),
    }


def main() -> None:
    result = build_freshness(_load(DATA))
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Input freshness: status={result['status']} coverage={result['date_coverage']}")


if __name__ == "__main__":
    main()
