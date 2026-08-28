#!/usr/bin/env python3
"""P2: Daily Intelligence -> Watchlist -> Monitoring -> Decision Feedback.

Dependency-free orchestration layer over the existing deterministic intelligence
engine. It deliberately keeps user preferences, monitoring state and feedback
separate from the source/event model so that later storage or API layers can
replace the JSON persistence without changing scoring semantics.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from intelligence import build as build_intelligence

ROOT = Path(__file__).resolve().parent
STATE_PATH = Path(os.environ.get("INSUREAI_P2_STATE", ROOT / "p2_state.json"))
OUTPUT_PATH = ROOT / "p2_daily_brief.json"
BRIEF_LIMIT = 20

DEFAULT_STATE = {
    "version": "p2-v1.0",
    "watchlists": [],
    "feedback": [],
    "monitoring": [],
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return json.loads(json.dumps(DEFAULT_STATE))
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_news(path: str | Path) -> list[dict]:
    """Return the article list from a production data file.

    `data.json` is a dict (`{"news": [...], "sources": [...], ...}`), while
    callers and tests pass a bare article list. Normalise both so the
    intelligence engine always receives `list[dict]`.
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw = raw.get("news", [])
    if not isinstance(raw, list):
        raise ValueError(f"unsupported news payload: {type(raw).__name__}")
    return [x for x in raw if isinstance(x, dict)]


def _match_watchlist(event: dict, watchlist: dict) -> bool:
    # `topic` is deliberately excluded from the keyword haystack: topics are
    # machine slugs such as `ai_intelligent`, so folding them in made every
    # keyword (e.g. "AI") match its own topic slug and turned a topic-scoped
    # watchlist into "every event in that topic".
    text = " ".join([
        event.get("title") or "",
        event.get("summary") or "",
        " ".join(event.get("entities") or []),
    ]).lower()
    keywords = [str(x).lower() for x in (watchlist.get("keywords") or [])]
    topics = {str(x) for x in (watchlist.get("topics") or [])}
    topic_ok = not topics or event.get("topic") in topics
    keyword_ok = not keywords or any(k in text for k in keywords)
    return topic_ok and keyword_ok


def _intelligence_score(event: dict) -> int:
    """Read the intelligence score from the engine's canonical location.

    The engine emits `event["scores"]["intelligence_score"]`. A top-level
    fallback is kept only for hand-built fixtures.
    """
    scores = event.get("scores")
    if isinstance(scores, dict) and scores.get("intelligence_score") is not None:
        return int(scores["intelligence_score"])
    return int(event.get("intelligence_score") or 0)


def _priority(event: dict, watchlist: dict | None = None) -> int:
    score = _intelligence_score(event)
    if watchlist:
        score += int(watchlist.get("priority_boost") or 0)
    return min(100, score)


def _feedback_boost(event_id: str, feedback: list[dict]) -> int:
    rows = [x for x in feedback if x.get("event_id") == event_id]
    if not rows:
        return 0
    useful = sum(1 for x in rows if x.get("label") in {"useful", "important"})
    noise = sum(1 for x in rows if x.get("label") in {"noise", "irrelevant"})
    return max(-15, min(15, useful * 5 - noise * 5))


def daily_brief(news: list[dict], state: dict) -> dict:
    intelligence = build_intelligence({"news": news})
    events = intelligence.get("events", [])
    rows = []
    for event in events:
        matched = [w for w in state.get("watchlists", []) if w.get("enabled", True) and _match_watchlist(event, w)]
        best_watch = max(matched, key=lambda x: int(x.get("priority_boost") or 0), default=None)
        score = min(100, _priority(event, best_watch) + _feedback_boost(event.get("event_id", ""), state.get("feedback", [])))
        item = dict(event)
        item["daily_priority"] = score
        item["watchlist_matches"] = [w.get("id") for w in matched]
        rows.append(item)
    rows.sort(key=lambda x: (x.get("daily_priority", 0), _intelligence_score(x)), reverse=True)
    return {
        "version": "p2-v1.0",
        "generated_at": now(),
        "brief": rows[:BRIEF_LIMIT],
        "watchlist_hits": sum(1 for x in rows if x.get("watchlist_matches")),
        "event_count": len(rows),
        "feedback_applied": len(state.get("feedback", [])),
    }


def upsert_watchlist(state: dict, watchlist: dict) -> dict:
    required = {"id", "name"}
    missing = required - set(watchlist)
    if missing:
        raise ValueError(f"watchlist missing: {sorted(missing)}")
    watchlist = {**watchlist, "enabled": watchlist.get("enabled", True), "updated_at": now()}
    state["watchlists"] = [x for x in state.get("watchlists", []) if x.get("id") != watchlist["id"]]
    state["watchlists"].append(watchlist)
    save_state(state)
    return watchlist


def record_feedback(state: dict, event_id: str, label: str, note: str = "") -> dict:
    allowed = {"useful", "important", "noise", "irrelevant", "incorrect", "acted_on"}
    if label not in allowed:
        raise ValueError(f"label must be one of {sorted(allowed)}")
    row = {"event_id": event_id, "label": label, "note": note, "created_at": now()}
    state.setdefault("feedback", []).append(row)
    save_state(state)
    return row


def register_monitor(state: dict, watchlist_id: str, event_id: str, status: str = "active") -> dict:
    if status not in {"active", "resolved", "snoozed"}:
        raise ValueError("status must be active, resolved or snoozed")
    row = {"watchlist_id": watchlist_id, "event_id": event_id, "status": status, "updated_at": now()}
    state["monitoring"] = [x for x in state.get("monitoring", []) if not (x.get("watchlist_id") == watchlist_id and x.get("event_id") == event_id)]
    state["monitoring"].append(row)
    save_state(state)
    return row


def run(news: list[dict], state: dict | None = None) -> dict:
    state = state or load_state()
    result = daily_brief(news, state)
    OUTPUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--news", default=str(ROOT / "data.json"))
    parser.add_argument("--watchlist", help="JSON object to upsert")
    parser.add_argument("--feedback", nargs=3, metavar=("EVENT_ID", "LABEL", "NOTE"))
    parser.add_argument("--monitor", nargs=2, metavar=("WATCHLIST_ID", "EVENT_ID"))
    args = parser.parse_args()
    state = load_state()
    if args.watchlist:
        upsert_watchlist(state, json.loads(args.watchlist))
    if args.feedback:
        record_feedback(state, args.feedback[0], args.feedback[1], args.feedback[2])
    if args.monitor:
        register_monitor(state, args.monitor[0], args.monitor[1])
    news = load_news(args.news)
    result = run(news, state)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
