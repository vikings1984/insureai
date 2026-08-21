#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Turn advisory action triggers into execution-ready decision packs.

The module does not execute actions. It specifies inputs, owner, deadline,
cost class, approval boundary, and readiness status so a human can act safely.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TRIGGERS = ROOT / "action_triggers.json"
OUTPUT = ROOT / "execution_readiness.json"

PACKS = {
    "evidence_refresh": {
        "required_inputs": ["independent_sources", "primary_regulatory_or_company_sources", "latest_event_timeline"],
        "deliverables": ["source_digest", "claim_delta", "confidence_change"],
        "deadline": "next_review_cycle",
        "cost_class": "low",
        "approval_boundary": "no_business_execution; human review only",
    },
    "exposure_mapping": {
        "required_inputs": ["affected_products", "customer_segments", "channels", "capital_or_operational_exposure"],
        "deliverables": ["impact_map", "affected_owner_list", "open_questions"],
        "deadline": "within_5_business_days",
        "cost_class": "low",
        "approval_boundary": "analysis only; human review; no policy or portfolio change",
    },
    "trigger_thresholds": {
        "required_inputs": ["metric_definition", "baseline", "escalation_threshold", "deescalation_threshold"],
        "deliverables": ["threshold_register", "owner_assignment", "review_cadence"],
        "deadline": "next_governance_cycle",
        "cost_class": "low",
        "approval_boundary": "threshold proposal only; human approval required before operational use",
    },
}


def build_readiness(data: dict) -> dict:
    results = []
    for row in (data or {}).get("results", []):
        action_id = row.get("action_id")
        pack = PACKS.get(action_id)
        if not pack:
            continue
        results.append({
            "event_id": row.get("event_id"),
            "action_id": action_id,
            "action_label": row.get("action_label"),
            "status": "ready_for_human_review",
            "scenario_count": row.get("scenario_count", 0),
            "owner_roles": row.get("owner_roles", []),
            "required_inputs": pack["required_inputs"],
            "deliverables": pack["deliverables"],
            "deadline": pack["deadline"],
            "cost_class": pack["cost_class"],
            "approval_boundary": pack["approval_boundary"],
            "trigger": row.get("trigger", {}),
            "automation": "advisory_only",
            "readiness_gate": "human_confirmation_required",
        })
    return {
        "version": 1,
        "principle": "把情报动作变成可审查的决策包，而不是自动执行命令。",
        "pack_count": len(results),
        "results": results[:1000],
    }


def main() -> None:
    data = json.loads(TRIGGERS.read_text(encoding="utf-8"))
    result = build_readiness(data)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Execution readiness: {result['pack_count']} decision packs")


if __name__ == "__main__":
    main()
