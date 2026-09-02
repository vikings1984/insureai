#!/usr/bin/env python3
"""S5 Decision Funnel：把 review_queue 的「待决策」洪流收敛为可管理的漏斗。

承接 E2 决策账本（decisions_ledger.json，含真实 decided_at + 去重样本）：
- 用账本 + review_queue.decision 标记「已决」事件（绝不伪造决策）。
- 其余「待决」事件按 review 原因 + 优先级派生紧急度分桶（now / soon / watch），
  作为可观测的代理（非业务判断；人类紧急度标签只在决策后存在）。
- 输出 decisions_pending.json：漏斗各层 + 排名靠前的待决清单（供 Executive Home X1）。

纪律（与 S1–S4、P2 一致）：
- fail-closed：decision_required == decided + pending；分桶计数自洽；每条必含 canonical_event_id。
- observation/conclusion 分离：待决分桶是事实代理；决策偏好结论在样本 <30 时显式阻断（open_questions）。
- 不伪造：已决集合只来自真实决策记录（账本 / review_queue.decision）；无制造的时间戳或补样本。
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REVIEW = ROOT / "review_queue.json"
LEDGER = ROOT / "decisions_ledger.json"
INTEL = ROOT / "intelligence.json"
CANONICAL = ROOT / "canonical_events.json"
OUTPUT = ROOT / "decisions_pending.json"

VERSION = "funnel-v1.0"
MIN_SAMPLE = 30
TOP_PENDING = 12

# 待决分桶（数值越大越紧急）
TIER_RANK = {"now": 2, "soon": 1, "watch": 0}
# review 原因中直接指向「需人工裁决」的冲突类
CONFLICT_REASONS = {"conflict", "claim_conflict"}


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


def _urgency_lookup(ledger_entries: list[dict], intel_decisions: list[dict]) -> dict[str, str]:
    out: dict[str, str] = {}
    for e in ledger_entries or []:
        eid = e.get("event_id")
        if eid and e.get("urgency"):
            out.setdefault(eid, e["urgency"])
    for d in intel_decisions or []:
        eid = d.get("event_id")
        if eid and d.get("urgency"):
            out.setdefault(eid, d["urgency"])
    return out


def _decided_at_lookup(ledger_entries: list[dict], review_items: list[dict]) -> dict[str, str]:
    out: dict[str, str] = {}
    for e in ledger_entries or []:
        eid = e.get("event_id")
        if eid and e.get("decided_at"):
            out[eid] = e["decided_at"]
    for i in review_items or []:
        d = i.get("decision")
        eid = i.get("event_id")
        if eid and isinstance(d, dict) and d.get("decided_at"):
            out.setdefault(eid, d["decided_at"])
    return out


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


def build(
    review_items: list[dict],
    ledger_entries: list[dict],
    intel_decisions: list[dict],
    ceid_map: dict[str, str],
    generated_at: str | None = None,
) -> dict[str, Any]:
    # —— 决策所需全集：review_queue 中 status=pending（需人工复核/决策）——
    required = [i for i in (review_items or []) if i.get("status") == "pending"]
    non_pending = len([i for i in (review_items or []) if i.get("status") != "pending"])

    # —— 已决事件集合（诚实来源：账本 ∪ review_queue.decision）——
    ledger_eids = {e.get("event_id") for e in (ledger_entries or []) if e.get("event_id")}
    decided_eids: set[str] = set(ledger_eids)
    for i in review_items or []:
        if isinstance(i.get("decision"), dict):
            decided_eids.add(i.get("event_id"))

    urgency = _urgency_lookup(ledger_entries, intel_decisions)
    decided_at = _decided_at_lookup(ledger_entries, review_items)

    pending: list[dict] = []
    decided: list[dict] = []
    for i in required:
        eid = i.get("event_id")
        if not eid:
            continue
        ceid = ceid_map.get(eid, eid)
        reasons = i.get("reasons") or []
        rtypes = {r.get("type") for r in reasons if isinstance(r, dict)}
        prio = i.get("priority") or 0
        is_decided = eid in decided_eids
        base = {
            "event_id": eid,
            "canonical_event_id": ceid,
            "title": i.get("title"),
            "topic": i.get("topic"),
            "priority": prio,
            "trust_level": i.get("trust_level"),
            "reason_types": sorted(rtypes),
            "urgency": urgency.get(eid),  # 已决才有人类紧急度标签
        }
        if is_decided:
            base["decided_at"] = decided_at.get(eid)
            decided.append(base)
        else:
            tier = _tier_of(rtypes, prio)
            base["tier"] = tier
            pending.append(base)

    # —— 分桶计数 ——
    by_tier = {t: 0 for t in TIER_RANK}
    for p in pending:
        by_tier[p["tier"]] += 1

    # —— 排名靠前的待决（供 Executive Home）——
    top_pending = sorted(
        pending, key=lambda p: (TIER_RANK.get(p["tier"], 0), p["priority"]), reverse=True
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
                    "已决只来自真实决策记录；样本<30 不结论；分桶为可观测代理",
        "meta": {
            "total_review_queue": len(review_items or []),
            "non_pending": non_pending,
            "decision_required": len(required),
            "decided": len(decided),
            "pending": len(pending),
            "pending_by_tier": by_tier,
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


def validate(doc: dict) -> None:
    assert doc.get("version") == VERSION, doc.get("version")
    meta = doc.get("meta") or {}
    req = meta.get("decision_required", 0)
    decided = meta.get("decided", 0)
    pending = meta.get("pending", 0)
    assert req == decided + pending, f"计数不自洽：decision_required({req}) != decided({decided}) + pending({pending})"
    by_tier = meta.get("pending_by_tier") or {}
    assert sum(by_tier.values()) == pending, f"分桶计数({sum(by_tier.values())}) != pending({pending})"
    funnel = doc.get("funnel") or {}
    for tier in ("now", "soon", "watch"):
        for p in funnel.get(tier, []):
            assert p.get("canonical_event_id"), "待决项缺少 canonical_event_id"
            assert p.get("tier") in TIER_RANK, f"非法分桶：{p.get('tier')}"
    for d in doc.get("decided_list", []):
        assert d.get("canonical_event_id"), "已决项缺少 canonical_event_id"
    assert isinstance(doc.get("top_pending"), list), "top_pending 必须为列表"
    assert doc.get("open_questions"), "open_questions 不得为空"


def run(persist: bool = True) -> dict[str, Any]:
    review = _load(REVIEW)
    ledger = _load(LEDGER)
    intel = _load(INTEL)
    canonical = _load(CANONICAL)
    review_items = review.get("items") or []
    ledger_entries = ledger.get("entries") or []
    intel_decisions = intel.get("decisions") or []
    ceid_map = _ceid_by_event(canonical)

    doc = build(review_items, ledger_entries, intel_decisions, ceid_map)
    validate(doc)

    if persist:
        OUTPUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return doc


def main() -> None:
    parser = argparse.ArgumentParser(description="S5 决策漏斗：收敛待决策洪流为可管理漏斗")
    parser.add_argument("--no-persist", action="store_true", help="只计算不写文件")
    args = parser.parse_args()
    doc = run(persist=not args.no_persist)
    print(json.dumps({
        "decision_required": doc["meta"]["decision_required"],
        "decided": doc["meta"]["decided"],
        "pending": doc["meta"]["pending"],
        "pending_by_tier": doc["meta"]["pending_by_tier"],
        "decided_sample_size": doc["meta"]["decided_sample_size"],
        "reached_threshold": doc["meta"]["reached_threshold"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
