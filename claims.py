#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Claim -> evidence mapping for InsureAI.

第一性原理：可信的情报必须把“结论”拆成可验证的最小事实单元。
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urlparse


def _domain(item: dict) -> str:
    try:
        return urlparse(item.get("source_url") or "").netloc.lower()
    except Exception:
        return ""


def _text(item: dict) -> str:
    return " ".join([
        str(item.get("title_zh") or item.get("title") or "").strip(),
        str(item.get("summary_zh") or item.get("summary") or "").strip(),
    ]).strip()


def _date(item: dict) -> str:
    value = item.get("published_at") or ""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).date().isoformat()
    except Exception:
        return value[:10] if len(value) >= 10 else ""


def _numbers(text: str) -> list[str]:
    return sorted(set(re.findall(r"\b\d+(?:[.,]\d+)?(?:%|m|bn|million|billion|亿|万)?\b", text.lower())))


def _entities(item: dict) -> list[str]:
    values = []
    tags = item.get("tags") or ""
    if isinstance(tags, str):
        values.extend(x.strip().lower() for x in tags.split(",") if x.strip())
    title = str(item.get("title") or "")
    values.extend(x.lower().strip() for x in re.findall(r"\b[A-Z][A-Za-z0-9&.-]*(?:\s+[A-Z][A-Za-z0-9&.-]*){0,3}", title))
    result, seen = [], set()
    for value in values:
        if len(value) >= 2 and value not in seen:
            seen.add(value)
            result.append(value)
    return result[:12]


def extract_claims(items: list[dict], event: dict) -> list[dict]:
    claims: list[dict] = []
    lead = items[0] if items else {}
    title = str(event.get("title") or _text(lead)).strip()
    if title:
        claims.append({"claim_id": "main", "type": "event", "text": title, "status": "supported"})
    ents = sorted({e for item in items for e in _entities(item)})
    if ents:
        claims.append({"claim_id": "entities", "type": "entities", "text": "涉及主体：" + "、".join(ents[:8]), "status": "supported"})
    nums = sorted({n for item in items for n in _numbers(_text(item))})
    if nums:
        claims.append({"claim_id": "numeric_facts", "type": "numeric", "text": "可观察数字事实：" + "、".join(nums[:8]), "status": "supported"})
    dates = sorted({_date(item) for item in items if _date(item)})
    if dates:
        claims.append({"claim_id": "dates", "type": "date", "text": "来源日期：" + "、".join(dates[:8]), "status": "supported"})
    return claims


def attach_evidence(claims: list[dict], items: list[dict]) -> list[dict]:
    out = []
    for claim in claims:
        evidence = []
        for item in items[:8]:
            text = _text(item)
            related = True
            if claim["type"] == "numeric":
                related = bool(set(_numbers(text)) & set(re.findall(r"\b\d+(?:[.,]\d+)?(?:%|m|bn|million|billion|亿|万)?\b", claim["text"].lower())))
            elif claim["type"] == "entities":
                related = bool(set(_entities(item)) & set(_entities({"title": claim["text"], "tags": claim["text"]})))
            if not related:
                continue
            evidence.append({
                "source_name": item.get("source_name"),
                "source_url": item.get("source_url"),
                "domain": _domain(item),
                "published_at": item.get("published_at"),
                "date_verified": bool(item.get("date_verified")),
            })
        claim = dict(claim)
        claim["evidence"] = evidence
        claim["evidence_count"] = len(evidence)
        claim["independent_domains"] = len({x["domain"] for x in evidence if x.get("domain")})
        claim["status"] = "supported" if evidence else "uncorroborated"
        if claim["independent_domains"] >= 2:
            claim["status"] = "cross_checked"
        out.append(claim)
    return out


def build_claims(items: list[dict], event: dict) -> dict:
    claims = attach_evidence(extract_claims(items, event), items)
    unsupported = sum(1 for x in claims if x["status"] == "uncorroborated")
    cross_checked = sum(1 for x in claims if x["status"] == "cross_checked")
    coverage = round(100 * (len(claims) - unsupported) / len(claims)) if claims else 0
    return {
        "version": 1,
        "claims": claims,
        "coverage": coverage,
        "cross_checked": cross_checked,
        "unsupported": unsupported,
    }
