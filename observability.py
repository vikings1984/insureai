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
AGING_STALE_MAX = 20
KEY_RELEVANCE_MIN = 0.8
# 关键源（监管/官方）关键词：这些源即便健康度偏低也不建议降权（排除关键源）
REGULATORY_KEYWORDS = ("监管", "银保监", "金融监督", "证监会", "人民银行", "央行",
                       "财政部", "交易所", "国资委", "统计局", "国务院", "总局")
SLOW_NODE_SEC = 60.0

# —— Review Queue 压缩分级（P1-2，第五阶段；只读，不 auto-defer）——
# 与 decision_funnel.CONFLICT_REASONS 对齐：conflict/claim_conflict = 直接指向需人工裁决。
COMPRESS_DECISION_REASONS = {"conflict", "claim_conflict"}
COMPRESS_MATERIAL_REASONS = {"change_impact"}
COMPRESS_RELEVANT_PRIORITY = 50

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


def compute_review_aging(state_items: dict, now=None) -> tuple[dict, int, int]:
    """纯函数：按 review_state 中 pending 项的 created_at 计算账龄分桶。

    返回 (buckets, max_age_days, stale_7plus)。`now` 可注入以便单测。
    """
    if now is None:
        now = datetime.now(timezone.utc)
    buckets = {"0_1": 0, "1_3": 0, "3_7": 0, "7_plus": 0}
    max_age = 0
    if isinstance(state_items, dict):
        for it in state_items.values():
            if not isinstance(it, dict):
                continue
            if (it.get("status") or "pending") != "pending":
                continue
            ca = it.get("created_at")
            if not ca:
                continue
            try:
                ct = datetime.fromisoformat(str(ca).replace("Z", "+00:00"))
                if ct.tzinfo is None:
                    ct = ct.replace(tzinfo=timezone.utc)
                days = (now - ct).days
            except (ValueError, TypeError):
                days = -1
            if days < 0:
                continue
            max_age = max(max_age, days)
            if days <= 1:
                buckets["0_1"] += 1
            elif days <= 3:
                buckets["1_3"] += 1
            elif days <= 7:
                buckets["3_7"] += 1
            else:
                buckets["7_plus"] += 1
    return buckets, max_age, buckets["7_plus"]


def compute_review_compression(items: list[dict]) -> dict:
    """纯函数：Review Queue 压缩分级（只读）。

    依据实测（100 条 pending 全在 0-1 天桶 → 非积压问题，而是「一次性产生太多需关注项」），
    本函数把 pending 复核项按「决策级 / 实质变化级 / 相关 / 噪声」分档，量化
    「每天真正需人判断 N 条」（首屏负荷）。**只做排序/呈现参考，不改变任何项状态、
    不 auto-defer。** 分档优先命中：决策级 > 实质变化级 > 相关 > 噪声。
    """
    tiers = {"decision_required": 0, "material_change": 0, "relevant": 0, "noise": 0}
    for it in items or []:
        if not isinstance(it, dict):
            continue
        if (it.get("status") or "pending") != "pending":
            continue
        reasons = {r.get("type") for r in (it.get("reasons") or []) if isinstance(r, dict)}
        if reasons & COMPRESS_DECISION_REASONS:
            tiers["decision_required"] += 1
        elif (reasons & COMPRESS_MATERIAL_REASONS) or it.get("change_impact") is not None:
            tiers["material_change"] += 1
        elif (_f(it.get("priority")) >= COMPRESS_RELEVANT_PRIORITY
              or it.get("trust_level") == "high"):
            tiers["relevant"] += 1
        else:
            tiers["noise"] += 1
    total = sum(tiers.values())
    human_load = tiers["decision_required"] + tiers["material_change"]
    return {
        "tiers": tiers,
        "total_pending": total,
        "daily_human_load": human_load,
        "compression_ratio": round(1 - (human_load / total), 4) if total else 0.0,
        "thresholds": {
            "decision_reasons": sorted(COMPRESS_DECISION_REASONS),
            "material_reasons": sorted(COMPRESS_MATERIAL_REASONS),
            "relevant_priority": COMPRESS_RELEVANT_PRIORITY,
        },
        "note": "只读压缩分级（排序/呈现用）；不 auto-defer、不改变任何项状态",
    }


