#!/usr/bin/env python3
"""S5 Decision Funnel：把 review_queue 的「待决策」洪流收敛为可管理的漏斗。

承接 E2 决策账本（decisions_ledger.json，含真实 decided_at + 去重样本）：
- 用账本 + review_queue.decision 标记「已决」事件（绝不伪造决策）。
- 其余「待决」事件按 review 原因 + 优先级派生紧急度分桶（now / soon / watch），
  作为可观测的代理（非业务判断；人类紧急度标签只在决策后存在）。

Sprint 3（§9.4）硬化：对每一条待决 CE 显式评估「六条件」（监控/T1监管、语义变化、
决策集阶段、证据+可信度过门、本角色未处理、fail-closed），把评估结果作为注解挂到每条
待决项上，并产出「真正达到决策门」的子集（decision_ready）——单源+监管/评级按纪律不得
进入 decision_ready。漏斗新增「分角色计数」（pending_by_role，四类冻结：AI/并购/监管/健康险）。

纪律（与 S1–S4、P2 一致）：
- fail-closed：decision_required == decided + pending；分桶计数自洽；每条必含 canonical_event_id。
- observation/conclusion 分离：待决分桶是事实代理；六条件是可观测评估，不是业务判断；
  决策偏好结论在样本 <30 时显式阻断（open_questions）。
- 不伪造：已决集合只来自真实决策记录（账本 / review_queue.decision）；无制造的时间戳或补样本。
- 89 留复核页：decision_required 取自 Human-Review 队列（诚实来源），非监控项留在复核页、不进主数字。
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REVIEW = ROOT / "review_queue.json"
LEDGER = ROOT / "decisions_ledger.json"
INTEL = ROOT / "intelligence.json"
CANONICAL = ROOT / "canonical_events.json"
ALERTS = ROOT / "p2_alerts.json"
STATE = ROOT / "p2_state.json"
OUTPUT = ROOT / "decisions_pending.json"

VERSION = "funnel-v1.1"
MIN_SAMPLE = 30
TOP_PENDING = 12

# 待决分桶（数值越大越紧急）
TIER_RANK = {"now": 2, "soon": 1, "watch": 0}
# review 原因中直接指向「需人工裁决」的冲突类
CONFLICT_REASONS = {"conflict", "claim_conflict"}

# —— §9.5 冻结四类角色（显式声明，不推断）——
ROLE_FROZEN = ["ai", "ma", "regulatory", "health"]
ROLE_LABEL = {
    "ai": "AI", "ma": "并购", "regulatory": "监管", "health": "健康险", "other": "其他",
}
# 角色关键词（来自冻结 watchlist，透明声明）
ROLE_KEYWORDS: dict[str, list[str]] = {
    "ma": ["并购", "收购", "股权", "增资", "受让", "控股"],
    "regulatory": ["监管", "批复", "处罚", "金监", "银保监", "监管函"],
    "health": ["健康险", "医疗险", "惠民保", "长期护理", "护理", "重疾"],
    "ai": ["AI", "大模型"],
}
ROLE_TOPICS: dict[str, set[str]] = {
    "ai": {"ai_intelligent"},
    "health": set(),
}

# —— §9.4 六条件阈值（显式声明、可复核）——
DECISION_STAGES = {"agreement", "regulatory", "closing"}
REG_ISSUED_EFFECTIVE = {"issued", "effective"}
OK_TRUST = {"medium", "high"}
MIN_EVIDENCE = 1  # 至少一条证据；单源+监管/评级仍按纪律不出 decision_ready


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


def _decided_at_lookup(ledger_entries: list[dict], review_items: list[dict]) -> dict[str, str]:
    out: dict[str, str] = {}
    for e in ledger_entries or []:
        eid = e.get("event_id")
        if eid and e.get("decided_at"):
            out.setdefault(eid, e["decided_at"])
    for i in review_items or []:
        d = i.get("decision")
        eid = i.get("event_id")
        if eid and isinstance(d, dict) and d.get("decided_at"):
            out.setdefault(eid, d["decided_at"])
    return out


def _role_of(ce: dict) -> str:
    """把 CE 归入冻结四类角色之一（AI/并购/监管/健康险），其余归 other。

    仅用显式声明的 domain / event_type / topic / 关键词，不做推断。
    """
    domain = ce.get("domain") or ""
    et = ce.get("event_type") or ""
    topic = ce.get("topic") or ""
    hay = (ce.get("title") or "") + " " + (ce.get("key_entity") or "")
    if domain == "regulatory" or et == "regulatory":
        return "regulatory"
    if et == "acquisition":
        return "ma"
    if topic in ROLE_TOPICS["health"] or any(k in hay for k in ROLE_KEYWORDS["health"]):
        return "health"
    if topic in ROLE_TOPICS["ai"] or any(k in hay for k in ROLE_KEYWORDS["ai"]):
        return "ai"
    if any(k in hay for k in ROLE_KEYWORDS["ma"]):
        return "ma"
    return "other"


def _watched(ce: dict, watch_topics: set[str], watch_kw: set[str]) -> bool:
    topic = ce.get("topic") or ""
    hay = (ce.get("title") or "") + " " + (ce.get("key_entity") or "") + " " + (ce.get("event_type") or "")
    if topic in watch_topics:
        return True
    return any(k and k in hay for k in watch_kw)


def _eval_six(
    ce: dict,
    intel_ev: dict | None,
    monitored: bool,
    acted: bool,
    t1_reg: bool,
    decided: bool,
    feedback_status: str | None,
    has_semantic_change: bool,
) -> dict[str, Any]:
    """§9.4 六条件评估。返回 {met, failed:[条件序号], detail:{...}}。

    条件：
      1. 在监控(Watch/曾标重要/曾 acted_on) OR 系统级 T1 监管
      2. 存在语义变化（阶段/关键命题），不是又来一个源
      3. 阶段属可决策集（收购 agreement/regulatory/closing）
      4. 证据覆盖+可信度过门；单源+监管/评级不得出 Decision Required
      5. 该 CE 本角色下未处理（无 decided_at 或反馈非 snoozed/resolved）
      6. fail-closed：推不出进 Open Question（缺数据则不声称达到门）
    """
    domain = ce.get("domain") or ""
    et = ce.get("event_type") or ""
    lc = ce.get("lifecycle") or {}
    stage = lc.get("stage") or ce.get("stage") or "n/a"
    status = lc.get("status") or ce.get("status")

    ev = len((intel_ev or {}).get("evidence") or []) if intel_ev else 0
    trust_level = ((intel_ev or {}).get("trust") or {}).get("level") if intel_ev else None
    src = (intel_ev or {}).get("source_count") or 0

    # 条件 1
    c1 = bool(monitored or acted or t1_reg)
    # 条件 2：来自 S4 语义告警（真实 delta）或并购阶段已前移
    c2 = bool(has_semantic_change) or (domain == "acquisition" and stage not in ("rumor", "n/a", None))
    # 条件 3：决策集阶段
    c3 = (domain == "acquisition" and stage in DECISION_STAGES) or (
        domain == "regulatory" and status in REG_ISSUED_EFFECTIVE
    )
    # 条件 4：证据+可信度过门；单源+监管/评级排除
    single_src_regulatory = (src <= 1) and (domain == "regulatory" or et == "rating")
    base4 = (ev >= MIN_EVIDENCE) and (trust_level in OK_TRUST)
    c4 = bool(base4) and not single_src_regulatory
    # 条件 5：本角色未处理
    c5 = (not decided) and (feedback_status not in ("snoozed", "resolved"))
    # 条件 6：fail-closed（缺 intel 数据则视为不可评估，不出 decision_ready）
    data_ok = intel_ev is not None
    c6 = data_ok  # 能评估才声称达到门；否则进 open_questions

    conds = [c1, c2, c3, c4, c5]
    failed = [i for i, c in enumerate(conds, 1) if not c]
    if not c6:
        failed.append(6)
    met = all(conds) and c6

    return {
        "met": met,
        "failed": failed,
        "detail": {
            "monitored": monitored, "acted": acted, "t1_reg": t1_reg,
            "has_semantic_change": has_semantic_change,
            "stage": stage, "status": status,
            "evidence_count": ev, "trust_level": trust_level, "source_count": src,
            "single_src_regulatory": single_src_regulatory, "decided": decided,
            "feedback_status": feedback_status,
        },
    }


def build(
    review_items: list[dict],
    ledger_entries: list[dict],
    intel_events: list[dict],
    canonical_events: dict,
    alert_ceids: set[str],
    t1_alert_ceids: set[str],
    watch_topics: set[str],
    watch_kw: set[str],
    feedback_status_by_ceid: dict[str, str],
    ceid_map: dict[str, str],
    generated_at: str | None = None,
) -> dict[str, Any]:
    ces = canonical_events.get("canonical_events") or {}
    # intel 按 canonical_event_id（兜底 event_id）
    intel_by_ceid: dict[str, dict] = {}
    for e in intel_events or []:
        cid = e.get("canonical_event_id") or ceid_map.get(e.get("event_id"), e.get("event_id"))
        if cid:
            intel_by_ceid.setdefault(cid, e)

    # 已决事件集合（诚实来源：账本 ∪ review_queue.decision）
    ledger_eids = {e.get("event_id") for e in (ledger_entries or []) if e.get("event_id")}
    decided_eids: set[str] = set(ledger_eids)
    for i in review_items or []:
        if isinstance(i.get("decision"), dict):
            decided_eids.add(i.get("event_id"))

    # —— 决策所需全集：review_queue 中 status=pending（诚实来源；89 留复核页）——
    required = [i for i in (review_items or []) if i.get("status") == "pending"]
    non_pending = len([i for i in (review_items or []) if i.get("status") != "pending"])

    urgency = {e.get("event_id"): e.get("urgency") for e in (ledger_entries or []) if e.get("event_id") and e.get("urgency")}
    decided_at = _decided_at_lookup(ledger_entries, review_items)

    pending: list[dict] = []
    decided: list[dict] = []
    six_failed_counter: Counter = Counter()
    decision_ready: list[dict] = []

    for i in required:
        eid = i.get("event_id")
        if not eid:
            continue
        ceid = ceid_map.get(eid, eid)
        ce = ces.get(ceid) or {}
        reasons = i.get("reasons") or []
        rtypes = {r.get("type") for r in reasons if isinstance(r, dict)}
        prio = i.get("priority") or 0
        is_decided = eid in decided_eids

        role = _role_of(ce) if ce else "other"
        monitored = _watched(ce, watch_topics, watch_kw) if ce else False
        acted = eid in ledger_eids
        t1_reg = (ce.get("domain") == "regulatory" and (ce.get("lifecycle") or {}).get("status") in REG_ISSUED_EFFECTIVE) or (ceid in t1_alert_ceids)
        has_semantic_change = ceid in alert_ceids
        six = _eval_six(
            ce, intel_by_ceid.get(ceid), monitored, acted, t1_reg, is_decided,
            feedback_status_by_ceid.get(ceid), has_semantic_change,
        )
        for f in six["failed"]:
            six_failed_counter[f] += 1

        base = {
            "event_id": eid,
            "canonical_event_id": ceid,
            "title": i.get("title") or ce.get("title"),
            "topic": i.get("topic") or ce.get("topic"),
            "priority": prio,
            "trust_level": (intel_by_ceid.get(ceid) or {}).get("trust", {}).get("level"),
            "reason_types": sorted(rtypes),
            "role": role,
            "meets_six": six["met"],
            "failed_conditions": six["failed"],
            "six_detail": six["detail"],
            "urgency": urgency.get(eid),
        }

        if is_decided:
            base["decided_at"] = decided_at.get(eid)
            decided.append(base)
        else:
            tier = _tier_of(rtypes, prio)
            base["tier"] = tier
            pending.append(base)
            if six["met"]:
                decision_ready.append({
                    "canonical_event_id": ceid,
                    "title": base["title"],
                    "role": role,
                    "tier": tier,
                })

    # —— 分桶计数 ——
    by_tier = {t: 0 for t in TIER_RANK}
    for p in pending:
        by_tier[p["tier"]] += 1
    # —— 分角色计数（§9.4 新增）——
    by_role = {r: 0 for r in ROLE_FROZEN}
    by_role["other"] = 0
    for p in pending:
        by_role[p["role"]] = by_role.get(p["role"], 0) + 1

    # —— 排名靠前的待决（供 Executive Home）——
    top_pending = sorted(
        pending, key=lambda p: ((p.get("meets_six") is True), TIER_RANK.get(p["tier"], 0), p["priority"]), reverse=True
    )[:TOP_PENDING]

    decided_sample = len(ledger_entries or [])
    reached = decided_sample >= MIN_SAMPLE

    open_questions: list[dict] = []
    if not reached:
        open_questions.append({
            "dimension": "决策偏好结论",
            "status": "insufficient_sample",
            "reason": f"E2 决策账本去重样本 {decided_sample} < {MIN_SAMPLE}，无法得出「哪类事件更易被决策」的结论",
            "unblock": "持续运行流水线自然累积至 ≥30 后，方可在 Personal Memory / Second Brain 产出偏好结论",
        })
    # 六条件缺口（observation，非结论）
    bottleneck = {str(k): six_failed_counter.get(k, 0) for k in (1, 2, 3, 4, 5, 6)}
    open_questions.append({
        "dimension": "六条件硬化（决策门）",
        "status": "evaluated",
        "reason": f"待决 {len(pending)} 条中真正达到六条件决策门 {len(decision_ready)} 条；各条件未达计数 {bottleneck}。"
                   "单源+监管/评级按纪律不进入 decision_ready。",
        "unblock": "六条件为可观测评估注解；decision_ready 子集供优先拍板，其余仍留 Human Review",
    })
    open_questions.append({
        "dimension": "待决分桶紧急度",
        "status": "observation_proxy",
        "reason": "待决事件无人类紧急度标签（标签仅在决策后存在）；now/soon/watch 由 review 原因 + 优先级派生",
        "unblock": "漏斗分桶为可观测代理，不改写 Human Review 的业务判断",
    })
    open_questions.append({
        "dimension": "已决集合来源",
        "status": "honest_merge",
        "reason": "已决 = 决策账本 event_id ∪ review_queue.decision；仅真实决策记录，无制造时间戳",
        "unblock": "Human Review 持续落 decision 后，账本样本增长、时间线收敛",
    })

    return {
        "version": VERSION,
        "generated_at": generated_at or _now(),
        "principle": "待决策洪流 → 漏斗（now/soon/watch）+ 排名靠前的待决；"
                    "已决只来自真实决策记录；六条件硬化为每条待决的注解 + decision_ready 子集；"
                    "分角色计数；样本<30 不结论；分桶为可观测代理",
        "meta": {
            "total_review_queue": len(review_items or []),
            "non_pending": non_pending,
            "decision_required": len(required),
            "decided": len(decided),
            "pending": len(pending),
            "pending_by_tier": by_tier,
            "pending_by_role": by_role,
            "decision_ready": len(decision_ready),
            "decision_ready_ceids": [d["canonical_event_id"] for d in decision_ready[:TOP_PENDING]],
            "six_failed_counter": {str(k): six_failed_counter.get(k, 0) for k in (1, 2, 3, 4, 5, 6)},
            "decided_sample_size": decided_sample,
            "reached_threshold": reached,
            "min_sample": MIN_SAMPLE,
            "consistency": "decision_required == decided + pending",
        },
        "funnel": {
            "now": [p for p in pending if p["tier"] == "now"],
            "soon": [p for p in pending if p["tier"] == "soon"],
            "watch": [p for p in pending if p["tier"] == "watch"],
        },
        "top_pending": top_pending,
        "decided_list": decided,
        "open_questions": open_questions,
    }


def _tier_of(reason_types: set[str], priority: int) -> str:
    """待决分桶：可观测代理（非业务判断）。

    - now：冲突类原因（conflict / claim_conflict）→ 需人工裁决。
    - soon：优先级高（>=75）或含 change_impact / evidence 原因（实质变化需复核）。
    - watch：其余（多为 event_cluster 聚类，低利害）。
    """
    if reason_types & CONFLICT_REASONS:
        return "now"
    if priority >= 75 or ("change_impact" in reason_types) or ("evidence" in reason_types):
        return "soon"
    return "watch"


def validate(doc: dict) -> None:
    assert doc.get("version") == VERSION, doc.get("version")
    meta = doc.get("meta") or {}
    req = meta.get("decision_required", 0)
    decided = meta.get("decided", 0)
    pending = meta.get("pending", 0)
    assert req == decided + pending, f"计数不自洽：decision_required({req}) != decided({decided}) + pending({pending})"
    by_tier = meta.get("pending_by_tier") or {}
    assert sum(by_tier.values()) == pending, f"分桶计数({sum(by_tier.values())}) != pending({pending})"
    # 分角色计数自洽
    by_role = meta.get("pending_by_role") or {}
    assert sum(by_role.values()) == pending, f"分角色计数({sum(by_role.values())}) != pending({pending})"
    funnel = doc.get("funnel") or {}
    for tier in ("now", "soon", "watch"):
        for p in funnel.get(tier, []):
            assert p.get("canonical_event_id"), "待决项缺少 canonical_event_id"
            assert p.get("tier") in TIER_RANK, f"非法分桶：{p.get('tier')}"
            assert p.get("role") in ROLE_LABEL, f"非法角色：{p.get('role')}"
    for d in doc.get("decided_list", []):
        assert d.get("canonical_event_id"), "已决项缺少 canonical_event_id"
    for p in doc.get("top_pending", []):
        for f in ("tier", "canonical_event_id", "title", "topic", "priority", "trust_level", "reason_types", "role", "meets_six", "failed_conditions"):
            assert f in p, f"top_pending 项缺字段 {f}: {p.get('title','?')}"
    assert isinstance(doc.get("top_pending"), list), "top_pending 必须为列表"
    assert doc.get("open_questions"), "open_questions 不得为空"


def run(persist: bool = True) -> dict[str, Any]:
    review = _load(REVIEW)
    ledger = _load(LEDGER)
    intel = _load(INTEL)
    canonical = _load(CANONICAL)
    alerts = _load(ALERTS)
    state = _load(STATE)

    review_items = review.get("items") or []
    ledger_entries = ledger.get("entries") or []
    intel_events = intel.get("events") or []
    ceid_map = _ceid_by_event(canonical)

    alert_list = alerts.get("semantic_alerts") or []
    alert_ceids = {a.get("canonical_event_id") for a in alert_list}
    t1_alert_ceids = {a.get("canonical_event_id") for a in alert_list if a.get("admission") == "T1_system"}

    # 冻结 watchlist 的关注面（enabled 才计入）
    watch_topics: set[str] = set()
    watch_kw: set[str] = set()
    for w in (state.get("watchlists") or []):
        if not w.get("enabled", True):
            continue
        for t in (w.get("topics") or []):
            watch_topics.add(t)
        for k in (w.get("keywords") or []):
            watch_kw.add(k)

    # 反馈状态（E3）：ceid → status（snoozed/resolved 视为已处理）
    feedback_status_by_ceid: dict[str, str] = {}
    for fb in (state.get("feedback") or []):
        eid = fb.get("event_id")
        cid = ceid_map.get(eid, eid)
        st = fb.get("status")
        if cid and st:
            feedback_status_by_ceid[cid] = st

    doc = build(
        review_items, ledger_entries, intel_events, canonical, alert_ceids, t1_alert_ceids,
        watch_topics, watch_kw, feedback_status_by_ceid, ceid_map,
    )
    validate(doc)

    if persist:
        OUTPUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return doc


def main() -> None:
    parser = argparse.ArgumentParser(description="S5 决策漏斗：收敛待决策洪流为可管理漏斗（六条件硬化 + 分角色计数）")
    parser.add_argument("--no-persist", action="store_true", help="只计算不写文件")
    args = parser.parse_args()
    doc = run(persist=not args.no_persist)
    print(json.dumps({
        "decision_required": doc["meta"]["decision_required"],
        "decided": doc["meta"]["decided"],
        "pending": doc["meta"]["pending"],
        "pending_by_tier": doc["meta"]["pending_by_tier"],
        "pending_by_role": doc["meta"]["pending_by_role"],
        "decision_ready": doc["meta"]["decision_ready"],
        "decided_sample_size": doc["meta"]["decided_sample_size"],
        "reached_threshold": doc["meta"]["reached_threshold"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
