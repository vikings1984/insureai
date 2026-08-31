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
from intelligence_signal import extract_signals
from source_tiers import TIER_AUTHORITY, tier_for_item

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

def _within_window(a: dict, b: dict, hours: int = 720) -> bool:
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
        for rep_key, rep_item in representatives:
            sim = _event_similarity(item, rep_item)
            # 持续性事件（合作/会议/系列 webinar）报道间隔常以周/月计，
            # 96h 硬窗口会把同 deal 真同事件切成多个单源事件 → false_split。
            # 放宽到 720h（30天）；超时但标题/实体相似度仍极高（>=0.70）的
            # 真同事件（如跨更长窗口的同一收购后续报道）仍允许合并，
            # 由 score>=0.52 与 anchor_conflict 守卫兜底防误合（Sprint 4 / 方案C）。
            if not _within_window(item, rep_item) and sim < 0.70:
                continue
            score = sim
            rep_anchor = _entity_anchor(rep_item)
            anchor_match = bool(anchor and rep_anchor and anchor == rep_anchor)
            anchor_conflict = bool(anchor and rep_anchor and anchor != rep_anchor)
            same_type = _event_type(item) == _event_type(rep_item)
            # anchor 只是 tags 的首个实体（编辑排序而非语义）；实体集合高度重叠时
            # anchor 冲突只是语态差异（主动/被动），不得硬阻断合并造成假拆分。
            entity_overlap = _entity_similarity(item, rep_item)
            if anchor_conflict and entity_overlap < 0.5 and score < 0.72:
                continue
            # Same-anchor, same-type articles that share ONLY the company name
            # (no specific sub-entity in common) are distinct events — e.g. two
            # different appointments at one company — and must not be merged.
            # Genuine same-event coverage (e.g. the same acquisition target
            # reported by two sources) shares a sub-entity beyond the anchor and
            # still merges. This fixes false merges on real data (Swiss Re 35/65,
            # two different appointments) without breaking the frozen v1 AGI
            # Heller-Kowitz same-event pair (shares the deal target entity).
            shared_entities = set(_entities(item)) & set(_entities(rep_item))
            specific_shared = shared_entities - {anchor, rep_anchor}
            accept = score >= 0.52 or (
                anchor_match and same_type and (specific_shared or score >= 0.42)
            )
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
        declared = float(item.get("source_authority") or 0)
        tier_authority = TIER_AUTHORITY.get(tier_for_item(item), 68)
        authority = round(0.6 * declared + 0.4 * tier_authority) if declared else tier_authority
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
    return {"relevance": round(relevance), "impact": round(impact), "novelty": round(novelty), "actionability": round(actionability), "confidence": round(confidence), "intelligence_score": total}

def _evidence(items: list[dict]) -> list[dict]:
    return [{"source_name": x.get("source_name"), "source_url": x.get("source_url"), "domain": _domain(x), "title": x.get("title_zh") or x.get("title"), "published_at": x.get("published_at"), "date_verified": bool(x.get("date_verified"))} for x in sorted(items, key=_timestamp, reverse=True)[:5]]

def _evidence_quality(items: list[dict], evidence: list[dict]) -> tuple[float, str]:
    source_count = len({x.get("source_name") for x in items if x.get("source_name")})
    source_independence = 1.0 if source_count >= 2 else 0.0
    traceability = sum(1 for x in evidence if x.get("source_url")) / max(1, len(evidence))
    date_verified = sum(1 for x in evidence if x.get("date_verified")) / max(1, len(evidence))
    coverage = round((source_independence * .50 + traceability * .25 + date_verified * .25) * 100, 1)
    return coverage, ("cross_checked" if source_count >= 2 else "single_source")

def _trust(coverage: float, conflict: bool = False) -> str:
    if conflict or coverage < 55:
        return "low"
    if coverage < 80:
        return "medium"
    return "high"

