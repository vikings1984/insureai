#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Turn robust decision-matrix actions into explicit, auditable triggers.

第一性原理：行动不是一句建议；必须有触发证据、升级条件、降级条件、责任角色和
可停止条件。触发器只提供观察与决策提示，不自动执行业务动作。
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MATRIX_PATH = ROOT / "scenario_matrix.json"
TEMPORAL_PATH = ROOT / "intelligence.json"
OUTPUT = ROOT / "action_triggers.json"

ROLES = ("executive", "product", "underwriting", "actuarial", "investment", "technology", "claims", "distribution")

TRIGGER_DEFS = {
    "evidence_refresh": {
        "owner_roles": ROLES,
        "start": "当前即开始持续监测，不等待单一预测成立。",
        "escalate": "新增至少 2 个独立来源，且至少 1 个高可信来源确认同一方向。",
        "deescalate": "连续两个周期没有新增独立证据，且主题信号转为 cooling/isolated。",
        "stop": "事件被证实为错误、撤回或与业务范围无关。",
    },
    "exposure_mapping": {
        "owner_roles": ROLES,
        "start": "当前证据已足以识别可能受影响的业务环节。",
        "escalate": "出现明确的监管、资本、产品、理赔或竞争影响证据。",
        "deescalate": "新增证据连续两个周期不再扩大影响范围。",
        "stop": "证据链显示实际影响不成立。",
    },
    "trigger_thresholds": {
        "owner_roles": ("executive", "product", "underwriting", "actuarial", "investment", "technology", "claims", "distribution"),
        "start": "建立升级/降级阈值并记录负责人。",
        "escalate": "核心指标同时满足：高可信 + accelerating/forming + 至少 3 个当前周期事件。",
        "deescalate": "核心指标转为 cooling，或证据可信度下降到 low。",
        "stop": "阈值不再适用于当前事件范围。",
    },
}


def build_triggers(matrix: dict, intelligence: dict | None = None) -> dict:
    results = []
    for row in (matrix or {}).get("results", []):
        event_id = str(row.get("event_id") or "")
        scenarios = [str(x) for x in row.get("scenarios", []) if x]
        if not event_id or len(scenarios) < 2:
            continue
        for action in row.get("robust_actions", []):
            action_id = action.get("action_id")
            definition = TRIGGER_DEFS.get(action_id)
            if not definition:
                continue
            results.append({
                "event_id": event_id,
                "action_id": action_id,
                "action_label": action.get("label"),
                "scenario_count": len(scenarios),
                "scenarios": scenarios,
                "owner_roles": list(definition["owner_roles"]),
                "trigger": {
                    "start": definition["start"],
                    "escalate": definition["escalate"],
                    "deescalate": definition["deescalate"],
                    "stop": definition["stop"],
                },
                "status": "monitor",
                "automation": "advisory_only",
                "guardrail": "触发器只生成观察/复核提示，不自动执行承保、投资、合规或经营动作。",
            })
    return {
        "version": 1,
        "principle": "把稳健行动转化为可观察、可升级、可降级、可停止的触发规则。",
        "trigger_count": len(results),
        "results": results[:1000],
    }


def main() -> None:
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    intelligence = None
    if TEMPORAL_PATH.exists():
        try:
            intelligence = json.loads(TEMPORAL_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            intelligence = None
    result = build_triggers(matrix, intelligence)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Action triggers: {result['trigger_count']} advisory triggers")


if __name__ == "__main__":
    main()
