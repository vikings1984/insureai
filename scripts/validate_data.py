#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Version-aware data contract validation for the daily pipeline.

Replaces the inline heredoc that previously lived in daily-collect.yml.
Expected artifact versions are read from contract.ARTIFACT_VERSIONS — the same
map the generators use when writing their outputs — so a version bump in a
generator can never silently break this gate again.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from contract import ARTIFACT_VERSIONS, validate  # noqa: E402


def load(name: str):
    with (ROOT / name).open(encoding="utf-8") as f:
        return json.load(f)


def check(label: str, condition, detail: str = ""):
    if not condition:
        raise AssertionError(f"{label}: {detail}")


def version_ok(name: str, data: dict) -> bool:
    return data.get("version") == ARTIFACT_VERSIONS[name]


def main() -> int:
    d = load("data.json")
    news = d.get("news", [])
    check("news", isinstance(news, list) and bool(news),
          f'count={len(news) if isinstance(news, list) else "not-list"}')
    for index, n in enumerate(news):
        check(f"news[{index}]", bool(n.get("title")) and "published_at" in n, str(n)[:240])

    i = load("intelligence.json")
    errors = validate(i)
    check("intelligence contract", not errors, "; ".join(errors[:10]))

    s = load("decision_stability.json")
    check("decision_stability", version_ok("decision_stability.json", s) and isinstance(s.get("results"), list), str(s)[:240])
    sh = load("decision_history.json")
    check("decision_history", version_ok("decision_history.json", sh) and isinstance(sh.get("snapshots"), list) and len(sh["snapshots"]) <= 90, str(sh)[:240])
    cred = load("decision_credibility.json")
    check("decision_credibility", version_ok("decision_credibility.json", cred) and cred.get("status") in {"ready", "review", "caution", "blocked"} and isinstance(cred.get("provenance"), dict) and isinstance(cred.get("reasons"), list) and len(cred.get("signal_details", [])) == 5, str(cred)[:400])
    radar = load("daily_risk_radar.json")
    check("daily_risk_radar", version_ok("daily_risk_radar.json", radar) and isinstance(radar.get("items"), list) and radar.get("status") in {"ready", "review", "caution", "blocked", "unknown"}, str(radar)[:400])
    owner = load("owner_risk_view.json")
    check("owner_risk_view", version_ok("owner_risk_view.json", owner) and isinstance(owner.get("items"), list) and owner.get("item_count", 0) >= len(owner["items"]) and isinstance(owner.get("credibility"), dict), str(owner)[:500])
    check("owner credibility", owner["credibility"].get("status") in {"ready", "review", "caution", "blocked", "unknown"} and isinstance(owner["credibility"].get("reasons"), list) and isinstance(owner["credibility"].get("provenance"), dict) and len(owner["credibility"].get("signal_details", [])) == 5, str(owner["credibility"])[:500])
    for index, item in enumerate(owner["items"]):
        check(f"owner item {index}", item.get("automation") == "advisory_only" and item.get("owners") and item.get("deadline") and item.get("next_step"), str(item)[:400])

    ta = load("trend_attribution.json")
    check("trend_attribution", version_ok("trend_attribution.json", ta) and isinstance(ta.get("modules"), dict), str(ta)[:300])
    for key, row in ta["modules"].items():
        check(f"trend module {key}", row.get("classification") in {"baseline", "single_spike", "persistent_worsening", "improving", "recovering", "recovered", "stable"}, str(row)[:300])

    q = load("review_queue.json")
    check("review_queue", version_ok("review_queue.json", q) and isinstance(q.get("items"), list), str(q)[:300])
    imp = load("change_impact.json")
    check("change_impact", version_ok("change_impact.json", imp) and isinstance(imp.get("impacted_events"), list) and isinstance(imp.get("baseline_available"), bool), str(imp)[:300])
    ledger = load("audit_ledger.json")
    check("audit_ledger", version_ok("audit_ledger.json", ledger) and ledger.get("privacy") == "hashes_and_metadata_only", str(ledger)[:300])
    for index, row in enumerate(ledger.get("stages", [])):
        check(f"audit stage {index}", len(row.get("sha256", "")) == 64 and "title" not in row and "url" not in row and "body" not in row, str(row)[:300])

    fb = load("feedback_attribution.json")
    check("feedback_attribution", version_ok("feedback_attribution.json", fb) and isinstance(fb.get("modules"), dict), str(fb)[:300])
    mh = load("module_health.json")
    check("module_health", version_ok("module_health.json", mh) and isinstance(mh.get("modules"), list), str(mh)[:300])
    mt = load("module_health_trend.json")
    check("module_health_trend", version_ok("module_health_trend.json", mt) and isinstance(mt.get("modules"), dict), str(mt)[:300])
    ob = load("optimization_backlog.json")
    check("optimization_backlog", version_ok("optimization_backlog.json", ob) and isinstance(ob.get("items"), list), str(ob)[:300])
    hist = load("optimization_backlog_history.json")
    check("optimization_backlog_history", version_ok("optimization_backlog_history.json", hist) and isinstance(hist.get("snapshots"), list) and len(hist["snapshots"]) <= 90, str(hist)[:300])
    for index, item in enumerate(ob["items"]):
        check(f"backlog item {index}", item.get("status") in {"open", "recovering", "resolved", "regressed"}, str(item)[:300])

    print(
        f"Validation passed: news={len(news)} events={len(i['events'])} "
        f"stability={len(s['results'])} credibility={cred['status']} "
        f"radar={len(radar['items'])} owner_view={len(owner['items'])} "
        f"trend_attribution={len(ta['modules'])} review={len(q['items'])} "
        f"impacts={imp['impacted_count']} backlog={len(ob['items'])} "
        f"baseline={mt['baseline_available']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())