#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""InsureAI event intelligence engine.

Core principle:
    Article -> Event -> Evidence -> Insight -> Decision

The engine is deterministic and dependency-free. Event matching considers
entity anchors, event type and time, while evidence quality explicitly rewards
independent sources instead of treating a single traceable article as a
cross-checked conclusion.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlparse

from radar import build_radar
from signal import extract_signals

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(HERE, "data.json")
OUTPUT_PATH = os.path.join(HERE, "intelligence.json")

MODEL_VERSION = 4
FINGERPRINT_VERSION = "efp-1"
TOPIC_LABELS = {
    "ai_intelligent": "AI智能化", "pension_finance": "养老金融",
    "product_innovation": "产品创新", "channel_transformation": "渠道变革",
    "capital_reinsurance": "资本与再保险", "climate_catastrophe": "气候与巨灾",
    "digital_transformation": "数字化转型", "regulatory_change": "监管变革",
}
EVENT_TYPES = {
    "acquisition": ["acquire", "acquisition", "buy", "merger", "收购", "并购", "合并"],
    "regulatory": ["regulation", "rule", "regulator", "compliance", "fine", "监管", "法规", "合规", "处罚", "办法", "政策"],
    "product": ["launch", "unveil", "product", "推出", "发布", "产品", "首发"],
    "capital": ["funding", "invest", "investment", "capital", "融资", "投资", "资本"],
    "market_entry": ["expand", "enter", "exit", "进入", "扩张", "退出", "落地"],
    "rating": ["rating", "upgrade", "downgrade", "credit", "评级", "信用", "展望"],
    "claims_loss": ["claim", "loss", "理赔", "赔付", "损失"],
    "personnel": ["appoint", "appointed", "appointment", "joins", "出任", "任命", "履新", "就任", "加盟"],
}
ACTION_WORDS = [
    "acquire", "acquisition", "buy", "merger", "launch", "unveil", "regulation", "rule", "fine", "approval",
    "invest", "investment", "expand", "enter", "exit", "raise", "funding", "upgrade", "downgrade", "loss", "claim",
    "收购", "并购", "发布", "推出", "获批", "监管", "处罚", "投资", "扩张", "退出", "融资", "升级", "下调",
    "理赔", "试点", "落地", "三审", "政策", "改革",
]
IMPACT_WORDS = [
    "reinsurance", "solvency", "capital", "catastrophe", "cyber", "ai", "artificial intelligence", "regulation",
    "regulator", "pension", "annuity", "insurance", "underwriting", "premium", "再保险", "偿付能力", "资本", "巨灾",
    "网络", "人工智能", "监管", "养老", "年金", "保险", "核保", "保费", "长期护理", "医保", "气候",
]
STOPWORDS = set("the a an and or of to in on for with from by as at is are was were be this that how what why insurance insurer insurers reinsurance news report reports viewpoint says said new company 保险 行业 新闻 报道 公司 表示 关于 最新 一个 以及 推动 进行".split())
ACTION_BY_TYPE = {
    "acquisition": "acquire", "regulatory": "regulate", "product": "launch", "capital": "invest",
    "market_entry": "enter", "rating": "rate", "claims_loss": "loss", "personnel": "appoint",
    "industry_update": "update",
}


def _norm(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"https?://\S+", " ", text)
    return re.sub(r"[^\w\u4e00-\u9fff]+", " ", text, flags=re.UNICODE).strip()


def _tokens(text: str) -> set[str]:
    return {x for x in _norm(text).split() if len(x) > 1 and x not in STOPWORDS}


def _entities(item: dict) -> list[str]:
    values = []
    tags = item.get("tags") or ""
    if isinstance(tags, str):
        values.extend(x.strip() for x in tags.split(",") if x.strip())
    title = item.get("title") or ""
    values.extend(re.findall(r"\b[A-Z][A-Za-z0-9&.-]*(?:\s+[A-Z][A-Za-z0-9&.-]*){0,3}", title))
    values.extend(re.findall(r"[\u4e00-\u9fff]{2,12}(?:公司|集团|保险|银行|证券|基金|监管局|委员会)", title))
    result, seen = [], set()
    for value in values:
        value = value.strip().lower()
        if len(value) >= 2 and value not in seen:
            seen.add(value)
            result.append(value)
    return result[:12]


def _entity_anchor(item: dict) -> str:
    entities = _entities(item)
    return entities[0] if entities else ""