def _insight(items: list[dict], scores: dict, event_type: str, entities: list[str]) -> dict:
    lead = max(items, key=lambda x: float(x.get("ai_score") or 0))
    title = lead.get("title_zh") or lead.get("title") or ""
    summary = lead.get("summary_zh") or lead.get("summary") or ""
    topic = TOPIC_LABELS.get(lead.get("research_topic"), "保险行业")
    source_count = len({x.get("source_name") for x in items if x.get("source_name")})
    evidence = _evidence(items)
    coverage, evidence_status = _evidence_quality(items, evidence)
    signals = extract_signals(title, summary, topic=lead.get("research_topic"))
    if source_count > 1:
        why = f"该变化已由 {source_count} 个独立信源交叉报道，适合进入事件跟踪。"
    elif scores["impact"] >= 75:
        why = f"它涉及{topic}的关键变化，潜在影响面较大，但目前仍需独立证据确认。"
    else:
        why = f"它属于{topic}的变化信号，目前更适合作为趋势观察，不宜仅凭单一报道下结论。"
    if event_type == "personnel":
        watch = "除非出现战略调整、组织重组或经营指标变化，否则建议降低持续关注优先级。"
    elif scores["actionability"] >= 70:
        watch = "继续追踪后续公告、监管文件、市场数据和竞争对手动作，判断是否需要调整业务判断。"
    else:
        watch = "观察是否出现第二个独立信源、监管动作或同类公司跟进，以确认趋势是否形成。"
    review_required = coverage < 75 or event_type in {"regulatory", "rating", "claims_loss"}
    return {"what_happened": title, "why_it_matters": why, "who_is_affected": topic, "what_to_watch": watch, "evidence": evidence, "evidence_coverage": coverage, "evidence_status": evidence_status, "signals": signals, "confidence": scores["confidence"], "summary": summary[:360], "entity_count": len(entities), "human_review_required": review_required}

def build(data: dict) -> dict:
    news = data.get("news", []) if isinstance(data, dict) else []
    events = []
    for event_id, items in _cluster(news).items():
        items = sorted(items, key=_timestamp, reverse=True)
        scores = _score(items)
        lead = items[0]
        entities = sorted({e for item in items for e in _entities(item)})[:16]
        event_type = _event_type(lead)
        evidence = _evidence(items)
        evidence_coverage, evidence_status = _evidence_quality(items, evidence)
        review_required = evidence_coverage < 75 or event_type in {"regulatory", "rating", "claims_loss"}
        conflict = False
        trust_level = _trust(evidence_coverage, conflict)
        events.append({"event_id": "evt_" + event_id, "event_fingerprint": _event_fingerprint(lead), "event_fingerprint_version": FINGERPRINT_VERSION, "title": lead.get("title_zh") or lead.get("title") or "", "event_type": event_type, "entities": entities, "topic": lead.get("research_topic"), "topic_label": TOPIC_LABELS.get(lead.get("research_topic"), "保险行业"), "published_at": lead.get("published_at"), "source_count": len({x.get("source_name") for x in items if x.get("source_name")}), "article_count": len(items), "article_ids": [x.get("id") for x in items if x.get("id") is not None], "scores": scores, "evidence": evidence, "evidence_coverage": evidence_coverage, "evidence_status": evidence_status, "review_required": review_required, "trust": {"level": trust_level, "conflict": conflict}, "insight": _insight(items, scores, event_type, entities)})
    events.sort(key=lambda x: (x["scores"]["intelligence_score"], x.get("published_at") or ""), reverse=True)
    today = datetime.now(timezone.utc).date().isoformat()
    daily = [e for e in events if (e.get("published_at") or "").startswith(today)][:5] or events[:5]
    event_types = Counter(e["event_type"] for e in events)
    return {"version": MODEL_VERSION, "generated_at": datetime.now(timezone.utc).isoformat(), "principle": "发现值得行动的变化，而不是堆积更多新闻", "model": {"article": "source item", "event": "entity + action + topic + time", "evidence": "traceable independent source support", "decision": "advisory only / human approval boundary"}, "events": events, "daily_brief": daily, "radar": build_radar(events), "stats": {"news_count": len(news), "event_count": len(events), "multi_source_events": sum(1 for e in events if e["source_count"] > 1), "review_required_events": sum(1 for e in events if e["review_required"]), "event_types": dict(event_types)}}

def main() -> None:
    with open(DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)
    result = build(data)
    tmp = OUTPUT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, OUTPUT_PATH)
    print(f"Intelligence v{MODEL_VERSION}: {result['stats']['news_count']} news -> {result['stats']['event_count']} events; review={result['stats']['review_required_events']}")

if __name__ == "__main__":
    main()
