#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bounded scenario intelligence: explicit assumptions, no forecast masquerading."""
from __future__ import annotations

SCENARIOS = {
    "trend_accelerates": {"label": "趋势继续加速", "watch": "同主题事件数量、独立来源与监管/资本动作继续增加"},
    "trend_cools": {"label": "趋势降温", "watch": "后续周期事件量下降、关注度回落且无新增高可信事件"},
    "regulation_leads": {"label": "监管先行", "watch": "监管文本、处罚、审批或实施细则先于商业扩张出现"},
    "competition_follows": {"label": "竞争跟随", "watch": "同类公司出现产品、并购、渠道或资本跟进行动"},
}


def _base_strength(event: dict, signal: dict | None) -> int:
    score = int(event.get("scores", {}).get("intelligence_score") or 0)
    trust = (event.get("trust") or {}).get("level", "low")
    strength = min(100, max(0, score))
    if trust == "high":
        strength += 5
    elif trust == "low":
        strength -= 10
    if signal:
        strength += min(10, int(signal.get("signal_strength") or 0) // 10)
    return min(100, max(0, strength))


def build_scenarios(data: dict) -> dict:
    events = data.get("events", []) if isinstance(data, dict) else []
    temporal = data.get("temporal") or {}
    signals = {x.get("topic"): x for x in temporal.get("topic_signals", []) if x.get("topic")}
    rows = []
    for event in events:
        signal = signals.get(event.get("topic"))
        strength = _base_strength(event, signal)
        if strength < 60:
            continue
        phase = (signal or {}).get("phase", "isolated")
        candidates = ["trend_accelerates", "trend_cools"]
        if event.get("event_type") == "regulatory":
            candidates.append("regulation_leads")
        if event.get("event_type") in {"acquisition", "product", "market_entry", "capital"}:
            candidates.append("competition_follows")
        for scenario in candidates:
            assumption = SCENARIOS[scenario]
            support = strength
            if scenario == "trend_accelerates" and phase == "accelerating":
                support += 10
            if scenario == "trend_cools" and phase == "cooling":
                support += 10
            if scenario == "regulation_leads" and event.get("event_type") == "regulatory":
                support += 8
            if scenario == "competition_follows" and event.get("event_type") in {"acquisition", "product", "market_entry", "capital"}:
                support += 6
            support = min(100, support)
            rows.append({
                "event_id": event.get("event_id"),
                "topic": event.get("topic"),
                "scenario": scenario,
                "scenario_label": assumption["label"],
                "support_level": support,
                "phase": phase,
                "assumption": assumption["watch"],
                "evidence_basis": {
                    "intelligence_score": event.get("scores", {}).get("intelligence_score", 0),
                    "trust_level": (event.get("trust") or {}).get("level", "low"),
                    "temporal_phase": phase,
                },
                "disclaimer": "场景推演不是预测；support_level 表示当前证据对该假设的支持强度，不是发生概率。",
            })
    rows.sort(key=lambda x: x["support_level"], reverse=True)
    return {
        "version": 1,
        "principle": "只在已有证据基础上构造显式假设，不把情景支持度冒充预测概率。",
        "scenario_count": len(rows),
        "scenarios": rows[:500],
    }


if __name__ == "__main__":
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parent
    data = json.loads((root / "intelligence.json").read_text(encoding="utf-8"))
    # intelligence.json contains nested outputs; be tolerant of missing temporal in older data.
    out = build_scenarios(data)
    (root / "scenario.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Scenario intelligence: {len(out['scenarios'])} scenarios")
