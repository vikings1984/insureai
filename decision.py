#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Decision intelligence: bounded, evidence-linked action guidance."""
from __future__ import annotations

import json
from datetime import datetime, timezone
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

# P1-2 决策上下文：五个业务职能分面及其信号来源（全部为 event 已有信号的映射）。
IMPACT_FACETS = {
    "strategic": {"label": "战略", "signals": ("strategic_change",), "types": {"acquisition", "capital", "market_entry"}},
    "product": {"label": "产品", "signals": ("market_change", "technology_change"), "types": {"product", "market_entry"}},
    "underwriting": {"label": "核保", "signals": ("financial_impact",), "types": {"claims_loss", "rating", "product"}},
    "investment": {"label": "投资", "signals": ("financial_impact",), "types": {"capital", "acquisition", "rating"}},
    "compliance": {"label": "合规", "signals": ("regulatory_change",), "types": {"regulatory"}},
}
# 类型未命中时，信号分面的影响强度按 45% 折算（次要影响不得高于类型直接命中的主影响）。
SIGNAL_FACET_RATIO = 0.45
# 与 intelligence_signal.py 的"有意义信号"阈值保持一致的分面在位判定线。
FACET_PRESENT_THRESHOLD = 28

OPPORTUNITY_BY_TYPE = {
    "acquisition": "标的整合与业务协同带来的组合机会",
    "capital": "资本合作与资产负债配置窗口",
    "market_entry": "新市场/新渠道的先发布局机会",
    "product": "产品创新与定价模型迭代机会",
    "regulatory": "合规能力先行带来的信誉与准入优势",
    "claims_loss": "风险减量服务与理赔效率提升空间",
    "rating": "评级改善带来的融资与再保成本优势",
    "industry_update": "行业动向中蕴含的业务参照机会",
    "personnel": "关键人才流动带来的组织补强机会",
}

RISK_BY_TYPE = {
    "acquisition": "交易估值与整合不及预期",
    "capital": "资本占用与偿付能力压力",
    "market_entry": "新市场竞争与获客成本超预期",
    "product": "产品定价不足与逆选择风险",
    "regulatory": "合规成本上升与业务节奏受限",
    "claims_loss": "赔付恶化与准备金不足",
    "rating": "评级下调推高再保与融资成本",
    "industry_update": "行业格局变化削弱现有定位",
    "personnel": "关键岗位空缺影响业务连续性",
}

NEXT_STEP_PREFIX = {"now": "优先处理", "soon": "列入近期计划", "watch": "保持跟踪"}
CONTEXT_FIELDS = ("business_impact", "affected_functions", "potential_opportunity", "potential_risk", "what_to_monitor", "recommended_next_step")

URGENCY = {"accelerating": "now", "forming": "soon", "cooling": "watch", "isolated": "watch"}
LABELS = {"now": "高", "soon": "中", "watch": "低"}
RANK = {"watch": 0, "soon": 1, "now": 2}
CALIBRATION = Path(__file__).resolve().parent / "calibration.json"


def _now() -> str:
    """引擎产出决策的真实时间戳（UTC，秒级）。绝不伪造为用户决策时间。"""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def _business_impact(event_type: str, signals: dict, score: int) -> dict:
    """影响强度分面：类型直接命中的职能以情报分为主导，仅信号激活的按 45% 折算。"""
    scores = (signals or {}).get("scores") or {}
    facets = {}
    for facet, spec in IMPACT_FACETS.items():
        sig = max((int(scores.get(k) or 0) for k in spec["signals"]), default=0)
        base = score if event_type in spec["types"] else int(round(sig * SIGNAL_FACET_RATIO))
        facets[facet] = min(100, base)
    return facets


def _affected_functions(impact: dict) -> list[dict]:
    present = [(f, v) for f, v in impact.items() if v >= FACET_PRESENT_THRESHOLD]
    if not present:
        # 类型未命中且信号偏弱时，取最高分面作为唯一参照，不凭空补职能。
        top = max(impact.items(), key=lambda kv: kv[1]) if any(impact.values()) else None
        present = [top] if top and top[1] > 0 else []
    return [{"function": f, "label": IMPACT_FACETS[f]["label"], "impact": v} for f, v in sorted(present, key=lambda kv: -kv[1])]


def _potential_risk(event_type: str, evidence_status: str, conflict: bool, trust: str) -> list[str]:
    risks = [RISK_BY_TYPE.get(event_type, "行业信号变化带来的不确定性")]
    if evidence_status == "single_source":
        risks.append("单一来源，结论待独立证据确认")
    if conflict:
        risks.append("证据存在冲突，结论尚未收敛")
    if trust == "low":
        risks.append("来源可信度低，行动前需复核")
    return risks


def context_coverage(decisions: list[dict]) -> float:
    """六要素齐备率：business_impact / affected_functions / opportunity / risk / monitor / next_step 任一为空即不齐备。"""
    if not decisions:
        return 0.0
    complete = sum(1 for row in decisions if all((row.get("context") or {}).get(f) for f in CONTEXT_FIELDS))
    return round(complete / len(decisions), 4)


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

        insight = event.get("insight") or {}
        impact = _business_impact(event_type, insight.get("signals") or {}, score)
        prefix = NEXT_STEP_PREFIX[urgency]
        # 默认兜底动作（"保持跟踪，…"）本身已含时限语义时不再叠加前缀。
        step = action if action.startswith(prefix) else prefix + "：" + action
        context = {
            "business_impact": impact,
            "affected_functions": _affected_functions(impact),
            "potential_opportunity": [OPPORTUNITY_BY_TYPE.get(event_type, "行业信号中的业务参照机会")],
            "potential_risk": _potential_risk(event_type, evidence_status, conflict, trust),
            "what_to_monitor": insight.get("what_to_watch") or "",
            "recommended_next_step": step + ("（先完成人工复核）" if human_review_required else ""),
        }

        out.append({
            "event_id": event.get("event_id"),
            "role": role,
            "decided_at": _now(),
            "action": action,
            "urgency": urgency,
            "urgency_label": LABELS[urgency],
            "human_review_required": human_review_required,
            "context": context,
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
