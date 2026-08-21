#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
InsureAI Intelligence Engine
============================
第一性原理：用户需要的不是更多新闻，而是更快发现值得行动的行业变化。

本模块不依赖外部 LLM/API，使用可解释、确定性的规则生成：
- event：将同一事件的多篇报道聚合
- intelligence_score：relevance / impact / novelty / actionability / confidence
- insight：发生了什么 / 为什么重要 / 影响谁 / 接下来关注什么
- daily brief：当天最值得关注的 5 个事件

输入：data.json
输出：intelligence.json
"""

import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(HERE, "data.json")
OUTPUT_PATH = os.path.join(HERE, "intelligence.json")

TOPIC_LABELS = {
    "ai_intelligent": "AI智能化",
    "pension_finance": "养老金融",
    "product_innovation": "产品创新",
    "channel_transformation": "渠道变革",
    "capital_reinsurance": "资本与再保险",
    "climate_catastrophe": "气候与巨灾",
    "digital_transformation": "数字化转型",
    "regulatory_change": "监管变革",
}

ACTION_WORDS = [
    "acquire", "acquisition", "buy", "merger", "launch", "unveil", "appoint",
    "regulation", "rule", "fine", "approval", "invest", "investment", "expand",
    "enter", "exit", "raise", "funding", "upgrade", "downgrade", "loss", "claim",
    "收购", "并购", "发布", "推出", "获批", "监管", "处罚", "投资", "扩张", "退出",
    "融资", "升级", "下调", "理赔", "试点", "落地", "三审", "政策", "改革",
]

IMPACT_WORDS = [
    "reinsurance", "solvency", "capital", "catastrophe", "cyber", "ai", "artificial intelligence",
    "regulation", "regulator", "pension", "annuity", "insurance", "underwriting", "premium",
    "再保险", "偿付能力", "资本", "巨灾", "网络", "人工智能", "监管", "养老", "年金", "保险",
    "核保", "保费", "长期护理", "医保", "气候",
]

PERSONNEL_WORDS = [
    "appoints", "appointed", "appointment", "names ", "joins", "出任", "任命", "履新", "就任", "加盟",
]

STOPWORDS = set(
    "the a an and or of to in on for with from by as at is are was were be this that how what why "
    "insurance insurer insurers reinsurance news report reports viewpoint says said new company "
    "保险 行业 新闻 报道 公司 表示 关于 最新 一个 以及 推动 进行".split()
)


def _norm(text):
    text = (text or "").lower()
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[^\w\u4e00-\u9fff]+", " ", text, flags=re.UNICODE)
    return text.strip()


def _tokens(text):
    raw = _norm(text).split()
    return {x for x in raw if len(x) > 1 and x not in STOPWORDS}


def _entities(item):
    """轻量实体抽取：优先 tags，其次标题中的英文实体/中文公司名片段。"""
    entities = []
    tags = item.get("tags") or ""
    if isinstance(tags, str):
        entities.extend([x.strip().lower() for x in tags.split(",") if x.strip()])
    title = item.get("title") or ""
    # 大写英文公司/机构串，例如 Munich Re、AM Best、JD Power。
    entities.extend(re.findall(r"\b[A-Z][A-Za-z0-9&.-]*(?:\s+[A-Z][A-Za-z0-9&.-]*){0,3}", title))
    # 常见中文公司/机构后缀。
    entities.extend(re.findall(r"[\u4e00-\u9fff]{2,12}(?:公司|集团|保险|银行|证券|基金|监管局|委员会)", title))
    seen = set()
    result = []
    for e in entities:
        e = e.strip().lower()
        if len(e) >= 2 and e not in seen:
            seen.add(e)
            result.append(e)
    return result[:12]


def _domain(item):
    try:
        return urlparse(item.get("source_url") or "").netloc.lower()
    except Exception:
        return ""


def _timestamp(item):
    value = item.get("published_at") or ""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def _event_key(item):
    title = item.get("title_zh") or item.get("title") or ""
    summary = item.get("summary_zh") or item.get("summary") or ""
    tokens = sorted(_tokens(title))
    entities = sorted(_entities(item))
    # 标题主体 + 实体构成稳定事件指纹；同事件不同媒体标题通常共享实体与核心词。
    core = "|".join(tokens[:12] + entities[:8])
    if not core:
        core = _norm(title)[:120]
    return hashlib.sha1(core.encode("utf-8")).hexdigest()[:12]


def _similarity(a, b):
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(1, len(ta | tb))


def _cluster(items):
    """两级聚类：稳定指纹优先；标题 token 相似度作为保守补充。"""
    groups = {}
    representatives = []
    for item in sorted(items, key=_timestamp, reverse=True):
        key = _event_key(item)
        if key in groups:
            groups[key].append(item)
            continue
        title = item.get("title_zh") or item.get("title") or ""
        matched = None
        for rep_key, rep_title in representatives:
            if _similarity(title, rep_title) >= 0.62:
                matched = rep_key
                break
        if matched:
            groups[matched].append(item)
        else:
            groups[key] = [item]
            representatives.append((key, title))
    return groups


def _score(items):
    scores = []
    for item in items:
        base = float(item.get("ai_score") or 0)
        text = _norm(" ".join([item.get("title", ""), item.get("summary", "")]))
        topic = item.get("research_topic")
        relevance = min(100, max(0, base + (8 if topic else 0)))
        impact_hits = sum(1 for x in IMPACT_WORDS if x in text)
        impact = min(100, 48 + impact_hits * 8 + (8 if topic in {"regulatory_change", "capital_reinsurance", "climate_catastrophe"} else 0))
        action_hits = sum(1 for x in ACTION_WORDS if x in text)
        actionability = min(100, 42 + action_hits * 7)
        if any(x in text for x in PERSONNEL_WORDS):
            actionability = min(actionability, 42)
            impact = min(impact, 55)
        authority = float(item.get("source_authority") or 70)
        confidence = min(100, max(40, authority * 0.75 + (15 if item.get("date_verified") else 0)))
        scores.append((relevance, impact, actionability, confidence))
    relevance = max(x[0] for x in scores)
    impact = max(x[1] for x in scores)
    actionability = max(x[2] for x in scores)
    confidence = min(100, sum(x[3] for x in scores) / len(scores) + min(10, (len(items) - 1) * 3))
    # 新颖性：单篇新事件最高，多源事件因重复报道降低，避免“报道最多”变成“最重要”。
    novelty = max(55, 100 - (len(items) - 1) * 12)
    total = round(relevance * 0.30 + impact * 0.25 + novelty * 0.15 + actionability * 0.20 + confidence * 0.10)
    return {
        "relevance": round(relevance),
        "impact": round(impact),
        "novelty": round(novelty),
        "actionability": round(actionability),
        "confidence": round(confidence),
        "intelligence_score": total,
    }


def _insight(items, scores):
    lead = max(items, key=lambda x: float(x.get("ai_score") or 0))
    title = lead.get("title_zh") or lead.get("title") or ""
    summary = lead.get("summary_zh") or lead.get("summary") or ""
    topic = TOPIC_LABELS.get(lead.get("research_topic"), "保险行业")
    source_count = len({x.get("source_name") for x in items if x.get("source_name")})
    if source_count > 1:
        why = f"该变化已被 {source_count} 个信源独立报道，说明它不只是单一媒体噪声，值得作为行业事件跟踪。"
    elif scores["impact"] >= 75:
        why = f"它涉及{topic}的关键变化，潜在影响面较大，应关注后续监管、资本、产品或经营层面的连锁反应。"
    else:
        why = f"它与{topic}相关，当前更适合作为趋势信号观察，而不是直接视为行业结论。"
    if scores["actionability"] >= 70:
        watch = "建议继续追踪后续公告、监管文件、市场数据或竞争对手动作，并评估是否需要调整业务判断。"
    else:
        watch = "建议观察是否出现第二个独立信源、监管动作或同类公司跟进，以确认趋势是否形成。"
    return {
        "what_happened": title,
        "why_it_matters": why,
        "who_is_affected": topic,
        "what_to_watch": watch,
        "evidence": [
            {
                "source_name": x.get("source_name"),
                "source_url": x.get("source_url"),
                "title": x.get("title_zh") or x.get("title"),
            }
            for x in sorted(items, key=_timestamp, reverse=True)[:5]
        ],
        "confidence": scores["confidence"],
        "summary": summary[:360],
    }


def build(data):
    news = data.get("news", []) if isinstance(data, dict) else []
    groups = _cluster(news)
    events = []
    for event_id, items in groups.items():
        items = sorted(items, key=_timestamp, reverse=True)
        scores = _score(items)
        lead = items[0]
        event = {
            "event_id": "evt_" + event_id,
            "title": lead.get("title_zh") or lead.get("title") or "",
            "topic": lead.get("research_topic"),
            "topic_label": TOPIC_LABELS.get(lead.get("research_topic"), "保险行业"),
            "published_at": lead.get("published_at"),
            "source_count": len({x.get("source_name") for x in items if x.get("source_name")}),
            "article_count": len(items),
            "article_ids": [x.get("id") for x in items if x.get("id") is not None],
            "scores": scores,
            "insight": _insight(items, scores),
        }
        events.append(event)
    events.sort(key=lambda x: (x["scores"]["intelligence_score"], x.get("published_at") or ""), reverse=True)
    today = datetime.now(timezone.utc).date()
    daily = [e for e in events if (e.get("published_at") or "").startswith(today.isoformat())]
    if len(daily) < 5:
        daily = events[:5]
    else:
        daily = daily[:5]
    return {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "principle": "发现值得行动的变化，而不是堆积更多新闻",
        "events": events,
        "daily_brief": daily,
        "stats": {
            "news_count": len(news),
            "event_count": len(events),
            "multi_source_events": sum(1 for e in events if e["source_count"] > 1),
        },
    }


def main():
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    result = build(data)
    tmp = OUTPUT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, OUTPUT_PATH)
    print(f"Intelligence engine: {result['stats']['news_count']} news -> {result['stats']['event_count']} events; daily brief={len(result['daily_brief'])}")


if __name__ == "__main__":
    main()
