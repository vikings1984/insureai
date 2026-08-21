#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scenario comparison and robust decision matrix for InsureAI."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCENARIO_PATH = ROOT / "scenario.json"
OUTPUT = ROOT / "scenario_matrix.json"

COMMON_ACTIONS = [
    ("evidence_refresh", "持续刷新证据", "跟踪独立来源、监管原文与新增业务信号，避免单次新闻驱动决策。"),
    ("exposure_mapping", "做影响暴露映射", "把事件可能影响的产品、客户、渠道、资本或运营环节列成清单。"),
    ("trigger_thresholds", "建立触发阈值", "预先定义哪些新增证据会让关注等级升级或降级。"),
]
SCENARIO_ACTIONS = {
    "trend_accelerates": [("capacity_review", "复核资源与能力容量"), ("resource_priority", "准备资源优先级方案")],
    "trend_cools": [("investment_gate", "设置新增投入闸门"), ("monitor_without_expansion", "保持监测但避免过早扩张")],
    "regulation_leads": [("regulatory_gap_review", "提前做监管差距分析"), ("compliance_impact_map", "建立合规影响清单")],
    "competition_follows": [("competitor_monitoring", "建立竞争对手监测"), ("response_playbook", "准备可逆的竞争响应预案")],
}

def build_matrix(data: dict) -> dict:
    scenarios = data.get("scenarios", []) if isinstance(data, dict) else []
    by_event: dict[str, list[dict]] = {}
    for row in scenarios:
        eid = str(row.get("event_id") or "")
        if eid:
            by_event.setdefault(eid, []).append(row)
    results = []
    for event_id, rows in by_event.items():
        names = sorted({r.get("scenario") for r in rows if r.get("scenario")})
        if len(names) < 2:
            continue
        robust = []
        for action_id, label, description in COMMON_ACTIONS:
            robust.append({"action_id": action_id, "label": label, "description": description, "coverage": 1.0, "robust": True, "reversibility": "high"})
        specific = []
        for name in names:
            for action_id, label in SCENARIO_ACTIONS.get(name, []):
                specific.append({"scenario": name, "action_id": action_id, "label": label, "applies": True})
        results.append({
            "event_id": event_id,
            "scenario_count": len(names),
            "scenarios": names,
            "robust_actions": robust,
            "scenario_specific_actions": specific,
            "principle": "先做跨情景稳健且可逆的动作，再等待决定性证据；不要求押注单一情景。",
            "disclaimer": "决策矩阵是情报辅助，不替代承保、投资、合规或管理决策。",
        })
    return {"version": 1, "principle": "在不确定性下最大化跨情景有效性与选择权，而不是预测唯一未来。", "event_count": len(results), "results": results[:500]}

def main() -> None:
    data = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    result = build_matrix(data)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Scenario matrix: {result['event_count']} events with multi-scenario decisions")

if __name__ == "__main__":
    main()
