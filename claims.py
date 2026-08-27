#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Proposition-level claim intelligence for InsureAI (Claim Schema v3).

Article -> Claim -> Evidence: 每条 claim 是一条可判定真伪的命题，
证据带方向（support / contradict），置信度按来源层级加权。
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from source_tiers import tier_for_item

CLAIM_SCHEMA_VERSION = 3

VERIFICATION_STATUSES = ("unverified", "single_source", "cross_checked", "conflicted")

# ---------------------------------------------------------------------------
# text helpers
# ---------------------------------------------------------------------------

_DENY_KEYWORDS = ("denied", "denies", "rumour", "rumor", "辟谣", "否认", "澄清", "传闻不实")

_ACQUISITION_KEYWORDS = (
    "acquire", "acquisition", "acquires", "to buy", "agrees to buy", "takeover",
    "收购", "并购", "收购案", "购入",
)
_REGULATORY_KEYWORDS = (
    "probe", "investigation", "fines", "fined", "penalty", "issues rule", "regulator",
    "监管", "处罚", "罚款", "调查", "出台", "发布通知", "新规",
)
_PRODUCT_KEYWORDS = ("launch", "launches", "unveil", "推出", "发布", "上线")
_RATING_UP_KEYWORDS = ("upgrade", "upgrades", "upgraded", "上调", "调高")
_RATING_DOWN_KEYWORDS = ("downgrade", "downgrades", "downgraded", "下调", "调低")
_PERSONNEL_KEYWORDS = ("appoint", "appoints", "appointed", "任命", "出任", "履新", "辞任")
_MARKET_ENTRY_KEYWORDS = ("enters", "expand into", "expands to", "进入", "布局", "扩张至")
_CAPITAL_KEYWORDS = ("raise", "raises", "funding", "investment round", "融资", "注资")
_LOSS_KEYWORDS = ("loss", "losses", "payout", "claims payment", "损失", "赔付", "理赔金额")

# 金额语境关键词：金额只有出现在这些词附近才算"该命题的值"，避免把营收等
# 无关数字误当成交易金额而制造假冲突。
_AMOUNT_CONTEXT_KEYWORDS = (
    "deal", "transaction", "acquire", "acquisition", "valued at", "worth",
    "price tag", "raise", "raised", "funding", "fine", "fined", "penalty",
    "loss", "payout", "收购", "交易", "融资", "注资", "罚款", "处罚", "损失", "赔付",
)

_UNIT_MULTIPLIERS = {
    "thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12,
    "mn": 1e6, "m": 1e6, "bn": 1e9, "k": 1e3, "tn": 1e12,
    "万": 1e4, "亿": 1e8, "万亿": 1e12,
}

_CURRENCIES = {"$": "USD", "us$": "USD", "usd": "USD", "€": "EUR", "£": "GBP", "¥": "CNY", "￥": "CNY", "rmb": "CNY"}

_AMOUNT_RE = re.compile(
    r"(?P<cur>\$|€|£|￥|¥|US\$|us\$|USD|usd|RMB|rmb)?\s*"
    r"(?P<num>\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>trillion|billion|million|thousand|万亿|亿|万|bn|mn|tm|tn|k|m|b)?",
    re.IGNORECASE,
)

_DATE_RE = re.compile(
    r"(?:effective|takes? effect|生效(?:日期)?|自)(?:\s+(?:from|on|于))?\s*"
    r"((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}"
    r"|\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?)",
    re.IGNORECASE,
)

_MONTHS = {m.lower(): i + 1 for i, m in enumerate(
    ("January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"))}


def _domain(item: dict) -> str:
    try:
        return (urlparse(item.get("source_url") or "").netloc or "").lower()
    except Exception:
        return ""


def _text(item: dict) -> str:
    return " ".join([
        str(item.get("title_zh") or item.get("title") or "").strip(),
        str(item.get("summary_zh") or item.get("summary") or "").strip(),
        str(item.get("title") or "").strip(),
        str(item.get("summary") or "").strip(),
    ]).strip()


def _date(item: dict) -> str:
    value = item.get("published_at") or ""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).date().isoformat()
    except Exception:
        return value[:10] if len(value) >= 10 else ""


