#!/usr/bin/env python3
"""Build a management-level daily intelligence terminal without release-cycle coupling."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "executive_terminal.json"

# P1-4 复核状态机的全部合法状态（用于分布展示，缺失状态补 0）
REVIEW_STATUSES = (
    "pending", "assigned", "in_review", "approved",
    "rejected", "escalated", "deferred", "resolved",
)
STATUS_LABELS = {
    "pending": "待复核",
    "assigned": "已分派",
    "in_review": "复核中",
    "approved": "已通过",
    "rejected": "已驳回",
    "escalated": "已升级",
    "deferred": "已挂起",
    "resolved": "已归档",
}
HEALTH_LABELS = {"healthy": "健康", "degraded": "降级", "critical": "严重", "unavailable": "无数据"}
SEVERITY_LABELS = {"critical": "严重", "warning": "警告", "info": "提示"}


def load(name: str, default):
    path = ROOT / name
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def main() -> None:
    intelligence = load("intelligence.json", {})
    claims = load("claims.json", {})
    review = load("review_queue.json", {})
    risk = load("daily_risk_radar.json", {})
    credibility = load("decision_credibility.json", {})
    deployment = load("deployment_verification.json", {})
    # P1-8 / P1-7 / P1-4：可观测性、DAG 执行报告、复核状态机
    observability = load("observability.json", {})
    dag_run = load("dag_run.json", {})
    review_state = load("review_state.json", {})

    events = intelligence.get("events") or []
    trends = (intelligence.get("radar") or {}).get("topic_trends") or []
    rising = [x for x in trends if x.get("direction") == "rising"]
    attention = [x for x in (risk.get("items") or risk.get("signals") or []) if isinstance(x, dict)]
    reviews = review.get("items") or review.get("queue") or []

    def score_event(event: dict) -> float:
        return float(event.get("importance", event.get("score", 0)) or 0) + (15 if event.get("review_required") else 0)

    priority_events = sorted(events, key=score_event, reverse=True)[:8]
    avg_coverage = sum(float(e.get("evidence_coverage", 0) or 0) for e in events) / len(events) if events else 0
    deployment_status = deployment.get("status", "unknown")

    def build_health() -> dict:
        """P1-8：系统健康度。artifact 缺失时降级 unavailable，不臆造结论。"""
        overall = observability.get("overall") or {}
        raw_alerts = observability.get("alerts") or []
        return {
            "available": bool(overall),
            "status": overall.get("status") or "unavailable",
            "status_label": HEALTH_LABELS.get(overall.get("status"), overall.get("status") or "无数据"),
            "score": overall.get("score"),
            "critical_count": int(overall.get("critical_count", 0) or 0),
            "warning_count": int(overall.get("warning_count", 0) or 0),
            "reasons": list(overall.get("reasons") or []),
            "alerts": [
                {
                    "severity": a.get("severity") or "info",
                    "severity_label": SEVERITY_LABELS.get(a.get("severity"), a.get("severity") or "提示"),
                    "code": a.get("code"),
                    "message": a.get("message"),
                }
                for a in raw_alerts
                if isinstance(a, dict)
            ],
            "generated_at": observability.get("generated_at"),
        }

    def build_pipeline() -> dict:
        """P1-7：DAG 执行报告。只汇总已有节点事实，不重算状态。"""
        nodes = [n for n in (dag_run.get("nodes") or []) if isinstance(n, dict)]
        failed = [n for n in nodes if n.get("status") == "failed"]
        ranked = sorted(nodes, key=lambda n: float(n.get("duration_sec") or 0), reverse=True)
        return {
            "available": bool(nodes),
            "ok": dag_run.get("ok"),
            "run_at": dag_run.get("run_at"),
            "node_count": len(nodes),
            "ok_count": sum(1 for n in nodes if n.get("status") == "ok"),
            "failed_count": len(failed),
            "failed_nodes": [
                {"id": n.get("id"), "name": n.get("name"), "exit_code": n.get("exit_code")}
                for n in failed
            ],
            "slowest_nodes": [
                {"id": n.get("id"), "name": n.get("name"), "duration_sec": n.get("duration_sec")}
                for n in ranked[:5]
                if float(n.get("duration_sec") or 0) > 0
            ],
        }

    def build_review_progress() -> dict:
        """P1-4：复核状态分布。状态机是每日继承的，故这里反映真实人工进展。"""
        items = review_state.get("items") or {}
        distribution = {}
        for status in REVIEW_STATUSES:
            count = sum(1 for rec in items.values() if isinstance(rec, dict) and rec.get("status") == status)
            if count:
                distribution[status] = count
        unknown = sum(
            1 for rec in items.values()
            if isinstance(rec, dict) and rec.get("status") not in REVIEW_STATUSES
        )
        if unknown:
            distribution["unknown"] = unknown
        return {
            "available": bool(items),
            "tracked": len(items),
            "queue_size": len(reviews),
            "distribution": [
                {
                    "status": status,
                    "label": STATUS_LABELS.get(status, status),
                    "count": distribution[status],
                }
                for status in REVIEW_STATUSES
                if status in distribution
            ] + ([{"status": "unknown", "label": "未知状态", "count": unknown}] if unknown else []),
        }

    health = build_health()
    pipeline = build_pipeline()
    review_progress = build_review_progress()

    output = {
        "version": 4,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": os.environ.get("GITHUB_SHA", "unknown"),
        "summary": {
            "event_count": len(events),
            "rising_topics": len(rising),
            "review_queue": len(reviews),
            "attention_signals": len(attention),
            "avg_evidence_coverage": round(avg_coverage, 1),
            "system_status": health["status_label"],
            "pipeline_status": "未运行" if not pipeline["available"]
            else ("正常" if pipeline["ok"] else "有失败节点"),
            "cross_checked_claims": int(claims.get("cross_checked_claim_count", 0) or 0),
            "single_source_claims": int(claims.get("single_source_claim_count", 0) or 0),
            "credibility_status": credibility.get("status", "unknown"),
            "deployment_status": deployment_status,
        },
        "what_changed": [
            {
                "title": e.get("topic") or e.get("title") or "未命名事件",
                "why": e.get("insight") or e.get("summary"),
                "event_id": e.get("event_id"),
                "trust": e.get("trust"),
                "evidence_coverage": e.get("evidence_coverage"),
                "review_required": bool(e.get("review_required", False)),
            }
            for e in priority_events
        ],
        "what_is_accelerating": rising[:8],
        "what_needs_attention": attention[:8],
        "what_needs_human_decision": reviews[:8],
        "system_health": health,
        "pipeline": pipeline,
        "review_progress": review_progress,
        "release": {
            "deployment_status": deployment_status,
            "deployment_verified": bool(deployment.get("verified", False)),
            "release_marker": deployment.get("release_marker"),
            "release_match": deployment.get("marker_found") is True,
        },
        "artifact_sources": [
            "intelligence.json",
            "claims.json",
            "review_queue.json",
            "daily_risk_radar.json",
            "decision_credibility.json",
            "deployment_verification.json",
            "observability.json",
            "dag_run.json",
            "review_state.json",
        ],
    }
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
