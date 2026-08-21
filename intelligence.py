#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""InsureAI event intelligence engine.

第一性原理：不是把相似文章堆在一起，而是识别“同一件事”，并让每个判断可追溯。
无外部 API、确定性、可测试。
"""
import hashlib
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlparse

from radar import build_radar

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(HERE, "data.json")
OUTPUT_PATH = os.path.join(HERE, "intelligence.json")

TOPIC_LABELS = {
    "ai_intelligent": "AI智能化", "pension_finance": "养老金融",
    "product_innovation": "产品创新", "channel_transformation": "渠道变革",
    "capital_reinsurance": "资本与再保险", "climate_catastrophe": "气候与巨灾",
    "digital_transformation": "数字化转型", "regulatory_change": "监管变革",
}

EVENT_TYPES = {
    "acquisition": ["acquire", "acquisition", "buy", "merger", "收购", "并购", "合并"],
    "regulatory": ["regulation", "rule", "regulator", "compliance", "fine", "监管", "法规", "合规", "处罚", "办法"],
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


def _norm(text):
    text = (text or "").lower()
    text = re.sub(r"https?://\S+", " ", text)
    return re.sub(r"[^\w\u4e00-\u9fff]+", " ", text, flags=re.UNICODE).strip()


def _tokens(text):
    return {x for x in _norm(text).split() if len(x) > 1 and x not in STOPWORDS}


def _entities(item):
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


def _timestamp(item):
    try:
        return datetime.fromisoformat((item.get("published_at") or "").replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def _event_type(item):
    text = _norm(" ".join([item.get("title", ""), item.get("summary", "")]))
    ranked = []
    for event_type, words in EVENT_TYPES.items():
        hits = sum(1 for word in words if word in text)
        if hits:
            ranked.append((hits, event_type))
    return max(ranked, key=lambda x: (x[0], x[1]))[1] if ranked else "industry_update"


def _signature(item):
    title = item.get("title_zh") or item.get("title") or ""
    entities = tuple(sorted(_entities(item))[:6])
    core_tokens = tuple(sorted(_tokens(title))[:12])
    return hashlib.sha1("|".join(core_tokens + entities).encode("utf-8")).hexdigest()[:12]


def _token_similarity(a, b):
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _entity_similarity(a, b):
    ea, eb = set(_entities(a)), set(_entities(b))
    if not ea or not eb:
        return 0.0
    return len(ea & eb) / max(1, len(ea | eb))


def _event_similarity(a, b):
    ta = a.get("title_zh") or a.get("title") or ""
    tb = b.get("title_zh") or b.get("title") or ""
    token = _token_similarity(ta, tb)
    entity = _entity_similarity(a, b)
    type_bonus = 0.15 if _event_type(a) == _event_type(b) else 0.0
    return min(1.0, 0.55 * token + 0.30 * entity + type_bonus)


def _within_window(a, b, hours=96):
    ta, tb = _timestamp(a), _timestamp(b)
    minimum = datetime.min.replace(tzinfo=timezone.utc)
    if ta == minimum or tb == minimum:
        return True
    return abs((ta - tb).total_seconds()) <= hours * 3600


def _cluster(items):
    groups = {}
    representatives = []
    for item in sorted(items, key=_timestamp, reverse=True):
        signature = _signature(item)
        if signature in groups:
            groups[signature].append(item)
            continue
        matched = None
        best_score = 0.0
        for rep_key, rep_item in representatives:
            if not _within_window(item, rep_item):
                continue
            score = _event_similarity(item, rep_item)
            same_entity = _entity_similarity(item, rep_item) >= 0.34
            same_type = _event_type(item) == _event_type(rep_item)
            accept = score >= 0.46 or (same_entity and same_type and score >= 0.30)
            if accept and score > best_score:
                matched, best_score = rep_key, score
        if matched:
            groups[matched].append(item)
        else:
            groups[signature] = [item]
            representatives.append((signature, item))
    return groups


def _score(items):
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


def _domain(item):
    try:
        return urlparse(item.get("source_url") or "").netloc.lower()
    except Exception:
        return ""


def _evidence(items):
    return [{
        "source_name": x.get("source_name"),
        "source_url": x.get("source_url"),
        "domain": _domain(x),
        "title": x.get("title_zh") or x.get("title"),
        "published_at": x.get("published_at"),
    } for x in sorted(items, key=_timestamp, reverse=True)[:5]]


def _insight(items, scores, event_type, entities):
    lead = max(items, key=lambda x: float(x.get("ai_score") or 0))
    title = lead.get("title_zh") or lead.get("title") or ""
    summary = lead.get("summary_zh") or lead.get("summary") or ""
    topic = TOPIC_LABELS.get(lead.get("research_topic"), "保险行业")
    source_count = len({x.get("source_name") for x in items if x.get("source_name")})
    evidence = _evidence(items)
    if source_count > 1:
        why = f"该变化已由 {source_count} 个信源交叉报道，优先级高于单一来源信息，适合进入事件跟踪。"
    elif scores["impact"] >= 75:
        why = f"它涉及{topic}的关键变化，潜在影响面较大，应观察其向监管、资本、产品或经营层面的传导。"
    else:
        why = f"它属于{topic}的变化信号，目前更适合作为趋势观察，不宜仅凭单一报道下结论。"
    if event_type == "personnel":
        watch = "除非出现战略调整、组织重组或经营指标变化，否则建议降低持续关注优先级。"
    elif scores["actionability"] >= 70:
        watch = "继续追踪后续公告、监管文件、市场数据和竞争对手动作，判断是否需要调整业务判断。"
    else:
        watch = "观察是否出现第二个独立信源、监管动作或同类公司跟进，以确认趋势是否形成。"
    return {
        "what_happened": title,
        "why_it_matters": why,
        "who_is_affected": topic,
        "what_to_watch": watch,
        "evidence": evidence,
        "confidence": scores["confidence"],
        "summary": summary[:360],
        "entity_count": len(entities),
    }


def build(data):
    news = data.get("news", []) if isinstance(data, dict) else []
    events = []
    for event_id, items in _cluster(news).items():
        items = sorted(items, key=_timestamp, reverse=True)
        scores = _score(items)
        lead = items[0]
        entities = sorted({e for item in items for e in _entities(item)})[:16]
        event_type = _event_type(lead)
        events.append({
            "event_id": "evt_" + event_id,
            "title": lead.get("title_zh") or lead.get("title") or "",
            "event_type": event_type,
            "entities": entities,
            "topic": lead.get("research_topic"),
            "topic_label": TOPIC_LABELS.get(lead.get("research_topic"), "保险行业"),
            "published_at": lead.get("published_at"),
            "source_count": len({x.get("source_name") for x in items if x.get("source_name")}),
            "article_count": len(items),
            "article_ids": [x.get("id") for x in items if x.get("id") is not None],
            "scores": scores,
            "insight": _insight(items, scores, event_type, entities),
        })
    events.sort(key=lambda x: (x["scores"]["intelligence_score"], x.get("published_at") or ""), reverse=True)
    today = datetime.now(timezone.utc).date().isoformat()
    daily = [e for e in events if (e.get("published_at") or "").startswith(today)][:5] or events[:5]
    event_types = Counter(e["event_type"] for e in events)
    return {
        "version": 3,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "principle": "发现值得行动的变化，而不是堆积更多新闻",
        "events": events,
        "daily_brief": daily,
        "radar": build_radar(events),
        "stats": {
            "news_count": len(news),
            "event_count": len(events),
            "multi_source_events": sum(1 for e in events if e["source_count"] > 1),
            "event_types": dict(event_types),
        },
    }


def main():
    with open(DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)
    result = build(data)
    tmp = OUTPUT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, OUTPUT_PATH)
    print(f"Intelligence engine: {result['stats']['news_count']} news -> {result['stats']['event_count']} events; daily brief={len(result['daily_brief'])}; radar={result['radar']['stats']['entities']} entities")


if __name__ == "__main__":
    main()