def _entities(item: dict) -> list[str]:
    values = []
    tags = item.get("tags") or ""
    if isinstance(tags, str):
        values.extend(x.strip() for x in tags.split(",") if x.strip())
    title = str(item.get("title") or "")
    values.extend(re.findall(r"\b[A-Z][A-Za-z0-9&.-]*(?:\s+[A-Z][A-Za-z0-9&.-]*){0,3}", title))
    result, seen = [], set()
    for value in values:
        key = value.lower()
        if len(value) >= 2 and key not in seen:
            seen.add(key)
            result.append(value)
    return result[:12]


def normalize_amount(num: str, unit: str | None, currency: str | None) -> float:
    value = float(num.replace(",", ""))
    unit_key = (unit or "").lower()
    multiplier = _UNIT_MULTIPLIERS.get(unit_key, 1.0)
    return value * multiplier


def parse_amounts(text: str) -> list[dict]:
    """Extract currency/scale amounts with normalized values."""
    out = []
    for match in _AMOUNT_RE.finditer(text):
        num, unit, cur = match.group("num"), match.group("unit"), match.group("cur")
        if not num or (not unit and len(num) < 2):
            continue
        if unit and unit.lower() not in _UNIT_MULTIPLIERS:
            continue
        if not unit and not cur:
            continue
        normalized = normalize_amount(num, unit, cur)
        if normalized <= 0 or normalized > 1e15:
            continue
        span = match.group(0).strip()
        if len(span) < 2:
            continue
        out.append({
            "raw": span,
            "normalized": normalized,
            "currency": _CURRENCIES.get((cur or "").lower(), None) if cur else None,
        })
    return out


def contextual_amounts(item: dict) -> list[dict]:
    """Amounts that plausibly belong to the event proposition (title always counts)."""
    title = str(item.get("title") or "") + " " + str(item.get("title_zh") or "")
    summary = str(item.get("summary") or "") + " " + str(item.get("summary_zh") or "")
    amounts = parse_amounts(title)
    for match in re.finditer(_AMOUNT_RE, summary):
        num, unit, cur = match.group("num"), match.group("unit"), match.group("cur")
        if not num:
            continue
        if unit and unit.lower() not in _UNIT_MULTIPLIERS:
            continue
        window = summary[max(0, match.start() - 60):match.end() + 60].lower()
        if not any(k in window for k in _AMOUNT_CONTEXT_KEYWORDS):
            continue
        normalized = normalize_amount(num, unit, cur)
        if normalized <= 0 or normalized > 1e15:
            continue
        amounts.append({"raw": match.group(0).strip(), "normalized": normalized,
                        "currency": _CURRENCIES.get((cur or "").lower(), None) if cur else None})
    deduped, seen = [], set()
    for amount in amounts:
        key = round(amount["normalized"], 2)
        if key not in seen:
            seen.add(key)
            deduped.append(amount)
    return deduped


def _event_amounts(items: list[dict]) -> list[dict]:
    """Contextual amounts across all articles, first-seen order, deduped by value."""
    out, seen = [], set()
    for item in items:
        for amount in contextual_amounts(item):
            key = round(amount["normalized"], 2)
            if key not in seen:
                seen.add(key)
                out.append(amount)
    return out


def parse_effective_dates(text: str) -> list[dict]:
    out = []
    for match in _DATE_RE.finditer(text):
        raw = match.group(1).strip()
        iso = _to_iso(raw)
        if iso:
            out.append({"raw": raw, "iso": iso})
    return out