def _timestamp(item: dict) -> datetime:
    try:
        return datetime.fromisoformat((item.get("published_at") or "").replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def _event_type(item: dict) -> str:
    text = _norm(" ".join([item.get("title", ""), item.get("summary", "")]))
    ranked = []
    for event_type, words in EVENT_TYPES.items():
        hits = sum(1 for word in words if word in text)
        if hits:
            ranked.append((hits, event_type))
    return max(ranked, key=lambda x: (x[0], x[1]))[1] if ranked else "industry_update"


def _signature(item: dict) -> str:
    title = item.get("title_zh") or item.get("title") or ""
    entities = tuple(sorted(_entities(item))[:6])
    core_tokens = tuple(sorted(_tokens(title))[:12])
    return hashlib.sha1("|".join(core_tokens + entities).encode("utf-8")).hexdigest()[:12]


def _event_fingerprint(item: dict) -> str:
    event_type = _event_type(item)
    anchor = _entity_anchor(item) or "unknown-entity"
    topic = item.get("research_topic") or "general"
    ts = _timestamp(item)
    period = ts.strftime("%Y-%m") if ts != datetime.min.replace(tzinfo=timezone.utc) else "undated"
    raw = "|".join((FINGERPRINT_VERSION, anchor, ACTION_BY_TYPE.get(event_type, event_type), topic, period))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _token_similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _entity_similarity(a: dict, b: dict) -> float:
    ea, eb = set(_entities(a)), set(_entities(b))
    if not ea or not eb:
        return 0.0
    return len(ea & eb) / max(1, len(ea | eb))


def _event_similarity(a: dict, b: dict) -> float:
    ta = a.get("title_zh") or a.get("title") or ""
    tb = b.get("title_zh") or b.get("title") or ""
    token = _token_similarity(ta, tb)
    entity = _entity_similarity(a, b)
    type_bonus = 0.15 if _event_type(a) == _event_type(b) else 0.0
    return min(1.0, 0.55 * token + 0.30 * entity + type_bonus)


def _within_window(a: dict, b: dict, hours: int = 96) -> bool:
    ta, tb = _timestamp(a), _timestamp(b)
    minimum = datetime.min.replace(tzinfo=timezone.utc)
    if ta == minimum or tb == minimum:
        return True
    return abs((ta - tb).total_seconds()) <= hours * 3600


def _cluster(items: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    representatives: list[tuple[str, dict]] = []
    for item in sorted(items, key=_timestamp, reverse=True):
        signature = _signature(item)
        if signature in groups:
            groups[signature].append(item)
            continue
        matched = None
        best_score = 0.0
        anchor = _entity_anchor(item)
        item_type = _event_type(item)
        for rep_key, rep_item in representatives:
            if not _within_window(item, rep_item):
                continue
            score = _event_similarity(item, rep_item)
            rep_anchor = _entity_anchor(rep_item)
            anchor_match = bool(anchor and rep_anchor and anchor == rep_anchor)
            anchor_conflict = bool(anchor and rep_anchor and anchor != rep_anchor)
            same_type = item_type == _event_type(rep_item)
            if anchor_conflict and score < 0.72:
                continue
            # Same entity but different event types should never merge on weak lexical overlap.
            # A very high similarity can still merge when titles are effectively duplicates.
            if anchor_match and not same_type and score < 0.72:
                continue
            accept = score >= 0.52 or (anchor_match and same_type and score >= 0.30)
            if accept and score > best_score:
                matched, best_score = rep_key, score
        if matched:
            groups[matched].append(item)
        else:
            groups[signature] = [item]
            representatives.append((signature, item))
    return groups


def _domain(item: dict) -> str:
    try:
        return urlparse(item.get("source_url") or "").netloc.lower()
    except Exception:
        return ""


def _score(items: list[dict]) -> dict:
    rows = []
    for item in items:
        base = float(item.get("ai_score") or 0)
        text = _norm(" ".join([item.get("title", ""), item.get("summary", "")]))
        topic = item.get("research_topic")
        relevance = min(100, max(0, base + (8 if topic else 0)))
        impact = min(100, 48 + sum(1 for x in IMPACT_WORDS if x in text) * 8 + (8 if topic in {"regulatory_change", "capital_reinsurance", "climate_catastrophe"} else 0))
        actionability = min(100, 42 + sum(1 for x in ACTION_WORDS if x in text) * 7)
        if _event_type(item) == "personnel":
            actionability = min(actionability, 42)
            impact = min(impact, 55)
        authority = float(item.get("source_authority") or 70)
        confidence = min(100, max(40, authority * 0.75 + (15 if item.get("date_verified") else 0)))
        rows.append((relevance, impact, actionability, confidence))
    relevance = max(x[0] for x in rows)
    impact = max(x[1] for x in rows)
    actionability = max(x[2] for x in rows)
    unique_domains = len({_domain(x) for x in items if _domain(x)})
    independent_bonus = min(12, max(0, unique_domains - 1) * 5)
    confidence = min(100, sum(x[3] for x in rows) / len(rows) + independent_bonus)
    novelty = max(55, 100 - (len(items) - 1) * 12)
    total = round(relevance * .30 + impact * .25 + novelty * .15 + actionability * .20 + confidence * .10)
    return {
        "relevance": round(relevance), "impact": round(impact), "novelty": round(novelty),
        "actionability": round(actionability), "confidence": round(confidence), "intelligence_score": total,
    }


def _evidence(items: list[dict]) -> list[dict]:
    return [{
        "source_name": x.get("source_name"),
        "source_url": x.get("source_url"),
        "domain": _domain(x),
        "title": x.get("title_zh") or x.get("title"),
        "published_at": x.get("published_at"),
        "date_verified": bool(x.get("date_verified")),
    } for x in sorted(items, key=_timestamp, reverse=True)[:5]]
