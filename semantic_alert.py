#!/usr/bin/env python3
"""S4 Semantic Alert：把每日 100+ 底层变化收敛为 ≤8 条语义告警。

两层：
1. Internal Diff：逐 canonical event 比对今昔快照
   （生命周期阶段 / 信任分 / 证据数 / 主张数 / 决策紧急度 / 日报优先级）。
2. Semantic Alert：把内部 diff 聚合成四类语义告警，按严重度排序截断至 ≤8：
   - EVENT_STAGE_CHANGED   并购生命周期阶段变化
   - EVENT_MATERIAL_CHANGED 证据/主张实质新增
   - RISK_INCREASED        信任分下降 / 当前低信任
   - DECISION_REQUIRED     决策紧急度升级 / 当前需决策

纪律（与 S1–S3、P2 一致）：
- fail-closed：任何告警必须含 type / canonical_event_id / severity / rationale / basis；数量硬上限 8。
- 不伪造变化：delta 类告警只在存在历史基线时产生；首跑仅播种基线并发「当前需关注」（seed）告警，明确标注 basis。
- observation/结论分离：internal_diffs 是事实，semantic_alerts 是聚合；推不出的维度写入 open_questions。
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
INTEL = ROOT / "intelligence.json"
LIFECYCLE = ROOT / "lifecycle_report.json"
BRIEF = ROOT / "p2_daily_brief.json"
CANONICAL = ROOT / "canonical_events.json"
BASELINE = ROOT / "p2_alert_baseline.json"
OUTPUT = ROOT / "p2_alerts.json"

VERSION = "alert-v1.0"
MAX_ALERTS = 8

# 决策紧急度等级（数值越大越紧急）
RANK = {"watch": 0, "soon": 1, "now": 2, None: 0}
# 并购生命周期阶段顺序（数值越大越接近交割/整合）
STAGE_ORDER = {
    "rumor": 0, "negotiation": 1, "agreement": 2, "regulatory": 3,
    "closing": 4, "integration": 5, "n/a": -1,
}
SEV_RANK = {"high": 3, "medium": 2, "low": 1}
ALERT_TYPES = {
    "EVENT_STAGE_CHANGED", "EVENT_MATERIAL_CHANGED",
    "RISK_INCREASED", "DECISION_REQUIRED",
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _ceid_by_event(canonical: dict) -> dict[str, str]:
    return {k: v for k, v in (canonical.get("by_event_id") or {}).items()}


def _decisions_by_event(decisions: list[dict]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for d in decisions or []:
        eid = d.get("event_id")
        u = d.get("urgency")
        if not eid:
            continue
        out.setdefault(eid, set()).add(u)
    return out


def _brief_by_event(brief: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for b in brief or []:
        eid = b.get("event_id")
        if eid:
            out[eid] = b
    return out


def _stage_by_ceid(lifecycle_entries: list[dict]) -> dict[str, str]:
    out: dict[str, str] = {}
    for e in lifecycle_entries or []:
        ceid = e.get("canonical_event_id")
        if ceid:
            out[ceid] = e.get("stage") or "n/a"
    return out


def current_snapshot(
    events: list[dict],
    lifecycle_entries: list[dict],
    decisions: list[dict],
    brief: list[dict],
    ceid_map: dict[str, str],
) -> dict[str, dict]:
    """构造「当前」逐 canonical event 快照，作为 diff 基准与基线种子。"""
    stage_map = _stage_by_ceid(lifecycle_entries)
    dec_map = _decisions_by_event(decisions)
    brief_map = _brief_by_event(brief)
    snap: dict[str, dict] = {}
    for ev in events or []:
        eid = ev.get("event_id")
        if not eid:
            continue
        ceid = ceid_map.get(eid, eid)
        trust = ev.get("trust") or {}
        claims = ev.get("claims") or {}
        dec = dec_map.get(eid) or set()
        urgency = max(dec, key=lambda u: RANK.get(u, 0)) if dec else None
        b = brief_map.get(eid) or {}
        snap[ceid] = {
            "event_id": eid,
            "title": ev.get("title"),
            "topic": ev.get("topic"),
            "stage": stage_map.get(ceid, "n/a"),
            "trust_score": trust.get("score"),
            "evidence_count": len(ev.get("evidence") or []),
            "proposition_count": (claims.get("proposition_count") if isinstance(claims.get("proposition_count"), int) else 0),
            "decision_urgency": urgency,
            "review_required": bool(ev.get("review_required")),
            "daily_priority": b.get("daily_priority") or 0,
        }
    # 生命周期条目可能覆盖 intelligence 未列的事件（用生命周期标题补全）
    for e in lifecycle_entries or []:
        ceid = e.get("canonical_event_id")
        if ceid and ceid not in snap:
            snap[ceid] = {
                "event_id": e.get("identity_key"),
                "title": e.get("title"),
                "topic": None,
                "stage": e.get("stage") or "n/a",
                "trust_score": None,
                "evidence_count": 0,
                "proposition_count": 0,
                "decision_urgency": None,
                "daily_priority": 0,
            }
    return snap


def compute_internal_diffs(current: dict[str, dict], baseline: dict[str, dict]) -> list[dict]:
    """逐事件字段级 diff（仅当有历史基线）。"""
    diffs: list[dict] = []
    fields = ["stage", "trust_score", "evidence_count", "proposition_count", "decision_urgency", "daily_priority"]
    for ceid, cur in current.items():
        base = baseline.get(ceid)
        if base is None:
            continue
        changes = []
        for f in fields:
            ov, nv = base.get(f), cur.get(f)
            if ov != nv:
                changes.append({"field": f, "old": ov, "new": nv})
        if changes:
            diffs.append({
                "canonical_event_id": ceid,
                "event_id": cur.get("event_id"),
                "title": cur.get("title"),
                "topic": cur.get("topic"),
                "changes": changes,
            })
    return diffs


def _mk_alert(atype: str, snap: dict, severity: str, rationale: str, basis: str,
              changed_fields: list[str], sort_key: float) -> dict:
    a = {
        "type": atype,
        "canonical_event_id": None,  # 由调用方填充
        "event_id": snap.get("event_id"),
        "title": snap.get("title"),
        "topic": snap.get("topic"),
        "severity": severity,
        "rationale": rationale,
        "basis": basis,
        "changed_fields": changed_fields,
    }
    a["_sort"] = sort_key  # 非序列化字段
    return a


def aggregate_alerts(current: dict[str, dict], diffs: list[dict], baseline_present: bool) -> list[dict]:
    """把 internal diff + 当前需关注状态聚合成语义告警，按严重度排序截断至 ≤8。"""
    candidates: list[dict] = []

    # —— 第一层：delta（仅当有历史基线）——
    for d in diffs:
        ceid = d["canonical_event_id"]
        snap = current.get(ceid, {})
        ch = {c["field"]: c for c in d["changes"]}
        changed = []

        if "stage" in ch:
            ov, nv = ch["stage"]["old"], ch["stage"]["new"]
            fwd = STAGE_ORDER.get(nv, -1) > STAGE_ORDER.get(ov, -1)
            sev = "high" if fwd else "medium"
            candidates.append(_mk_alert(
                "EVENT_STAGE_CHANGED", snap, sev,
                f"并购生命周期阶段 {ov} → {nv}", "delta", ["stage"],
                3.0 + (STAGE_ORDER.get(nv, -1)),
            ))
            candidates[-1]["canonical_event_id"] = ceid
            changed.append("stage")

        mat = 0
        if "evidence_count" in ch:
            mat += (ch["evidence_count"]["new"] or 0) - (ch["evidence_count"]["old"] or 0)
        if "proposition_count" in ch:
            mat += (ch["proposition_count"]["new"] or 0) - (ch["proposition_count"]["old"] or 0)
        if mat > 0:
            sev = "high" if mat >= 3 else "medium"
            candidates.append(_mk_alert(
                "EVENT_MATERIAL_CHANGED", snap, sev,
                f"证据/主张实质新增 {mat} 项", "delta", ["evidence_count", "proposition_count"],
                2.0 + mat,
            ))
            candidates[-1]["canonical_event_id"] = ceid
            changed.append("material")

        if "trust_score" in ch:
            drop = (ch["trust_score"]["old"] or 0) - (ch["trust_score"]["new"] or 0)
            if drop > 0:
                sev = "high" if drop >= 15 else ("medium" if drop >= 5 else "low")
                candidates.append(_mk_alert(
                    "RISK_INCREASED", snap, sev,
                    f"信任分 {ch['trust_score']['old']} → {ch['trust_score']['new']}（降 {drop}）",
                    "delta", ["trust_score"], 2.0 + drop / 10.0,
                ))
                candidates[-1]["canonical_event_id"] = ceid
                changed.append("trust")

        if "decision_urgency" in ch:
            ov, nv = ch["decision_urgency"]["old"], ch["decision_urgency"]["new"]
            if RANK.get(nv, 0) > RANK.get(ov, 0):
                sev = "high" if nv == "now" else "medium"
                candidates.append(_mk_alert(
                    "DECISION_REQUIRED", snap, sev,
                    f"决策紧急度 {ov} → {nv}", "delta", ["decision_urgency"],
                    3.0 + RANK.get(nv, 0),
                ))
                candidates[-1]["canonical_event_id"] = ceid
                changed.append("decision")

    # —— 第二层：当前需关注（standing / seed）——
    for ceid, snap in current.items():
        u = snap.get("decision_urgency")
        prio = snap.get("daily_priority") or 0
        if u in ("now", "soon"):
            if not any(a["type"] == "DECISION_REQUIRED" and a["canonical_event_id"] == ceid for a in candidates):
                sev = "high" if u == "now" else "medium"
                basis = "standing" if baseline_present else "seed"
                candidates.append(_mk_alert(
                    "DECISION_REQUIRED", snap, sev,
                    f"当前决策紧急度 {u}（待人工确认）", basis, ["decision_urgency"],
                    3.0 + RANK.get(u, 0) + prio / 1000.0,
                ))
                candidates[-1]["canonical_event_id"] = ceid
        elif snap.get("review_required") and not u:
            # 事件被标记需人工复核、但尚无任何决策记录 → 仍需决策
            if not any(a["type"] == "DECISION_REQUIRED" and a["canonical_event_id"] == ceid for a in candidates):
                sev = "high" if prio >= 85 else "medium"
                basis = "standing" if baseline_present else "seed"
                candidates.append(_mk_alert(
                    "DECISION_REQUIRED", snap, sev,
                    f"待人工复核、暂无决策记录（日报优先级 {prio}）", basis, ["review_required"],
                    2.5 + prio / 1000.0,
                ))
                candidates[-1]["canonical_event_id"] = ceid

        ts = snap.get("trust_score")
        if isinstance(ts, int) and ts < 40:
            if not any(a["type"] == "RISK_INCREASED" and a["canonical_event_id"] == ceid for a in candidates):
                basis = "standing" if baseline_present else "seed"
                candidates.append(_mk_alert(
                    "RISK_INCREASED", snap, "medium",
                    f"当前信任分偏低（{ts}）", basis, ["trust_score"],
                    2.0 + (40 - ts) / 10.0,
                ))
                candidates[-1]["canonical_event_id"] = ceid

    # 排序：严重度优先，其次 sort_key
    candidates.sort(key=lambda a: (SEV_RANK.get(a["severity"], 0), a["_sort"]), reverse=True)
    top = candidates[:MAX_ALERTS]
    for a in top:
        a.pop("_sort", None)
    return top


def build(
    events: list[dict],
    lifecycle_entries: list[dict],
    decisions: list[dict],
    brief: list[dict],
    baseline: dict[str, dict] | None = None,
    ceid_map: dict[str, str] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    ceid_map = ceid_map or {}
    current = current_snapshot(events, lifecycle_entries, decisions, brief, ceid_map)
    baseline_present = bool(baseline)
    diffs = compute_internal_diffs(current, baseline) if baseline_present else []
    alerts = aggregate_alerts(current, diffs, baseline_present)

    type_counts: dict[str, int] = {}
    for a in alerts:
        type_counts[a["type"]] = type_counts.get(a["type"], 0) + 1

    open_questions: list[dict] = []
    if not baseline_present:
        open_questions.append({
            "dimension": "历史基线（delta 类告警）",
            "status": "unavailable_first_run",
            "reason": "首跑无历史快照，EVENT_STAGE_CHANGED / EVENT_MATERIAL_CHANGED / "
                      "RISK_INCREASED(delta) / DECISION_REQUIRED(delta) 暂不可用",
            "unblock": "本次仅播种基线并发布「当前需关注」（seed）告警；次日运行起产生真实 delta",
        })
    open_questions.append({
        "dimension": "非并购事件生命周期阶段",
        "status": "not_applicable",
        "reason": "EVENT_STAGE_CHANGED 仅适用于 acquisition 类 canonical event（lifecycle 覆盖 16/141）",
        "unblock": "其余事件靠 MATERIAL / RISK / DECISION 三类语义告警覆盖",
    })
    open_questions.append({
        "dimension": "决策人工确认",
        "status": "delegated",
        "reason": "告警中的决策紧急度来自 intelligence.json 引擎产出，不改写业务判断",
        "unblock": "high-impact action 仍由 Human Review 确认（见 decision.guardrail）",
    })

    return {
        "version": VERSION,
        "generated_at": generated_at or _now(),
        "principle": "两层收敛：Internal Diff（事实）→ Semantic Alert（≤8 条聚合）；"
                    "delta 不伪造、首跑仅种子、告警不改写业务判断",
        "meta": {
            "total_events": len(current),
            "baseline_present": baseline_present,
            "basis": "delta_vs_baseline" if baseline_present else "seed_first_run",
            "internal_diff_count": len(diffs),
            "alert_count": len(alerts),
            "max_alerts": MAX_ALERTS,
            "alert_type_counts": type_counts,
        },
        "internal_diffs": diffs,
        "semantic_alerts": alerts,
        "open_questions": open_questions,
    }


def validate(doc: dict) -> None:
    assert doc.get("version") == VERSION, doc.get("version")
    meta = doc.get("meta") or {}
    alerts = doc.get("semantic_alerts") or []
    assert isinstance(alerts, list), "semantic_alerts 必须为列表"
    assert len(alerts) <= MAX_ALERTS, f"语义告警超过上限 {MAX_ALERTS}：{len(alerts)}"
    assert meta.get("alert_count") == len(alerts), "meta.alert_count 与实际不符"
    for a in alerts:
        assert a.get("type") in ALERT_TYPES, f"未知告警类型：{a.get('type')}"
        assert a.get("canonical_event_id"), "告警缺少 canonical_event_id"
        assert a.get("severity") in SEV_RANK, f"告警 severity 非法：{a.get('severity')}"
        assert a.get("rationale"), "告警缺少 rationale"
        assert a.get("basis") in {"delta", "standing", "seed"}, f"告警 basis 非法：{a.get('basis')}"
    assert isinstance(doc.get("internal_diffs"), list), "internal_diffs 必须为列表"
    assert doc.get("open_questions"), "open_questions 不得为空"


def run(persist: bool = True) -> dict[str, Any]:
    intel = _load(INTEL)
    lifecycle = _load(LIFECYCLE)
    brief_doc = _load(BRIEF)
    canonical = _load(CANONICAL)
    baseline_doc = _load(BASELINE)

    events = intel.get("events") or []
    decisions = intel.get("decisions") or []
    lifecycle_entries = lifecycle.get("entries") or []
    brief = brief_doc.get("brief") or []
    ceid_map = _ceid_by_event(canonical)
    baseline = baseline_doc.get("snapshots") if isinstance(baseline_doc.get("snapshots"), dict) else None

    doc = build(events, lifecycle_entries, decisions, brief, baseline, ceid_map)
    validate(doc)

    if persist:
        OUTPUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # 播种/更新基线（供次日 diff）
        new_baseline = {
            "version": VERSION,
            "generated_at": doc["generated_at"],
            "snapshots": current_snapshot(events, lifecycle_entries, decisions, brief, ceid_map),
        }
        BASELINE.write_text(json.dumps(new_baseline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return doc


def main() -> None:
    parser = argparse.ArgumentParser(description="S4 语义告警：收敛每日底层变化为 ≤8 条语义告警")
    parser.add_argument("--no-persist", action="store_true", help="只计算不写文件")
    args = parser.parse_args()
    doc = run(persist=not args.no_persist)
    print(json.dumps({
        "basis": doc["meta"]["basis"],
        "internal_diff_count": doc["meta"]["internal_diff_count"],
        "alert_count": doc["meta"]["alert_count"],
        "alert_type_counts": doc["meta"]["alert_type_counts"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