def section_review(alerts: list[dict]) -> dict:
    """人工复核域：P1-4 状态机分布 + 队列积压 + 积压账龄（P1-B，只读）。

    账龄（aging）按 review_state.json 中 pending 项的 created_at 计算滞留天数，
    分桶 0-1 / 1-3 / 3-7 / >7 天。**仅报告，不做任何自动 defer / 关闭动作**；
    仅当 >7 天陈旧桶超过 AGING_STALE_MAX 时发一条 warning 提醒人工关注。
    """
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

    # 账龄：以 review_state 中 pending 项的 created_at 为入队时刻
    buckets, max_age, stale = compute_review_aging(state_items)

    if pending > REVIEW_BACKLOG_MAX:
        alerts.append({
            "severity": SEVERITY_WARNING, "code": "REVIEW_BACKLOG",
            "message": f"待复核积压 {pending} 条，超过阈值 {REVIEW_BACKLOG_MAX}",
        })
    if stale > AGING_STALE_MAX:
        alerts.append({
            "severity": SEVERITY_WARNING, "code": "REVIEW_AGING_STALE",
            "message": f"{stale} 条 pending 复核已滞留 >7 天，超过阈值 {AGING_STALE_MAX}，建议人工清理",
        })

    return {
        "status": "healthy" if pending <= REVIEW_BACKLOG_MAX and stale <= AGING_STALE_MAX
        else "degraded",
        "queue_generated_count": queue.get("generated_count", 0),
        "queue_items": len(items),
        "queue_status_distribution": dist,
        "tracked_items": len(state_items) if isinstance(state_items, dict) else 0,
        "pending": pending,
        "aging": {
            "buckets": buckets,
            "max_age_days": max_age,
            "stale_7plus": stale,
            "note": "只读指标；不自动 defer/关闭 pending 项",
        },
        "compression": compute_review_compression(items),
    }


def section_ce_linkage(alerts: list[dict]) -> dict:
    """下游 CE 联动审计（P0-C，Event OS 第四阶段「生产验证」核心可观测性指标）。

    验证 review / monitoring / decision 三类下游产物是否正确挂接到 Canonical Event 层。
    若某类下游产物悄悄丢失 canonical_event_id（或 review 的 event_id 无法解析到 CE 池），
    本段会告警，从而在生产验证阶段捕捉「CE 联动回归」这类静默故障。

    口径（均对照 canonical_events.json 的 CE 池）：
    - decision  : decisions_pending.json 的 funnel 项，canonical_event_id 必须落在 CE 池；
    - monitoring: p2_alerts.json 的 semantic_alerts，ceid / canonical_event_id 必须落在 CE 池
                  （当前无告警时视为 vacuously 100%，不告警）；
    - review    : review_queue.json 的 item 只带 event_id（由 CE 注册表在下游 canonicalize），
                  故用「event_id 经 by_event_id 解析到 CE 池」的解析率度量，未解析数即解析失败数。

    告警策略：仅当某非空表面的联动比例 < 1.0 才告警；CE 池缺失则整段降级 unavailable。
    该指标属数据一致性审计，不破坏 fail-closed 安全门，故以 warning 级别上报。
    """
    ce = _read_json("canonical_events.json")
    ces = (ce or {}).get("canonical_events") or {}
    pool = set(ces.keys())
    by_eid = (ce or {}).get("by_event_id") or {}

    if not pool:
        alerts.append({
            "severity": SEVERITY_WARNING, "code": "CE_LINKAGE_UNAVAILABLE",
            "message": "未找到 Canonical Event 池（canonical_events.json），无法审计 CE 联动",
        })
        return {"status": "unavailable", "ce_pool_size": 0, "surfaces": {}}

    def _ratio(ok: int, total: int) -> float:
        return round(ok / total, 4) if total else 1.0

    # decision 表面
    dp = _read_json("decisions_pending.json")
    tiers: list[dict] = []
    if dp:
        fn = dp.get("funnel") or {}
        for t in ("now", "soon", "watch"):
            tiers += fn.get(t) or []
    dec_total = len(tiers)
    dec_ok = sum(1 for i in tiers if i.get("canonical_event_id") in pool)

    # monitoring 表面
    pa = _read_json("p2_alerts.json")
    al = (pa or {}).get("semantic_alerts") or []
    mon_total = len(al)
    mon_ok = sum(1 for i in al
                 if (i.get("ceid") or i.get("canonical_event_id")) in pool)

    # review 表面（event_id → CE 解析率）
    rq = _read_json("review_queue.json")
    items = (rq or {}).get("items") or []
    rev_total = len(items)
    rev_ok = 0
    rev_unresolved: list[str] = []
    for i in items:
        eid = i.get("event_id")
        if not eid:
            rev_unresolved.append("<empty_event_id>")
            continue
        ceid = by_eid.get(eid)
        if ceid in pool or eid in pool:
            rev_ok += 1
        else:
            rev_unresolved.append(eid)

    surfaces = {
        "decision": {"total": dec_total, "linked": dec_ok, "ratio": _ratio(dec_ok, dec_total)},
        "monitoring": {"total": mon_total, "linked": mon_ok, "ratio": _ratio(mon_ok, mon_total)},
        "review": {"total": rev_total, "linked": rev_ok, "ratio": _ratio(rev_ok, rev_total)},
    }

    gaps = [name for name, s in surfaces.items() if s["total"] > 0 and s["ratio"] < 1.0]
    if gaps:
        detail = "; ".join(f"{name} {surfaces[name]['linked']}/{surfaces[name]['total']}"
                           for name in gaps)
        alerts.append({
            "severity": SEVERITY_WARNING, "code": "CE_LINKAGE_GAP",
            "message": f"下游 CE 联动缺失：{detail}",
        })

    status = "healthy" if not gaps else "degraded"
    return {
        "status": status,
        "ce_pool_size": len(pool),
        "surfaces": surfaces,
        "unresolved_review_event_ids": len(rev_unresolved),
    }


