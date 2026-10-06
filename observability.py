#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P1-8 Observability Dashboard：把分散在各处的生产指标统一收敛为一张健康快照（零依赖）。

此前系统的指标散落在至少 6 处产物里，要看清"今天生产到底健康不健康"需要人工翻文件：

    quality/index.json     质量档案（P0-6）
    dag_run.json           流水线逐节点状态/耗时（P1-7）
    run.json               本次 run 的 commit / 状态
    data.json              每个信源的 Source Health 六项指标（P1-2）
    module_health.json     各模块健康度
    review_queue.json / review_state.json  人工复核积压与状态分布（P1-4）

本模块把它们收敛为一份 ``observability.json``：

    overall.status   healthy / degraded / critical
    overall.score    1.0 起扣（critical 每项 -0.4，warning 每项 -0.1，下限 0.0）
    sections         分域明细（quality / pipeline / run / sources / modules / review）
    alerts           带 severity + code + message 的告警列表

设计原则：
- **只读聚合**：不修改任何源产物，不写业务判断，不阻断流水线。
- **容错**：任一源文件缺失/损坏只让对应 section 降级为 unavailable，并在 alerts 中
  记一条 warning，绝不让整个可观测性构建失败（观测自身不该成为故障源）。
- 阈值集中为模块级常量，便于调整。

用法::

    python3 observability.py                  # 生成 observability.json 并打印摘要
    python3 observability.py --json           # 结果输出到 stdout
    python3 observability.py --fail-on-critical   # 存在 critical 时 exit 1（可作 CI 门）
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(HERE, "observability.json")

VERSION = "1.0"

# —— 阈值（集中在此，便于调整）——
MACRO_QUALITY_MIN = 0.95
SOURCE_AVAILABILITY_MIN = 0.5
SOURCE_FRESHNESS_MIN = 0.2
MODULE_ERROR_RATE_MAX = 0.2
REVIEW_BACKLOG_MAX = 50
SLOW_NODE_SEC = 60.0

SEVERITY_CRITICAL = "critical"
SEVERITY_WARNING = "warning"


def _read_json(name: str):
    """读取根目录 json；缺失/损坏返回 None（观测自身不因单文件失败而崩）。"""
    path = os.path.join(HERE, name)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError, ValueError):
        return None


def _commit_sha() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE,
                             capture_output=True, text=True)
        if out.returncode == 0:
            return out.stdout.strip()[:12]
    except Exception:
        pass
    return "unknown"


