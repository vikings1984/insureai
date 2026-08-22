#!/usr/bin/env python3
"""Run the real analytical/release pipeline without committing or publishing.

This intentionally mirrors the build order used by daily-collect.yml while
skipping the final git commit/push. It is the end-to-end smoke test that unit
suites cannot provide.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ANALYTICAL_STEPS = [
    [sys.executable, "intelligence.py"],
    [sys.executable, "trust_build.py"],
    [sys.executable, "temporal_build.py"],
    [sys.executable, "calibration.py"],
    [sys.executable, "decision_build.py"],
    [sys.executable, "decision_stability.py"],
    [sys.executable, "decision_credibility.py"],
    [sys.executable, "counterfactual.py"],
    [sys.executable, "scenario.py"],
    [sys.executable, "scenario_matrix.py"],
    [sys.executable, "action_triggers.py"],
    [sys.executable, "execution_readiness.py"],
    [sys.executable, "change_impact.py"],
    [sys.executable, "contract.py"],
    [sys.executable, "evaluation.py"],
    [sys.executable, "production_replay.py"],
    [sys.executable, "review.py"],
    [sys.executable, "feedback_attribution.py"],
    [sys.executable, "module_health.py"],
    [sys.executable, "module_health_trend.py"],
    [sys.executable, "trend_attribution.py"],
    [sys.executable, "optimization_backlog.py"],
    [sys.executable, "daily_risk_radar.py"],
    [sys.executable, "owner_risk_view.py"],
    [sys.executable, "prerender.py", "--site-url", os.environ.get("SITE_URL", "https://vikings1984.github.io/insureai")],
    [sys.executable, "scripts/inject_intelligence_ui.py"],
    [sys.executable, "scripts/inject_personalization_ui.py"],
    [sys.executable, "scripts/inject_trust_ui.py"],
    [sys.executable, "scripts/inject_claim_evidence_ui.py"],
    [sys.executable, "scripts/inject_temporal_ui.py"],
    [sys.executable, "scripts/inject_decision_ui.py"],
    [sys.executable, "scripts/inject_review_ui.py"],
    [sys.executable, "scripts/inject_action_triggers_ui.py"],
    [sys.executable, "scripts/inject_execution_readiness_ui.py"],
    [sys.executable, "scripts/inject_owner_risk_ui.py"],
    [sys.executable, "scripts/quality_score.py"],
]

RELEASE_STEPS = [
    [sys.executable, "release_manifest.py"],
    [sys.executable, "audit_ledger.py"],
    [sys.executable, "release_manifest.py"],
    [sys.executable, "release_provenance.py"],
]


def run_step(command: list[str]) -> None:
    label = " ".join(command[1:])
    print(f"\n=== {label} ===", flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def smoke_collect(limit: int) -> None:
    run_step([sys.executable, "collect.py", "--dry-run", "--limit", str(limit)])


def validate_release() -> None:
    import json

    manifest = json.loads((ROOT / "release_manifest.json").read_text(encoding="utf-8"))
    provenance = json.loads((ROOT / "release_provenance.json").read_text(encoding="utf-8"))
    gate = json.loads((ROOT / "production_quality_gate.json").read_text(encoding="utf-8"))
    audit = json.loads((ROOT / "audit_ledger.json").read_text(encoding="utf-8"))

    assert manifest["quality_status"] == "passed", manifest
    assert manifest["deployment_status"] == "pending", manifest
    assert gate["status"] == "passed", gate
    artifacts = {row.get("artifact") for row in audit.get("stages", [])}
    assert "production_quality_gate.json" in artifacts, artifacts
    assert provenance["quality"]["production_gate_status"] == "passed", provenance
    assert provenance["artifacts"]["production_quality_gate_sha256"], provenance
    print("\nFULL PIPELINE SMOKE: PASS")
    print(f"audit stages={len(audit.get('stages', []))} gate={gate['status']} deployment={manifest['deployment_status']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--collect-limit", type=int, default=3)
    parser.add_argument("--skip-collect", action="store_true")
    args = parser.parse_args()

    if not args.skip_collect:
        smoke_collect(args.collect_limit)
    for command in ANALYTICAL_STEPS:
        run_step(command)
    for command in RELEASE_STEPS:
        run_step(command)
    validate_release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
