#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Canonical signal extraction for InsureAI.

The signal layer is intentionally deterministic: it explains *why* an article
looks important without pretending that keyword hits are a complete semantic
understanding. Generators can use it as a transparent pre-model feature set.
"""
from __future__ import annotations

import re

SIGNAL_TYPES = (
    "strategic_change",
    "regulatory_change",
    "market_change",
    "technology_change",
    "financial_impact",
)

SIGNAL_KEYWORDS = {
    "strategic_change": {
        "acquisition", "acquire", "merger", "buy", "expand", "exit", "enter",
        "收购", "并购", "合并", "扩张", "退出", "进入", "战略", "重组",
    },
    "regulatory_change": {
        "regulation", "regulator", "rule", "compliance", "fine", "policy",
        "监管", "法规", "政策", "办法", "指引", "处罚", "合规", "三审",
    },
    "market_change": {
        "market", "premium", "demand", "launch", "distribution", "broker",
        "市场", "保费", "需求", "产品", "渠道", "经纪", "竞争", "份额",
    },
    "technology_change": {
        "ai", "artificial", "intelligence", "agent", "automation", "insurtech",
        "digital", "cloud", "data", "cyber", "人工智能", "大模型", "智能体", "保险科技",
        "数字化", "云", "数据", "网络安全", "科技",
    },
    "financial_impact": {
        "capital", "investment", "funding", "rating", "solvency", "loss", "claim",
        "资本", "投资", "融资", "评级", "偿付能力", "损失", "理赔", "赔付", "收益",
    },
}

ACTION_WORDS = {
    "launch", "unveil", "acquire", "buy", "merge", "expand", "enter", "exit",
    "raise", "invest", "upgrade", "downgrade", "approve", "fine",
    "发布", "推出", "收购", "并购", "扩张", "进入", "退出", "融资", "投资", "升级", "下调", "获批", "处罚",
}


def _norm(text: str) -> str:
    text = (text or "").lower()
    return re.sub(r"[^\w\u4e00-\u9fff]+", " ", text, flags=re.UNICODE)


def extract_signals(title: str, summary: str = "", *, topic: str | None = None) -> dict:
    text = _norm(f"{title} {summary}")
    scores: dict[str, int] = {}
    matched: dict[str, list[str]] = {}
    for signal_type, keywords in SIGNAL_KEYWORDS.items():
        hits = sorted({kw for kw in keywords if kw in text})
        score = min(100, len(hits) * 14 + (8 if topic and signal_type.replace("_change", "") in topic else 0))
        scores[signal_type] = score
        matched[signal_type] = hits[:12]

    actionability = min(100, len([x for x in ACTION_WORDS if x in text]) * 15)
    strongest = max(scores, key=scores.get) if scores else "market_change"
    strength = scores.get(strongest, 0)
    confidence = min(100, 45 + sum(1 for x in scores.values() if x >= 28) * 10)

    return {
        "primary": strongest,
        "strength": strength,
        "confidence": confidence,
        "actionability": actionability,
        "scores": scores,
        "matched_keywords": matched,
    }


__all__ = ["SIGNAL_TYPES", "extract_signals"]