def section_source_degrade(alerts: list[dict]) -> dict:
    """信源降权建议清单（P1-C，只读报告，**不执行**）。

    从 P1-2 Source Health 六项指标中筛出「健康度偏低」的信源，生成**建议降权**清单。
    关键设计：

    - 候选条件：availability < 门槛 或 freshness < 门槛（与 section_sources 一致）；
    - **排除关键源**：insurance_relevance >= KEY_RELEVANCE_MIN，或名称命中监管/官方关键词，
      一律不进入建议清单——监管/官方源即便暂时陈旧也必须保留在池中，降权会伤情报覆盖；
    - 仅当「不健康 且 低价值」时才建议降权（纯 advisory，绝不自动 suspend / 改写 data.json）。

    本段只产出报告，不发告警（告警由 section_sources 负责），不修改任何源产物。
    """
    data = _read_json("data.json")
    sh = (data or {}).get("source_health") or {}
    if not isinstance(sh, dict) or not sh:
        return {"status": "unavailable", "suggestions": []}

    # 人工确认台账（P2）：读取 source_degrade_ledger.json，把每条建议的最新人工动作
    # 标注为 status（suggested/confirm/downweight/suspend/reject/recover）。只读呈现，
    # 绝不据此自动改写 data.json 或暂停信源。
    ledger = _read_json("source_degrade_ledger.json") or {}
    latest: dict[str, str] = {}
    for act in (ledger.get("actions") or []):
        if isinstance(act, dict) and act.get("source"):
            latest[act["source"]] = act.get("action", "suggested")

    suggestions = []
    for name, v in sh.items():
        if not isinstance(v, dict):
            continue
        avail = _f(v.get("availability"))
        fresh = _f(v.get("freshness"))
        rel = _f(v.get("insurance_relevance"))
        reasons = []
        if avail < SOURCE_AVAILABILITY_MIN:
            reasons.append(f"availability={avail}<{SOURCE_AVAILABILITY_MIN}")
        if fresh < SOURCE_FRESHNESS_MIN:
            reasons.append(f"freshness={fresh}<{SOURCE_FRESHNESS_MIN}")
        if not reasons:
            continue  # 健康源不进清单
        # 排除关键源
        is_key = rel >= KEY_RELEVANCE_MIN or any(kw in (name or "") for kw in REGULATORY_KEYWORDS)
        if is_key:
            continue
        suggestions.append({
            "source": name,
            "availability": avail,
            "freshness": fresh,
            "insurance_relevance": rel,
            "reasons": reasons,
            "status": latest.get(name, "suggested"),
        })

    suggestions.sort(key=lambda s: (s["insurance_relevance"], s["freshness"]))
    return {
        "status": "healthy" if not suggestions else "degraded",
        "key_relevance_min": KEY_RELEVANCE_MIN,
        "excluded_keyword_count": len(REGULATORY_KEYWORDS),
        "suggestion_count": len(suggestions),
        "confirmed_count": sum(1 for s in suggestions if s["status"] != "suggested"),
        "note": "只读建议清单 + 人工确认状态；不自动降权/暂停任何信源，需人工拍板后执行",
        "suggestions": suggestions,
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
        "ce_linkage": section_ce_linkage(alerts),
        "source_degrade": section_source_degrade(alerts),
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
