#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local-first personal intelligence ranking for InsureAI.

No account system and no server-side user data: preferences stay in browser localStorage.
"""
from __future__ import annotations

PROFILE_VERSION = 1
ROLE_LABELS = {
    "executive": "管理层 / 高管", "product": "产品", "underwriting": "核保",
    "actuarial": "精算", "investment": "投资 / 资管", "technology": "科技 / 数字化",
    "claims": "理赔", "distribution": "渠道",
}


def normalize_profile(profile: dict | None) -> dict:
    profile = profile if isinstance(profile, dict) else {}
    role = profile.get("role") if profile.get("role") in ROLE_LABELS else "executive"
    topics = profile.get("topics") if isinstance(profile.get("topics"), list) else []
    entities = profile.get("entities") if isinstance(profile.get("entities"), list) else []
    return {"version": PROFILE_VERSION, "role": role, "topics": [str(x).strip().lower() for x in topics if str(x).strip()][:8], "entities": [str(x).strip().lower() for x in entities if str(x).strip()][:12]}


def personalize_event(event: dict, profile: dict | None) -> dict:
    p = normalize_profile(profile)
    score = float(event.get("scores", {}).get("intelligence_score") or 0)
    topic = str(event.get("topic") or "").lower()
    entities = {str(x).strip().lower() for x in event.get("entities") or []}
    topic_hit = topic in set(p["topics"])
    entity_hits = entities.intersection(p["entities"])
    role_event_types = {
        "executive": {"acquisition", "capital", "regulatory", "market_entry"},
        "product": {"product", "market_entry", "regulatory"},
        "underwriting": {"rating", "claims_loss", "product", "regulatory"},
        "actuarial": {"claims_loss", "rating", "capital", "catastrophe"},
        "investment": {"capital", "acquisition", "rating", "regulatory"},
        "technology": {"product", "market_entry", "regulatory"},
        "claims": {"claims_loss", "product", "regulatory"},
        "distribution": {"market_entry", "product"},
    }
    boost = 8 if event.get("event_type") in role_event_types.get(p["role"], set()) else 0
    boost += 10 if topic_hit else 0
    boost += min(18, len(entity_hits) * 9)
    return {"personal_score": round(min(100, score + boost)), "topic_match": topic_hit, "entity_matches": sorted(entity_hits), "role_match": boost > 0}


def personalize(events: list[dict], profile: dict | None) -> list[dict]:
    out = []
    for event in events:
        item = dict(event)
        item["personalization"] = personalize_event(event, profile)
        out.append(item)
    out.sort(key=lambda x: (x["personalization"]["personal_score"], x.get("scores", {}).get("intelligence_score", 0), x.get("published_at") or ""), reverse=True)
    return out
