#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Summarize decision credibility without depending on a future release artifact."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _load(name: str, default):
    path = ROOT / name
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _source(name: str, value: dict) -> dict:
    return {
        "source": name,
        "available": bool(value),
        "source_commit": value.get("source_commit") if isinstance(value, dict) else None,
    }


def _reason(code: str, severity: str, message: str, signal: str, actual, threshold) -> dict:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "signal": signal,
        "actual": actual,
        "threshold": threshold,
    }


def build_credibility() -> dict:
    # release_manifest is produced later in the pipeline. It is therefore optional
    # here; a missing file must never be interpreted as a failed quality gate.
    release = _load("release_manifest.json", {})
    stability = _load("decision_stability.json", {})
    availability = _load("evidence_availability.json", {})

    stability_rows = stability.get("results") or []
    jitter = sum(1 for row in stability_rows if row.get("status") == "jitter")
    unstable = sum(1 for row in stability_rows if row.get("status") in {"jitter", "changed"})
    availability_rows = availability.get("results") or availability.get("items") or []
    low_availability = sum(
        1 for row in availability_rows
        if row.get("availability") in {"low", "unavailable"}
    )

    release_available = bool(release)
    quality_status = release.get("quality_status") if release_available else "unknown"
    deployment_status = release.get("deployment_status") if release_available else "unknown"
    deployment_verified = bool(release.get("deployment_verified", False)) if release_available else False

    reasons = []
    if release_available and quality_status != "passed":
        reasons.append(
            _reason(
                "quality_not_passed",
                "blocked",
                "已存在的发布质量门禁未通过，不能把当前决策视为可发布。",
                "quality_status",
                quality_status,
                "passed",
            )
        )
    elif not release_available:
        reasons.append(
            _reason(
                "release_manifest_unavailable",
                "review",
                "可信度计算发生在发布清单生成之前，当前没有可用于部署验收的 release manifest。",
                "release_manifest_available",
                False,
                True,
            )
        )

    if deployment_status not in {"verified", "pending"}:
        reasons.append(
            _reason(
                "deployment_state_unavailable",
                "review",
                "当前运行尚未提供可验证的生产部署状态。",
                "deployment_status",
                deployment_status,
                ["verified", "pending"],
            )
        )
    elif not deployment_verified:
        reasons.append(
            _reason(
                "deployment_not_verified",
                "review",
                "质量通过不等于生产部署已经验收；当前发布身份尚未得到线上验证。",
                "deployment_verified",
                deployment_verified,
                True,
            )
        )

    if jitter > 0:
        reasons.append(
            _reason(
                "decision_jitter_detected",
                "review",
                "决策稳定性检测发现 jitter，需要人工复核受影响判断。",
                "decision_jitter_events",
                jitter,
                0,
            )
        )
    if low_availability > 0:
        reasons.append(
            _reason(
                "low_or_unavailable_evidence",
                "review",
                "存在低可用或不可用证据，相关判断不应自动升级为确定结论。",
                "low_or_unavailable_evidence",
                low_availability,
                0,
            )
        )

    blocking = any(r["severity"] == "blocked" for r in reasons)
    if blocking:
        status = "blocked"
    elif any(r["severity"] == "review" for r in reasons):
        status = "review"
    elif any(r["severity"] == "caution" for r in reasons):
        status = "caution"
    else:
        status = "ready"

    generated_at = datetime.now(timezone.utc).isoformat()
    signal_details = [
        {
            "signal": "quality_status",
            "actual": quality_status,
            "comparator": "==",
            "threshold": "passed",
            "result": quality_status == "passed",
            "source": "release_manifest.json",
            "source_available": release_available,
        },
        {
            "signal": "deployment_status",
            "actual": deployment_status,
            "comparator": "in",
            "threshold": ["verified", "pending"],
            "result": deployment_status in {"verified", "pending"},
            "source": "release_manifest.json",
            "source_available": release_available,
        },
        {
            "signal": "decision_jitter_events",
            "actual": jitter,
            "comparator": ">",
            "threshold": 0,
            "result": jitter == 0,
            "source": "decision_stability.json",
        },
        {
            "signal": "low_or_unavailable_evidence",
            "actual": low_availability,
            "comparator": ">",
            "threshold": 0,
            "result": low_availability == 0,
            "source": "evidence_availability.json",
        },
        {
            "signal": "release_manifest_available",
            "actual": release_available,
            "comparator": "==",
            "threshold": True,
            "result": release_available,
            "source": "release_manifest.json",
        },
    ]

    return {
        "version": 3,
        "status": status,
        "principle": "可信度摘要只汇总当前阶段已经存在的质量信号，不读取未来阶段的产物作为失败依据；任何降级均给出可审计原因。",
        "quality": {"status": quality_status},
        "deployment": {"status": deployment_status, "verified": deployment_verified},
        "stability": {
            "jitter_events": jitter,
            "unstable_events": unstable,
            "signal": "stable" if jitter == 0 else "review",
        },
        "evidence": {
            "low_or_unavailable": low_availability,
            "signal": "sufficient" if low_availability == 0 else "review",
        },
        "provenance": {
            "generated_at": generated_at,
            "quality": _source("release_manifest.json", release),
            "stability": _source("decision_stability.json", stability),
            "evidence": _source("evidence_availability.json", availability),
            "auditability": "missing_future_stage_inputs_are_explicit_and_non_blocking",
        },
        "signal_details": signal_details,
        "reasons": reasons,
        "reason_codes": [r["code"] for r in reasons],
        "guardrail": "该摘要不替代承保、投资、合规或管理决策。",
    }


def main() -> None:
    output = build_credibility()
    (ROOT / "decision_credibility.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "Decision credibility:",
        output["status"],
        "reasons:",
        ",".join(output["reason_codes"]) or "none",
    )


if __name__ == "__main__":
    main()
