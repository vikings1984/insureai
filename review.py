#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Human-in-the-loop review queue for InsureAI intelligence.

第一性原理：人工精力应该优先花在模型最不确定、最可能造成错误决策的样本上。
该模块只生成可复核队列，不自动改变生产结论。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent
INTEL = ROOT / "intelligence.json"
QUEUE = ROOT / "review_queue.json"

REVIEW_TYPES = {
    "event_cluster": "事件聚类可疑：可能存在误合并或漏合并",
    "evidence": "证据不足：关键 Claim 缺少独立来源支持",
    "conflict": "事实冲突：不同来源存在数字/实体冲突",
    "trend": "趋势可疑：趋势信号样本不足或可信度偏低",
    "decision": "决策建议可疑：行动级别与证据强度不匹配",
}


def _priority(item: dict) -> int:
    score = int(item.get("scores", {}).get("intelligence_score") or 0)
    trust = (item.get("trust") or {}).get("level", "low")
    priority = 20
    if score >= 85:
        priority += 20
    if trust == "low":
        priority += 25
    elif trust == "medium":
        priority += 10
    if (item.get("trust") or {}).get("conflict"):
        priority += 30
    claims = item.get("claims") or {}
    coverage = float(claims.get("coverage") or 0)
    if coverage < 80:
        priority += 20
    if (item.get("decision") or {}).get("urgency") == "now" and trust != "high":
        priority += 30
    return min(priority, 100)


def _candidate_reasons(event: dict) -> list[dict]:
    reasons = []
    trust = event.get("trust") or {}
    claims = event.get("claims") or {}
    decision = event.get("decision") or {}
    scores = event.get("scores") or {}
    if trust.get("conflict"):
        reasons.append({"type": "conflict", "reason": "trust layer detected source conflict"})
    if float(claims.get("coverage") or 0) < 80:
        reasons.append({"type": "evidence", "reason": f"claim evidence coverage={claims.get('coverage', 0)}"})
    if trust.get("level") == "low" and int(scores.get("intelligence_score") or 0) >= 80:
        reasons.append({"type": "evidence", "reason": "high-value event has low trust"})
    if decision.get("urgency") == "now" and trust.get("level") != "high":
        reasons.append({"type": "decision", "reason": "now recommendation without high trust"})
    temporal = event.get("temporal") or {}
    if temporal and temporal.get("phase") in {"accelerating", "forming"} and temporal.get("current_period_count", 0) < 3:
        reasons.append({"type": "trend", "reason": "trend phase has fewer than 3 current-period events"})
    if int(event.get("article_count") or 0) == 1:
        reasons.append({"type": "event_cluster", "reason": "single-article event; cluster boundary should be reviewed for high-impact cases"})
    return reasons


def build_review_queue(data: dict) -> dict:
    candidates = []
    for event in data.get("events", []) if isinstance(data.get("events"), list) else []:
        reasons = _candidate_reasons(event)
        if not reasons:
            continue
        candidates.append({
            "event_id": event.get("event_id"),
            "title": event.get("title"),
            "priority": _priority(event),
            "status": "pending",
            "reasons": reasons[:5],
            "article_ids": event.get("article_ids", []),
            "source_count": event.get("source_count", 0),
            "trust_level": (event.get("trust") or {}).get("level", "low"),
            "intelligence_score": (event.get("scores") or {}).get("intelligence_score", 0),
        })
    candidates.sort(key=lambda x: (x["priority"], x.get("intelligence_score", 0)), reverse=True)
    return {
        "version": 1,
        "principle": "人工复核优先处理不确定性高且潜在影响大的样本",
        "generated_count": len(candidates),
        "items": candidates[:100],
    }


def write_queue(data: dict) -> dict:
    queue = build_review_queue(data)
    QUEUE.write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return queue


def main() -> None:
    data = json.loads(INTEL.read_text(encoding="utf-8"))
    queue = write_queue(data)
    print(f"Review queue generated: {len(queue['items'])} pending candidates")


if __name__ == "__main__":
    main()
