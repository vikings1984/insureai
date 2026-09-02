#!/usr/bin/env python3
"""S6 Replay / Projection：每 canonical event 的生命周期变化链（回放）。

回答「为何今天变重要」——但**只基于真实累积的历史快照**，绝不伪造跨期变化：
- 提供 `p2_stage_history.json` 累计器：按运行日期逐 canonical event 记录
  stage / 证据数 / 主张数 / 信息源数 / 信任分（同一天重跑则覆盖，不去重叠加）。
- 首跑仅播种历史（链长=1），明确标注「首次观测、暂无跨期变化」；次日起产生真实跃迁。
- next_stage_projection 为**生命周期固定顺序的下一阶段**（可观测事实），明确标注「非预测」。

纪律（与 S1–S5、P2 一致）：
- fail-closed：version 校验；每条回放必含 canonical_event_id / replay_chain / current_stage。
- observation/conclusion 分离：why_important_today 由历史差值派生；投影为顺序事实；不足则 open_questions。
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
LIFECYCLE = ROOT / "lifecycle_report.json"
INTEL = ROOT / "intelligence.json"
CANONICAL = ROOT / "canonical_events.json"
HISTORY = ROOT / "p2_stage_history.json"
OUTPUT = ROOT / "event_replays.json"

VERSION = "replay-v1.0"
HISTORY_VERSION = "history-v1.0"

# 并购生命周期固定顺序（数值越大越接近交割/整合）
STAGE_ORDER = ["rumor", "negotiation", "agreement", "regulatory", "closing", "integration"]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _ceid_by_event(canonical: dict) -> dict[str, str]:
    return {k: v for k, v in (canonical.get("by_event_id") or {}).items()}


def current_snapshot(events: list[dict], lifecycle_entries: list[dict],
                     ceid_map: dict[str, str], run_date: str) -> dict[str, dict]:
    """构造「本次运行」逐 canonical event 快照（供历史累计）。"""
    ev_by_ceid: dict[str, dict] = {}
    for ev in events or []:
        eid = ev.get("event_id")
        if not eid:
            continue
        ceid = ceid_map.get(eid, eid)
        trust = ev.get("trust") or {}
        claims = ev.get("claims") or {}
        ev_by_ceid[ceid] = {
            "evidence_count": len(ev.get("evidence") or []),
            "proposition_count": (claims.get("proposition_count") if isinstance(claims.get("proposition_count"), int) else 0),
            "source_count": ev.get("source_count") or 0,
            "trust_score": trust.get("score"),
        }
    snap: dict[str, dict] = {}
    for e in lifecycle_entries or []:
        ceid = e.get("canonical_event_id")
        if not ceid:
            continue
        base = ev_by_ceid.get(ceid, {})
        snap[ceid] = {
            "date": run_date,
            "stage": e.get("stage") or "n/a",
            "evidence_count": base.get("evidence_count", 0),
            "proposition_count": base.get("proposition_count", 0),
            "source_count": base.get("source_count", 0),
            "trust_score": base.get("trust_score"),
        }
    return snap


def append_history(prior: dict[str, list[dict]], current: dict[str, dict], run_date: str) -> dict[str, list[dict]]:
    """按日期累积快照（同日覆盖，不去重叠加）。"""
    history: dict[str, list[dict]] = {k: list(v) for k, v in (prior or {}).items()}
    for ceid, snap in current.items():
        lst = history.setdefault(ceid, [])
        replaced = False
        for i, old in enumerate(lst):
            if old.get("date") == run_date:
                lst[i] = snap
                replaced = True
                break
        if not replaced:
            lst.append(snap)
    return history


def _stage_index(stage: str) -> int:
    """生命周期阶段序号；非并购/未知阶段（n/a）返回 -1 表示不适用。

    n/a 事件（占多数）不参与「阶段前移」判定——否则 STAGE_ORDER.index('n/a') 会抛
    ValueError，导致次日回放整体崩溃（此前的真实缺陷）。
    """
    try:
        return STAGE_ORDER.index(stage)
    except (ValueError, TypeError):
        return -1


def _why_important(cur: dict, prev: dict | None) -> str:
    """由真实历史差值派生「为何今天变重要」；首观测或无变化则如实说明。"""
    if prev is None:
        return f"首次观测（stage={cur['stage']}），暂无跨期变化"
    parts: list[str] = []
    ci, pi = _stage_index(cur["stage"]), _stage_index(prev["stage"])
    if ci >= 0 and pi >= 0 and ci > pi:
        parts.append(f"阶段前移 {prev['stage']}→{cur['stage']}")
    ev_delta = (cur.get("evidence_count") or 0) - (prev.get("evidence_count") or 0)
    prop_delta = (cur.get("proposition_count") or 0) - (prev.get("proposition_count") or 0)
    if ev_delta + prop_delta >= 3:
        parts.append(f"证据/主张实质新增 +{ev_delta + prop_delta}")
    elif ev_delta > 0:
        parts.append(f"证据 +{ev_delta}")
    src_delta = (cur.get("source_count") or 0) - (prev.get("source_count") or 0)
    if src_delta > 0:
        parts.append(f"信息源 +{src_delta}")
    if not parts:
        return "无显著跨期变化"
    return "；".join(parts) + f"（{cur['date']}）"


def _next_stage(stage: str) -> str | None:
    """生命周期固定顺序的下一阶段（可观测事实，非预测）。"""
    if stage not in STAGE_ORDER:
        return None
    idx = STAGE_ORDER.index(stage)
    if idx >= len(STAGE_ORDER) - 1:
        return None
    return STAGE_ORDER[idx + 1]


def build_replays(history: dict[str, list[dict]], lifecycle_entries: list[dict],
                  ceid_map: dict[str, str], intel_events: list[dict]) -> list[dict]:
    topic_map: dict[str, str] = {}
    for ev in intel_events or []:
        ceid = ceid_map.get(ev.get("event_id"), ev.get("event_id"))
        if ev.get("topic"):
            topic_map.setdefault(ceid, ev["topic"])
    lc_by_ceid = {e.get("canonical_event_id"): e for e in (lifecycle_entries or []) if e.get("canonical_event_id")}

    replays: list[dict] = []
    for ceid, chain in history.items():
        chain = sorted(chain, key=lambda s: s.get("date") or "")
        transitions: list[dict] = []
        for i in range(1, len(chain)):
            if chain[i]["stage"] != chain[i - 1]["stage"]:
                transitions.append({
                    "date": chain[i]["date"],
                    "from": chain[i - 1]["stage"],
                    "to": chain[i]["stage"],
                })
        cur = chain[-1]
        prev = chain[-2] if len(chain) >= 2 else None
        nxt = _next_stage(cur["stage"])
        lc = lc_by_ceid.get(ceid) or {}
        replays.append({
            "canonical_event_id": ceid,
            "event_id": lc.get("identity_key"),
            "title": lc.get("title") or cur.get("title"),
            "topic": topic_map.get(ceid),
            "current_stage": cur["stage"],
            "first_seen": chain[0]["date"],
            "last_seen": cur["date"],
            "snapshot_count": len(chain),
            "replay_chain": chain,
            "transitions": transitions,
            "why_important_today": _why_important(cur, prev),
            "next_stage_projection": {
                "stage": nxt,
                "basis": "生命周期固定顺序的下一阶段（非预测）" if nxt else "不适用（非 M&A 或已至末端）",
            },
        })
    # 有跃迁的优先，其次快照数多者优先
    replays.sort(key=lambda r: (len(r["transitions"]) > 0, r["snapshot_count"]), reverse=True)
    return replays


def build(events: list[dict], lifecycle_entries: list[dict], canonical_events: dict,
          ceid_map: dict[str, str], generated_at: str | None = None,
          run_date: str | None = None, prior_history: dict[str, list[dict]] | None = None) -> dict[str, Any]:
    run_date = run_date or _today()
    current = current_snapshot(events, lifecycle_entries, ceid_map, run_date)
    history = append_history(prior_history or {}, current, run_date)
    replays = build_replays(history, lifecycle_entries, ceid_map, events)

    by_stage: dict[str, int] = {}
    with_transitions = 0
    for r in replays:
        by_stage[r["current_stage"]] = by_stage.get(r["current_stage"], 0) + 1
        if r["transitions"]:
            with_transitions += 1

    open_questions: list[dict] = []
    seeded = sum(1 for r in replays if r["snapshot_count"] == 1)
    if seeded == len(replays):
        open_questions.append({
            "dimension": "跨期回放（replay）",
            "status": "seeded_first_run",
            "reason": "历史累计器首跑仅播种当前快照，暂无跨期阶段跃迁/证据变化可回放",
            "unblock": "后续每日运行追加快照后，阶段跃迁与证据增长将真实显现",
        })
    else:
        open_questions.append({
            "dimension": "跨期回放（replay）",
            "status": "accumulating",
            "reason": f"已累积 {len(replays) - seeded} 个事件的多日快照，跃迁 {with_transitions} 个",
            "unblock": "持续运行扩展历史纵深",
        })
    open_questions.append({
        "dimension": "next_stage 投影",
        "status": "observation_only",
        "reason": "next_stage_projection 仅为生命周期固定顺序的下一阶段，非预测、不改写业务判断",
        "unblock": "Human Review 仍依实际进展确认阶段演进",
    })

    return {
        "version": VERSION,
        "generated_at": generated_at or _now(),
        "run_date": run_date,
        "principle": "回放只基于真实累积历史；首跑仅播种、不伪造跃迁；next_stage 为顺序事实、非预测",
        "meta": {
            "total_canonical": len(replays),
            "with_history_multi_day": len(replays) - seeded,
            "with_transitions": with_transitions,
            "by_current_stage": by_stage,
        },
        "history": history,
        "replays": replays,
        "open_questions": open_questions,
    }


def validate(doc: dict) -> None:
    assert doc.get("version") == VERSION, doc.get("version")
    assert isinstance(doc.get("history"), dict), "history 必须为字典"
    for r in doc.get("replays") or []:
        assert r.get("canonical_event_id"), "回放缺少 canonical_event_id"
        assert isinstance(r.get("replay_chain"), list) and r["replay_chain"], "replay_chain 必须为非空列表"
        assert r.get("current_stage") in (STAGE_ORDER + ["n/a"]), f"非法阶段：{r.get('current_stage')}"
        assert isinstance(r.get("transitions"), list), "transitions 必须为列表"
        assert r.get("next_stage_projection") and "basis" in r["next_stage_projection"], "next_stage_projection 缺少 basis"
    assert doc.get("open_questions"), "open_questions 不得为空"


def run(persist: bool = True) -> dict[str, Any]:
    lifecycle = _load(LIFECYCLE)
    intel = _load(INTEL)
    canonical = _load(CANONICAL)
    lifecycle_entries = lifecycle.get("entries") or []
    events = intel.get("events") or []
    ceid_map = _ceid_by_event(canonical)

    prior = _load(HISTORY).get("history") if HISTORY.exists() else None
    doc = build(events, lifecycle_entries, canonical, ceid_map, prior_history=prior)
    validate(doc)

    if persist:
        # 历史累计器独立持久化（供次日追加）
        hist_doc = {
            "version": HISTORY_VERSION,
            "updated_at": doc["generated_at"],
            "history": doc["history"],
        }
        HISTORY.write_text(json.dumps(hist_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        OUTPUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return doc


def main() -> None:
    parser = argparse.ArgumentParser(description="S6 回放/投影：逐 canonical event 生命周期变化链")
    parser.add_argument("--no-persist", action="store_true", help="只计算不写文件")
    args = parser.parse_args()
    doc = run(persist=not args.no_persist)
    print(json.dumps({
        "total_canonical": doc["meta"]["total_canonical"],
        "with_transitions": doc["meta"]["with_transitions"],
        "by_current_stage": doc["meta"]["by_current_stage"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