def _to_iso(raw: str) -> str | None:
    m = re.match(r"([A-Za-z]+)\s+(\d{1,2})", raw)
    if m and m.group(1).lower() in _MONTHS:
        return f"2026-{_MONTHS[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"
    m = re.match(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", raw)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return None


def _has_any(text: str, keywords) -> bool:
    lowered = text.lower()
    return any(k.lower() in lowered for k in keywords)


def _infer_category(event: dict, text: str) -> str:
    event_type = str(event.get("event_type") or "").strip()
    if event_type and event_type != "industry_update":
        return event_type
    if _has_any(text, _ACQUISITION_KEYWORDS):
        return "acquisition"
    if _has_any(text, _REGULATORY_KEYWORDS):
        return "regulatory"
    if _has_any(text, _RATING_UP_KEYWORDS) or _has_any(text, _RATING_DOWN_KEYWORDS):
        return "rating"
    if _has_any(text, _PERSONNEL_KEYWORDS):
        return "personnel"
    if _has_any(text, _PRODUCT_KEYWORDS):
        return "product"
    return event_type or "industry_update"


def _subject_object(event: dict, items: list[dict]) -> tuple[str | None, str | None]:
    tags = _entities(items[0]) if items else []
    event_entities = [str(x) for x in (event.get("entities") or []) if str(x).strip()]
    subject = tags[0] if tags else (event_entities[0] if event_entities else None)
    obj = tags[1] if len(tags) > 1 else (event_entities[-1] if len(event_entities) > 1 else None)
    return subject, obj


def _span(text: str, keyword: str, width: int = 70) -> str:
    idx = text.lower().find(keyword.lower())
    if idx < 0:
        return text[:width]
    start = max(0, idx - 30)
    return re.sub(r"\s+", " ", text[start:idx + width]).strip()


# ---------------------------------------------------------------------------
# proposition extraction
# ---------------------------------------------------------------------------

def extract_propositions(items: list[dict], event: dict) -> list[dict]:
    combined = " ".join(_text(x) for x in items)
    category = _infer_category(event, str(event.get("title") or "") + " " + combined)
    subject, obj = _subject_object(event, items)
    lead = items[0] if items else {}
    propositions: list[dict] = []
    event_id = str(event.get("event_id") or "")

    def add(claim_type: str, claim_text: str, *, value=None, pattern=None, subject_ref=None, object_ref=None):
        propositions.append({
            "claim_type": claim_type,
            "claim_text": claim_text,
            "subject": subject_ref or subject,
            "object": object_ref or obj,
            "value": value,
            "match_pattern": pattern or claim_type,
        })

    if category == "acquisition":
        if subject and obj:
            add("acquisition_intent", f"{subject} 拟收购 {obj}", pattern="acquisition_intent")
            add("transaction_scope", f"交易标的为 {obj}", pattern="acquisition_intent")
        elif subject:
            add("acquisition_intent", f"{subject} 存在收购动作（{_span(combined, '收购', 50)}）", pattern="acquisition_intent")
        for amount in _event_amounts(items)[:3]:
            add("transaction_amount", f"交易金额为 {amount['raw']}", value=amount, pattern="transaction_amount")
        if _has_any(combined, ("expand", "strengthen", "加强", "布局", "拓展")):
            add("strategic_context", "战略意图：" + _span(combined, "expand" if "expand" in combined else "布局"), pattern="strategic_context")
    elif category == "regulatory":
        add("regulatory_action", "监管行动：" + _span(combined, "监管" if "监管" in combined else "regulator"), pattern="regulatory_action")
        for amount in _event_amounts(items)[:2]:
            add("fine_amount", f"处罚/涉及金额为 {amount['raw']}", value=amount, pattern="fine_amount")
        dates = parse_effective_dates(combined)
        if dates:
            add("effective_date", f"生效时间为 {dates[0]['raw']}", value=dates[0], pattern="effective_date")
    elif category == "rating":
        direction = "上调" if _has_any(combined, _RATING_UP_KEYWORDS) else "下调"
        target = obj or subject or "相关主体"
        add("rating_change", f"{target} 信用评级被{direction}", pattern="rating_change")
        for amount in _event_amounts(items)[:2]:
            add("rating_amount", f"评级涉及金额为 {amount['raw']}", value=amount, pattern="transaction_amount")
    elif category == "personnel":
        add("executive_change", "人事变动：" + _span(combined, "appoint" if "appoint" in combined.lower() else "任命"), pattern="executive_change")
    elif category == "product":
        add("product_launch", f"{subject or '相关主体'} 发布新产品/平台（{_span(combined, 'launch' if 'launch' in combined.lower() else '推出', 60)}）", pattern="product_launch")
        for amount in _event_amounts(items)[:2]:
            add("product_amount", f"产品涉及金额为 {amount['raw']}", value=amount, pattern="transaction_amount")
    elif category == "capital":
        add("capital_raise", f"{subject or '相关主体'} 涉及融资/注资（{_span(combined, '融资' if '融资' in combined else 'raise', 60)}）", pattern="capital_raise")
        for amount in _event_amounts(items)[:3]:
            add("capital_amount", f"融资金额为 {amount['raw']}", value=amount, pattern="transaction_amount")
    elif category == "market_entry":
        add("market_entry", f"{subject or '相关主体'} 进入/布局新市场（{_span(combined, '进入' if '进入' in combined else 'enters', 60)}）", pattern="market_entry")
        for amount in _event_amounts(items)[:2]:
            add("market_amount", f"涉及金额为 {amount['raw']}", value=amount, pattern="transaction_amount")
    elif category == "claims_loss":
        add("loss_event", f"{subject or '相关主体'} 涉及损失/赔付事件（{_span(combined, '损失' if '损失' in combined else 'loss', 60)}）", pattern="loss_event")
        for amount in _event_amounts(items)[:3]:
            add("loss_amount", f"损失/赔付金额为 {amount['raw']}", value=amount, pattern="transaction_amount")
    else:
        add("event_summary", str(event.get("title") or _text(lead)).strip(), pattern="event_summary")
        for amount in _event_amounts(items)[:2]:
            add("reported_amount", f"涉及金额为 {amount['raw']}", value=amount, pattern="transaction_amount")

    for idx, prop in enumerate(propositions, start=1):
        prop["claim_id"] = f"{event_id}/c{idx}" if event_id else f"c{idx}"
        prop["event_id"] = event_id or None
    return propositions


# ---------------------------------------------------------------------------
# evidence attachment
# ---------------------------------------------------------------------------

def _pattern_keywords(pattern: str):
    mapping = {
        "acquisition_intent": _ACQUISITION_KEYWORDS,
        "regulatory_action": _REGULATORY_KEYWORDS,
        "product_launch": _PRODUCT_KEYWORDS,
        "executive_change": _PERSONNEL_KEYWORDS,
        "market_entry": _MARKET_ENTRY_KEYWORDS,
        "capital_raise": _CAPITAL_KEYWORDS,
        "loss_event": _LOSS_KEYWORDS,
        "rating_change": _RATING_UP_KEYWORDS + _RATING_DOWN_KEYWORDS,
        "strategic_context": ("expand", "strengthen", "加强", "布局", "拓展"),
        "event_summary": (),
    }
    return mapping.get(pattern, ())


def _evidence_row(item: dict, relation: str, matched_span: str = "") -> dict:
    return {
        "evidence_id": str(item.get("id") or item.get("source_url") or item.get("source_name") or "unknown"),
        "source_name": item.get("source_name"),
        "source_url": item.get("source_url"),
        "domain": _domain(item),
        "source_tier": tier_for_item(item),
        "published_at": item.get("published_at"),
        "date_verified": bool(item.get("date_verified")),
        "relation": relation,
        "matched_span": matched_span[:160],
    }


def _match_keyword_claim(prop: dict, item: dict) -> tuple[bool, bool, str]:
    """Return (supports, contradicts, matched_span) for keyword-based propositions."""
    text = _text(item)
    if prop.get("match_pattern") == "event_summary":
        return True, False, prop.get("claim_text", "")[:80]
    keywords = _pattern_keywords(prop.get("match_pattern"))
    supports = bool(keywords) and _has_any(text, keywords)
    if supports and prop.get("subject"):
        supports = str(prop["subject"]).lower() in text.lower()
    contradicts = not supports and _has_any(text, _DENY_KEYWORDS)
    keyword = next((k for k in keywords if k.lower() in text.lower()), "")
    return supports, contradicts, _span(text, keyword) if keyword else prop.get("claim_text", "")[:80]


def _match_value_claim(prop: dict, item: dict) -> tuple[bool, bool, str]:
    """Return (supports, contradicts, matched_span) for value-based propositions."""
    value = prop.get("value") or {}
    if value.get("normalized") is not None:
        target = round(float(value["normalized"]), 2)
        amounts = contextual_amounts(item)
        if not amounts:
            return False, False, ""
        own = next((a for a in amounts if round(a["normalized"], 2) == target), amounts[0])
        supports = round(own["normalized"], 2) == target
        return supports, not supports, own["raw"]
    if value.get("iso"):
        dates = parse_effective_dates(_text(item))
        if not dates:
            return False, False, ""
        own = next((d for d in dates if d["iso"] == value["iso"]), dates[0])
        supports = own["iso"] == value["iso"]
        return supports, not supports, own["raw"]
    return False, False, ""


def _confidence(supporting: list[dict], contradicting: list[dict]) -> int:
    if not supporting:
        return 20
    domains = {x["domain"] for x in supporting if x.get("domain")}
    best_tier = min(x.get("source_tier") or 3 for x in supporting)
    tier_score = {1: 40, 2: 34, 3: 26, 4: 18}.get(best_tier, 26)
    score = 30 + tier_score + 15 * min(max(len(domains) - 1, 0), 3)
    if len(domains) >= 2:
        score += 10
    if contradicting:
        score -= 25
    score = max(0, min(100, round(score)))
    if len(domains) <= 1:
        score = min(score, 65)
    return score


def attach_evidence(propositions: list[dict], items: list[dict]) -> list[dict]:
    out = []
    for prop in propositions:
        supporting, contradicting = [], []
        is_value_claim = bool((prop.get("value") or {}).get("normalized") is not None or (prop.get("value") or {}).get("iso"))
        for item in items[:12]:
            if is_value_claim:
                supports, contradicts, matched = _match_value_claim(prop, item)
            else:
                supports, contradicts, matched = _match_keyword_claim(prop, item)
            if supports:
                supporting.append(_evidence_row(item, "support", matched))
            elif contradicts:
                contradicting.append(_evidence_row(item, "contradict", matched))
        claim = {
            "claim_id": prop.get("claim_id"),
            "event_id": prop.get("event_id"),
            "claim_type": prop.get("claim_type"),
            "claim_text": prop.get("claim_text"),
            "subject": prop.get("subject"),
            "object": prop.get("object"),
            "value": prop.get("value"),
            "source_articles": sorted({x["evidence_id"] for x in supporting + contradicting}),
            "supporting_evidence": supporting,
            "contradicting_evidence": contradicting,
            "evidence": supporting,
            "evidence_refs": [x["evidence_id"] for x in supporting],
            "evidence_count": len(supporting),
            "independent_domains": len({x["domain"] for x in supporting if x.get("domain")}),
        }
        if contradicting and supporting:
            claim["verification_status"] = "conflicted"
        elif not supporting:
            claim["verification_status"] = "unverified"
        elif claim["independent_domains"] >= 2:
            claim["verification_status"] = "cross_checked"
        else:
            claim["verification_status"] = "single_source"
        claim["confidence"] = _confidence(supporting, contradicting)
        dates = sorted({_date_from(x) for x in supporting if _date_from(x)})
        claim["first_seen"] = dates[0] if dates else None
        claim["last_confirmed"] = dates[-1] if dates else None
        out.append(claim)
    return out


def _date_from(evidence: dict) -> str:
    value = evidence.get("published_at") or ""
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc).date().isoformat()
    except Exception:
        return ""


def build_claims(items: list[dict], event: dict) -> dict:
    claims = attach_evidence(extract_propositions(items, event), items)
    supported = [x for x in claims if x["verification_status"] != "unverified"]
    cross_checked = sum(1 for x in claims if x["verification_status"] == "cross_checked")
    conflicted = sum(1 for x in claims if x["verification_status"] == "conflicted")
    coverage = round(100 * len(supported) / len(claims)) if claims else 0
    return {
        "version": CLAIM_SCHEMA_VERSION,
        "claims": claims,
        "coverage": coverage,
        "cross_checked": cross_checked,
        "conflicted": conflicted,
        "unsupported": len(claims) - len(supported),
        "proposition_count": len(claims),
    }
