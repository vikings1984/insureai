#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Decision intelligence: bounded, evidence-linked action guidance."""
from __future__ import annotations

ROLE_ACTIONS = {
    "executive": {"acquisition": "评估战略与资本影响", "regulatory": "检查监管暴露与经营影响", "capital": "复核资本配置与竞争格局", "market_entry": "评估市场与竞争响应"},
    "product": {"product": "评估产品机会、条款与定价影响", "regulatory": "检查产品合规与审批路径", "market_entry": "评估竞争产品与渠道响应"},
    "underwriting": {"claims_loss": "复核风险假设、核保规则与损失暴露", "rating": "复核风险评级与承保边界", "regulatory": "检查核保规则的监管影响"},
    "actuarial": {"claims_loss": "复核损失趋势、赔付假设与定价影响", "rating": "复核风险分层与资本假设", "capital": "评估资本与偿付能力影响", "catastrophe": "复核巨灾假设与风险敞口"},
    "investment": {"capital": "评估资本流向与投资影响", "acquisition": "关注交易估值与资本结构", "rating": "复核信用风险变化", "regulatory": "检查监管约束对资产配置的影响"},
    "technology": {"product": "评估技术能力与系统优先级", "market_entry": "评估数字渠道和技术竞争变化", "regulatory": "检查数据、AI 与系统治理影响"},
    "claims": {"claims_loss": "复核理赔流程、损失趋势与资源配置", "product": "检查理赔条款与客户体验影响", "regulatory": "检查理赔合规要求"},
    "distribution": {"market_entry": "评估渠道竞争与客户触达变化", "product": "评估产品渠道适配", "regulatory": "检查销售与分销合规影响"},
}

URGENCY = {"accelerating": "now", "forming": "soon", "cooling": "watch", "isolated": "watch"}
LABELS = {"now": "高", "soon": "中", "watch": "低"}


def build_decisions(events: list[dict], temporal: dict | None = None, role: str = "executive") -> list[dict]:
    temporal = temporal or {}
    topic_phase = {x.get("topic"): x for x in temporal.get("topic_signals", [])}
    actions = ROLE_ACTIONS.get(role, ROLE_ACTIONS["executive"])
    out = []
    for event in events:
        score = int(event.get("scores", {}).get("intelligence_score") or 0)
        trust = event.get("trust", {}).get("level", "low")
        conflict = bool(event.get("trust", {}).get("conflict"))
        phase_row = topic_phase.get(event.get("topic")) or {}
        phase = phase_row.get("phase", "isolated")
        action = actions.get(event.get("event_type")) or "保持跟踪，等待更多独立证据或业务信号"

        # Safety rule: any unresolved source conflict or low trust must never escalate
        # to an action-taking urgency, even when score/trend is otherwise strong.
        if conflict or trust == "low":
            urgency = "watch"
        elif score >= 82 and trust == "high" and phase == "accelerating":
            urgency = "now"
        elif score >= 75 and trust in {"high", "medium"} and phase in {"accelerating", "forming"}:
            urgency = URGENCY.get(phase, "watch")
        else:
            urgency = URGENCY.get(phase, "watch")

        out.append({
            "event_id": event.get("event_id"),
            "role": role,
            "action": action,
            "urgency": urgency,
            "urgency_label": LABELS[urgency],
            "basis": {"intelligence_score": score, "trust_level": trust, "temporal_phase": phase, "signal_strength": phase_row.get("signal_strength", 0), "conflict": conflict},
            "guardrail": "这是情报辅助建议，不替代承保、投资、合规或管理决策。",
        })
    rank = {"watch": 0, "soon": 1, "now": 2}
    return sorted(out, key=lambda x: (rank[x["urgency"]], x["basis"]["intelligence_score"]), reverse=True)
