#!/usr/bin/env python3
"""P2.1 Continuous Monitoring — 跨天稳定事件身份 + 变化检测 + 告警去重。

背景（为什么需要这一层）
------------------------
引擎每次 `build()` 都用当天文章重算事件，事件 ID 是
`"evt_" + 内容哈希(领衔文章)`，对*正在发展的故事*不稳定：每天新增报道会让
领衔文章变化 → 哈希变化 → `event_id` 变化。而 `p2_state.json` 里的
`monitoring` 列表只是 CLI 手动书签，`daily_brief` 从不读取它。

因此"持续监控某事件的状态变化并主动告警"在原来的 `event_id` 上无法锚定。
本模块用引擎已算出的 `event_fingerprint`（= 锚定实体+动作类型+主题+年月的
哈希）作为**跨天稳定身份**——同一公司、同一动作、同一个月内恒定不变，覆盖绝大多数
发展型故事；跨月连续性通过实体锚定 + 相似度匹配上一层（见 `resolve_canonical`）。

本模块是**增量**的：读取引擎事件列表 + 持久化的监控 store，产出变化记录与告警，
不修改引擎、也不修改每日简报。

设计取舍（待 Vikings 决策）
--------------------------
- 事件"生命周期状态"（rumor→preferred→agreement→approval→closing→integration）
  这里**不硬编码枚举**，而是从可观测信号派生（证据状态、复核开关、评分、实体增长）。
  硬编码生命周期属于域模型，应由业务拍板。
- 告警只在"事件命中启用中的关注清单"或"被 active 监控"时产生；snoozed/resolved
  的监控项抑制告警（复用 p2_intelligence 的监控语义）。
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from intelligence import _event_similarity
from p2_intelligence import _match_watchlist, load_state

ROOT = Path(__file__).resolve().parent
# store（跨天持久化的 seen/alert_history）与每轮输出报告必须分文件，
# 否则报告会覆盖 store，导致下一轮连续性丢失。
STORE_PATH = Path(os.environ.get("INSUREAI_P2_MONITOR", ROOT / "p2_monitoring_store.json"))
OUTPUT_PATH = ROOT / "p2_monitoring.json"
LINK_THRESHOLD = 0.35  # 跨月联动所需的最低事件相似度（中文标题 token 粗，阈值低于引擎聚类）
ENTITY_LINK_THRESHOLD = 0.5  # 跨月联动的实体重叠下限（发展型故事保留多数实体）
LINK_WINDOW_DAYS = 30  # 监控联动的回看窗口（远宽于引擎 96h 聚类窗，因已知实体）
ALERT_HISTORY_LIMIT = 200

DEFAULT_STORE: dict[str, Any] = {
    "version": "p2.1-v1.0",
    "seen": {},          # canonical_id -> 上次见到的事件快照
    "alert_history": [],  # 近期已告警的 dedup_key，用于去重
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_store() -> dict[str, Any]:
    if not STORE_PATH.exists():
        return json.loads(json.dumps(DEFAULT_STORE))
    return json.loads(STORE_PATH.read_text(encoding="utf-8"))


def save_store(store: dict[str, Any]) -> None:
    STORE_PATH.write_text(json.dumps(store, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _intel_score(event: dict) -> int:
    return int((event.get("scores") or {}).get("intelligence_score") or 0)


def _snapshot(event: dict, canonical_id: str) -> dict:
    """压缩存储一个事件的关键可监控字段，作为跨天比对的基准。"""
    return {
        "canonical_id": canonical_id,
        "title": event.get("title"),
        "event_type": event.get("event_type"),
        "topic": event.get("topic"),
        "published_at": event.get("published_at"),
        "article_count": int(event.get("article_count") or 0),
        "source_count": int(event.get("source_count") or 0),
        "intelligence_score": _intel_score(event),
        "evidence_status": event.get("evidence_status"),
        "review_required": bool(event.get("review_required")),
        "trust_level": (event.get("trust") or {}).get("level"),
        "entities": list(event.get("entities") or []),
        "last_seen": now(),
    }


def build_today_map(events: list[dict]) -> dict[str, dict]:
    """按 `event_fingerprint` 分组，取每组评分最高的事件作为代表。

    `event_fingerprint` 即跨天稳定身份（同公司/动作/主题/月恒定）。
    """
    groups: dict[str, list[dict]] = {}
    for ev in events:
        fp = ev.get("event_fingerprint") or ev.get("event_id")
        if not fp:
            continue
        groups.setdefault(fp, []).append(ev)
    out: dict[str, dict] = {}
    for fp, evs in groups.items():
        out[fp] = max(evs, key=_intel_score)
    return out


def _within_link_window(a: dict, b: dict, days: int = LINK_WINDOW_DAYS) -> bool:
    """监控联动的回看窗口：已知实体前提下放宽到约 30 天。

    引擎的 96h 聚类窗只适用于「当天新稿件并入聚类」，对跨周/跨月发展的
    同一事件过严，会永远联动不上。
    """
    try:
        ta = datetime.fromisoformat((a.get("published_at") or "").replace("Z", "+00:00")).astimezone(timezone.utc)
        tb = datetime.fromisoformat((b.get("published_at") or "").replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return True
    return abs((ta - tb).total_seconds()) <= days * 86400


def _entity_overlap(a: dict, b: dict) -> float:
    """直接用双方已持久化的 entities 列表算 Jaccard，避免重新抽取导致失真。

    快照只存了顶层 entities，引擎的 `_entity_similarity` 会从 tags/标题重抽，
    快照缺 tags 时会丢实体、把重叠算高，引发误联动。
    """
    sa = set(a.get("entities") or [])
    sb = set(b.get("entities") or [])
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def resolve_canonical(today_map: dict[str, dict], seen: dict[str, dict]) -> dict[str, str]:
    """为本月新出现的 fingerprint 寻找跨月延续的旧 canonical_id。

    仅当：实体重叠 >= 阈值、回看窗口内、事件相似度 >= LINK_THRESHOLD 时联动。
    返回 {fingerprint: canonical_id}。
    """
    mapping = {fp: fp for fp in today_map}
    if not seen:
        return mapping
    seen_items = list(seen.values())
    for fp, ev in today_map.items():
        if fp in seen:
            continue  # 本月已认识的，直接用自身
        best_cid = None
        best_score = 0.0
        for s in seen_items:
            if not _within_link_window(ev, s):
                continue
            # 用实体重叠门禁代替脆弱的「锚定首实体」（泛词如 "AI" 会排第一导致误锚）
            if _entity_overlap(ev, s) < ENTITY_LINK_THRESHOLD:
                continue
            sc = _event_similarity(ev, s)
            if sc > best_score:
                best_score = sc
                best_cid = s.get("canonical_id")
        if best_cid and best_score >= LINK_THRESHOLD:
            mapping[fp] = best_cid
    return mapping


def _change(canonical_id: str, event: dict, change_type: str,
            prev: dict | None, cur: dict, detail: dict | None = None) -> dict:
    return {
        "canonical_id": canonical_id,
        "title": event.get("title"),
        "event_type": event.get("event_type"),
        "topic": event.get("topic"),
        "change_type": change_type,
        "prev": prev,
        "now": cur,
        "detail": detail or {},
        "generated_at": now(),
    }


def detect_changes(today_map: dict[str, dict], seen: dict[str, dict],
                   canonical_map: dict[str, str]) -> list[dict]:
    """比对当天事件与上次快照，产出变化记录。"""
    changes: list[dict] = []
    for fp, ev in today_map.items():
        cid = canonical_map.get(fp, fp)
        cur = _snapshot(ev, cid)
        prev = seen.get(cid)
        if prev is None:
            changes.append(_change(cid, ev, "NEW", None, cur))
            continue
        if cur["article_count"] > prev["article_count"]:
            changes.append(_change(cid, ev, "NEW_EVIDENCE", prev, cur,
                                   {"article_count": [prev["article_count"], cur["article_count"]]}))
        if cur["source_count"] > prev["source_count"]:
            changes.append(_change(cid, ev, "NEW_SOURCE", prev, cur,
                                   {"source_count": [prev["source_count"], cur["source_count"]]}))
        delta = cur["intelligence_score"] - prev["intelligence_score"]
        if delta > 0:
            changes.append(_change(cid, ev, "SEVERITY_UP", prev, cur, {"delta": delta}))
        elif delta < 0:
            changes.append(_change(cid, ev, "SEVERITY_DOWN", prev, cur, {"delta": delta}))
        single = {"single_source", "unverified", None}
        if prev["evidence_status"] in single and cur["evidence_status"] in {"multi_source", "verified"}:
            changes.append(_change(cid, ev, "EVIDENCE_UPGRADED", prev, cur))
        if not prev["review_required"] and cur["review_required"]:
            changes.append(_change(cid, ev, "REVIEW_OPENED", prev, cur))
        new_entities = set(cur["entities"]) - set(prev["entities"])
        if new_entities:
            changes.append(_change(cid, ev, "NEW_ENTITY", prev, cur,
                                   {"added": sorted(new_entities)}))
        if prev["trust_level"] != cur["trust_level"]:
            changes.append(_change(cid, ev, "TRUST_CHANGE", prev, cur,
                                   {"from": prev["trust_level"], "to": cur["trust_level"]}))
    return changes


_SEVERITY = {
    "NEW_EVIDENCE": "high",
    "SEVERITY_UP": "high",
    "NEW_SOURCE": "high",
    "EVIDENCE_UPGRADED": "high",
    "NEW": "medium",
    "NEW_ENTITY": "medium",
    "REVIEW_OPENED": "medium",
    "TRUST_CHANGE": "medium",
    "SEVERITY_DOWN": "low",
}


def _event_from_change(ch: dict) -> dict:
    """从变化记录重建一个最小事件，供关注清单匹配使用。"""
    now_snap = ch.get("now") or {}
    return {
        "title": ch.get("title") or now_snap.get("title") or "",
        "summary": "",
        "entities": now_snap.get("entities") or [],
        "topic": ch.get("topic") or now_snap.get("topic"),
    }


def filter_alerts(changes: list[dict], state: dict, store: dict) -> list[dict]:
    """只对被关注 / 被 active 监控的事件告警；snoozed/resolved 抑制；去重。"""
    watchlists = [w for w in state.get("watchlists", []) if w.get("enabled", True)]
    monitors = state.get("monitoring", [])
    known_alerts = set(store.get("alert_history", []))
    alerts: list[dict] = []
    for ch in changes:
        cid = ch["canonical_id"]
        watched = False
        watch_id = None
        for w in watchlists:
            if _match_watchlist(_event_from_change(ch), w):
                watched = True
                watch_id = w.get("id")
                break
        mon = [m for m in monitors if m.get("event_id") == cid]
        suppressed = any(m.get("status") in {"snoozed", "resolved"} for m in mon)
        actively_monitored = any(m.get("status") == "active" for m in mon)
        if suppressed:
            continue
        if not (watched or actively_monitored):
            continue
        dedup = f"{cid}|{ch['change_type']}"
        if dedup in known_alerts:
            continue
        alerts.append({
            "canonical_id": cid,
            "title": ch["title"],
            "watchlist_id": watch_id,
            "change_type": ch["change_type"],
            "severity": _SEVERITY.get(ch["change_type"], "medium"),
            "detail": ch.get("detail"),
            "generated_at": ch["generated_at"],
            "dedup_key": dedup,
        })
    return alerts


def run_monitoring(events: list[dict], state: dict | None = None,
                   store: dict | None = None, persist: bool = True) -> dict:
    state = state or load_state()
    store = store or load_store()
    today_map = build_today_map(events)
    canonical_map = resolve_canonical(today_map, store.get("seen", {}))
    changes = detect_changes(today_map, store.get("seen", {}), canonical_map)
    alerts = filter_alerts(changes, state, store)

    # 更新 store：seen 用当天快照覆盖；alert_history 追加并裁剪
    new_seen = {canonical_map.get(fp, fp): _snapshot(ev, canonical_map.get(fp, fp))
                for fp, ev in today_map.items()}
    store["seen"] = new_seen
    hist = list(store.get("alert_history", [])) + [a["dedup_key"] for a in alerts]
    store["alert_history"] = hist[-ALERT_HISTORY_LIMIT:]

    result = {
        "version": "p2.1-v1.0",
        "generated_at": now(),
        "tracked_event_count": len(new_seen),
        "change_count": len(changes),
        "alert_count": len(alerts),
        "changes": changes,
        "alerts": alerts,
    }
    if persist:
        save_store(store)
        (ROOT / "p2_monitoring.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--news", default=str(ROOT / "data.json"),
                        help="生产数据文件（含 news），将经引擎 build")
    parser.add_argument("--events", help="已构建的 intelligence 事件 JSON（含 events 数组）")
    args = parser.parse_args()
    if args.events:
        raw = json.loads(Path(args.events).read_text(encoding="utf-8"))
        events = raw.get("events", []) if isinstance(raw, dict) else raw
    else:
        from intelligence import build
        from p2_intelligence import load_news
        events = build({"news": load_news(args.news)}).get("events", [])
    result = run_monitoring(events)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
