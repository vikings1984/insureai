#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Decision intelligence: bounded, evidence-linked action guidance."""
from __future__ import annotations

import json
from pathlib import Path

ROLE_ACTIONS = {
    "executive": {"acquisition": "评估战略与资本影响", "regulatory": "检查监管暴露与经营影响", "capital": "复核资本配置与竞争格局", "market_entry": "评估市场与竞争响应"},
    "product": {"product": "评估产品机会、条款与定价影响", "regulatory": "检查产品合规与审批路径", "market_entry": "评估竞争产品与渠道响应"},
    "underwriting": {"claims_loss": "复核风险假设、核保规则与损失暴露", "rating": "复核风险评级与承保边界", "regulatory": "检查核保规则的监管影响"},
    "actuarial": {"claims_loss": "复核损失趋势、赔付假设与定价影响", "rating": "复核风险分层与资本假设", "capital": "评估资本与偿付能力影响", "market_entry": "评估市场变化对假设的影响"},
    "investment": {"capital": "评估资本流向与投资影响", "acquisition": "关注交易估值与资本结构", "rating": "复核信用风险变化", "regulatory": "检查监管约束对资产配置的影响"},
    "technology": {"product": "评估技术能力与系统优先级", "market_entry": "评估数字渠道和技术竞争变化", "regulatory": "检查数据、AI 与系统治理影响"},
    "claims": {"claims_loss": "复核理赔流程、损失趋势与资源配置", "product": "检查理赔条款与客户体验影响", "regulatory": "检查理赔合规要求"},
    "distribution": {"market_entry": "评估渠道竞争与客户触达变化", "product": "评估产品渠道适配", "regulatory": "检查销售与分销合规影响"},
}

URGENCY = {"accelerating": "now", "forming": "soon", "cooling": "watch", "isolated": "watch"}
LABELS = {"now": "高", "soon": "中", "watch": "低"}
RANK = {"watch": 0, "soon": 1, "now": 2}
CALIBRATION = Path(__file__).resolve().parent / "calibration.json"


def _load_calibration() -> dict:
    if not CALIBRATION.exists():
        return {"status": "neutral", "overrides": {}}
    try:
        data = json.loads(CALIBRATION.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"status": "neutral", "overrides": {}}
    except Exception:
        return {"status": "neutral", "overrides": {}}


def _apply_calibration(urgency: str, event_type: str, calibration: dict) -> str:
    override = (calibration.get("overrides") or {}).get(event_type) or {}
    cap = override.get("max_urgency")
    if cap in RANK and RANK[urgency] > RANK[cap]:
        return cap
    return urgency


def build_decisions(events: list[dict], temporal: dict | None = None, role: str = "executive", calibration: dict | None = None) -> list[dict]:
    """Build advisory-only decisions.

    Safety rule: evidence coverage below 75, low trust, conflicts, or explicit
    review requirements can never produce an unqualified ``now`` action.
    """
    temporal = temporal or {}
    calibration = calibration if calibration is not None else _load_calibration()
    topic_phase = {x.get("topic"): x for x in temporal.get("topic_signals", [])}
    actions = ROLE_ACTIONS.get(role, ROLE_ACTIONS["executive"])
    out = []
    for event in events:
        score = int(event.get("scores", {}).get("intelligence_score") or 0)
        trust = event.get("trust", {}).get("level", "low")
        conflict = bool(event.get("trust", {}).get("conflict"))
        evidence_coverage = float(event.get("evidence_coverage", event.get("insight", {}).get("evidence_coverage", 0)) or 0)
        evidence_status = event.get("evidence_status", event.get("insight", {}).get("evidence_status", "unknown"))
        explicit_review = bool(event.get("review_required", event.get("insight", {}).get("human_review_required", False)))
        phase_row = topic_phase.get(event.get("topic")) or {}
        phase = phase_row.get("phase", "isolated")
        event_type = event.get("event_type") or "industry_update"
        action = actions.get(event_type) or "保持跟踪，等待更多独立证据或业务信号"

        low_evidence = evidence_coverage < 75 or evidence_status == "single_source"
        if conflict or trust == "low" or explicit_review or low_evidence:
            urgency = "watch"
        elif score >= 82 and trust == "high" and phase == "accelerating":
            urgency = "now"
        elif score >= 75 and trust in {"high", "medium"} and phase in {"accelerating", "forming"}:
            urgency = URGENCY.get(phase, "watch")
        else:
            urgency = URGENCY.get(phase, "watch")

        before_calibration = urgency
        urgency = _apply_calibration(urgency, event_type, calibration)
        calibration_applied = urgency != before_calibration
        human_review_required = explicit_review or low_evidence or conflict or trust != "high"

        out.append({
            "event_id": event.get("event_id"),
            "role": role,
            "action": action,
            "urgency": urgency,
            "urgency_label": LABELS[urgency],
            "human_review_required": human_review_required,
            "basis": {
                "intelligence_score": score,
                "trust_level": trust,
                "evidence_coverage": evidence_coverage,
                "evidence_status": evidence_status,
                "temporal_phase": phase,
                "signal_strength": phase_row.get("signal_strength", 0),
                "conflict": conflict,
                "pre_calibration_urgency": before_calibration,
                "calibration_applied": calibration_applied,
                "calibration_status": calibration.get("status", "neutral"),
            },
            "guardrail": "这是情报辅助建议，不替代承保、投资、合规或管理决策；任何 high-impact action 必须由人工确认。",
        })
    return sorted(out, key=lambda x: (RANK[x["urgency"]], x["basis"]["intelligence_score"]), reverse=True)