def _f(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def section_quality(alerts: list[dict]) -> dict:
    """质量域：来自 P0-6 Quality Registry 的最新档案 + 历史档案数。"""
    latest = _read_json("quality/latest.json")
    index = _read_json("quality/index.json") or []
    if not isinstance(index, list):
        index = []
    if not latest:
        alerts.append({
            "severity": SEVERITY_WARNING, "code": "QUALITY_UNAVAILABLE",
            "message": "未找到质量档案（quality/latest.json），请先运行 benchmark.py",
        })
        return {"status": "unavailable", "records": len(index)}

    metrics = latest.get("metrics", {})
    macro = _f(metrics.get("macro_quality"), 0.0)
    safety = metrics.get("safety_pass")
    false_merge = _f(metrics.get("event.false_merge_rate"), 0.0)
    false_split = _f(metrics.get("split.false_split_rate"), 0.0)
    single_source = _f(metrics.get("claim_evidence.single_source_false_cross_check_rate"), 0.0)

    if macro < MACRO_QUALITY_MIN:
        alerts.append({
            "severity": SEVERITY_CRITICAL, "code": "QUALITY_MACRO_LOW",
            "message": f"macro_quality={macro} 低于门槛 {MACRO_QUALITY_MIN}",
        })
    if safety is False:
        alerts.append({
            "severity": SEVERITY_CRITICAL, "code": "QUALITY_SAFETY_FAIL",
            "message": "benchmark safety_pass=False",
        })
    if false_merge > 0:
        alerts.append({
            "severity": SEVERITY_CRITICAL, "code": "QUALITY_FALSE_MERGE",
            "message": f"事件误合并率 {false_merge} > 0",
        })
    if false_split > 0:
        alerts.append({
            "severity": SEVERITY_CRITICAL, "code": "QUALITY_FALSE_SPLIT",
            "message": f"事件假拆分率 {false_split} > 0",
        })
    if single_source > 0:
        alerts.append({
            "severity": SEVERITY_CRITICAL, "code": "QUALITY_SINGLE_SOURCE_MISLABEL",
            "message": f"单一信源被误判为已交叉验证的比例 {single_source} > 0",
        })

    status = "healthy" if macro >= MACRO_QUALITY_MIN and safety is not False else "critical"
    return {
        "status": status,
        "commit": latest.get("commit"),
        "when": latest.get("when"),
        "macro_quality": macro,
        "safety_pass": safety,
        "event_false_merge_rate": false_merge,
        "split_false_split_rate": false_split,
        "single_source_false_cross_check_rate": single_source,
        "records": len(index),
    }


def section_pipeline(alerts: list[dict]) -> dict:
    """流水线域：来自 P1-7 dag_run.json（逐节点 status / 耗时）。"""
    run = _read_json("dag_run.json")
    if not run:
        alerts.append({
            "severity": SEVERITY_WARNING, "code": "PIPELINE_UNAVAILABLE",
            "message": "未找到 dag_run.json，请先运行 dag.py run",
        })
        return {"status": "unavailable"}

    nodes = run.get("nodes") or []
    failed = [n.get("id") for n in nodes if n.get("status") == "failed"]
    slow = [{"id": n.get("id"), "duration_sec": n.get("duration_sec")}
            for n in nodes if _f(n.get("duration_sec")) > SLOW_NODE_SEC]
    total = round(sum(_f(n.get("duration_sec")) for n in nodes), 3)
    ok = bool(run.get("ok"))

    if failed:
        alerts.append({
            "severity": SEVERITY_CRITICAL, "code": "PIPELINE_NODE_FAILED",
            "message": f"DAG 节点失败: {', '.join(str(x) for x in failed)}",
        })
    if slow:
        alerts.append({
            "severity": SEVERITY_WARNING, "code": "PIPELINE_SLOW_NODE",
            "message": f"{len(slow)} 个节点耗时超过 {SLOW_NODE_SEC}s",
        })

    return {
        "status": "healthy" if ok and not failed else "critical",
        "ok": ok,
        "node_count": len(nodes),
        "failed_nodes": failed,
        "slow_nodes": slow,
        "total_duration_sec": total,
        "run_at": run.get("run_at"),
    }


def section_run(alerts: list[dict]) -> dict:
    """本次 run 的溯源与状态。"""
    run = _read_json("run.json")
    if not run:
        return {"status": "unavailable"}
    status = run.get("status")
    if status and status != "passed":
        alerts.append({
            "severity": SEVERITY_CRITICAL, "code": "RUN_FAILED",
            "message": f"run status={status} failed_stage={run.get('failed_stage')}",
        })
    return {
        "status": "healthy" if status == "passed" else (status or "unknown"),
        "run_id": run.get("run_id"),
        "build_sha": run.get("build_sha"),
        "engine_version": run.get("engine_version"),
        "started_at": run.get("started_at"),
        "ended_at": run.get("ended_at"),
        "failed_stage": run.get("failed_stage"),
    }


def section_sources(alerts: list[dict]) -> dict:
    """信源域：来自 P1-2 Source Health 六项指标（存于 data.json）。"""
    data = _read_json("data.json")
    sh = (data or {}).get("source_health") or {}
    if not isinstance(sh, dict) or not sh:
        return {"status": "unavailable", "source_count": 0}

    names = list(sh.keys())
    avail = {k: _f(v.get("availability")) for k, v in sh.items() if isinstance(v, dict)}
    fresh = {k: _f(v.get("freshness")) for k, v in sh.items() if isinstance(v, dict)}
    low_avail = sorted([k for k, v in avail.items() if v < SOURCE_AVAILABILITY_MIN])
    stale = sorted([k for k, v in fresh.items() if v < SOURCE_FRESHNESS_MIN])

    if low_avail:
        alerts.append({
            "severity": SEVERITY_WARNING, "code": "SOURCE_LOW_AVAILABILITY",
            "message": f"{len(low_avail)} 个信源可用性低于 {SOURCE_AVAILABILITY_MIN}: "
                       f"{', '.join(low_avail[:5])}",
        })
    if stale:
        alerts.append({
            "severity": SEVERITY_WARNING, "code": "SOURCE_STALE",
            "message": f"{len(stale)} 个信源新鲜度低于 {SOURCE_FRESHNESS_MIN}",
        })

    def _avg(d):
        return round(sum(d.values()) / len(d), 4) if d else 0.0

    status = "healthy" if not low_avail and not stale else "degraded"
    return {
        "status": status,
        "source_count": len(names),
        "avg_availability": _avg(avail),
        "avg_freshness": _avg(fresh),
        "low_availability": low_avail,
        "stale": stale,
    }


def section_modules(alerts: list[dict]) -> dict:
    """模块健康域：来自 module_health.json。"""
    mh = _read_json("module_health.json")
    mods = (mh or {}).get("modules")
    if not isinstance(mods, list) or not mods:
        return {"status": "unavailable", "module_count": 0}

    degraded = []
    for m in mods:
        if not isinstance(m, dict):
            continue
        if _f(m.get("error_rate")) > MODULE_ERROR_RATE_MAX:
            degraded.append(m.get("module"))
    if degraded:
        alerts.append({
            "severity": SEVERITY_WARNING, "code": "MODULE_ERROR_RATE",
            "message": f"{len(degraded)} 个模块错误率超过 {MODULE_ERROR_RATE_MAX}: "
                       f"{', '.join(str(x) for x in degraded[:5])}",
        })

    health_dist = {}
    for m in mods:
        if isinstance(m, dict):
            h = m.get("health") or "unknown"
            health_dist[h] = health_dist.get(h, 0) + 1

    return {
        "status": "healthy" if not degraded else "degraded",
        "module_count": len(mods),
        "health_distribution": health_dist,
        "high_error_rate": degraded,
    }


def section_review(alerts: list[dict]) -> dict:
    """人工复核域：P1-4 状态机分布 + 队列积压。"""
    queue = _read_json("review_queue.json") or {}
    items = queue.get("items") or []
    state = _read_json("review_state.json") or {}
    state_items = state.get("items") or {}

    dist = {}
    for it in items:
        if isinstance(it, dict):
            s = it.get("status") or "pending"
            dist[s] = dist.get(s, 0) + 1
    pending = dist.get("pending", 0)

    if pending > REVIEW_BACKLOG_MAX:
        alerts.append({
            "severity": SEVERITY_WARNING, "code": "REVIEW_BACKLOG",
            "message": f"待复核积压 {pending} 条，超过阈值 {REVIEW_BACKLOG_MAX}",
        })

    return {
        "status": "healthy" if pending <= REVIEW_BACKLOG_MAX else "degraded",
        "queue_generated_count": queue.get("generated_count", 0),
        "queue_items": len(items),
        "queue_status_distribution": dist,
        "tracked_items": len(state_items) if isinstance(state_items, dict) else 0,
        "pending": pending,
    }


def build() -> dict:
    alerts: list[dict] = []
    sections = {
        "quality": section_quality(alerts),
        "pipeline": section_pipeline(alerts),
        "run": section_run(alerts),
        "sources": section_sources(alerts),
        "modules": section_modules(alerts),
        "review": section_review(alerts),
    }

    critical = [a for a in alerts if a.get("severity") == SEVERITY_CRITICAL]
    warning = [a for a in alerts if a.get("severity") == SEVERITY_WARNING]
    score = max(0.0, 1.0 - 0.4 * len(critical) - 0.1 * len(warning))
    if critical:
        status = "critical"
    elif warning:
        status = "degraded"
    else:
        status = "healthy"

    return {
        "version": VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": _commit_sha(),
        "overall": {
            "status": status,
            "score": round(score, 4),
            "critical_count": len(critical),
            "warning_count": len(warning),
            "reasons": [a["message"] for a in alerts[:10]],
        },
        "sections": sections,
        "alerts": alerts,
    }


def main(argv: list[str]) -> int:
    doc = build()
    to_stdout = "--json" in argv
    if not to_stdout:
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
            f.write("\n")

    if to_stdout:
        print(json.dumps(doc, ensure_ascii=False, indent=2))
    else:
        o = doc["overall"]
        print(f"[observability] status={o['status']} score={o['score']} "
              f"critical={o['critical_count']} warning={o['warning_count']}")
        for a in doc["alerts"][:10]:
            print(f"  - [{a['severity']}] {a['code']}: {a['message']}")

    if "--fail-on-critical" in argv and doc["overall"]["critical_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
