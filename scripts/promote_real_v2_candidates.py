#!/usr/bin/env python3
"""P1-4.1 real-data expansion — human-review-aid for promoting proposed candidates.

Flow (respects the hard constraint: production data is NEVER auto-labeled):

  1. prepare   candidates.json -> review_bundle.json
               For every proposed candidate we (a) map its embedded article
               metadata into the engine's input schema, (b) run the engine to
               see whether it AGREES with the proposed relation (same/different
               event), and (c) emit a suggested gold delta with decision=pending.
               Nothing is validated; the human decides per entry.

  2. apply     review_bundle.json -> gold_real.json + articles_real.json
               Only entries with decision=="approve" are promoted. Entries that
               are still "pending" block a real apply (refuses to auto-validate).
               After writing, the runner is executed on the real set and the
               macro_quality / safety rates are reported (NOT gated — real-data
               quality is measured, not forced to 1.0).

  3. apply --dry-run   print the projected promotion + engine-agreement impact
                       without writing anything.

The curated synthetic v2 (gold.json, macro=1.0) is NEVER touched; the real set
lives in its own gold_real.json / articles_real.json so the curated regression
test stays green.
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT))

import intelligence  # noqa: E402
from real_data_benchmark import _rows, run_benchmark  # noqa: E402

REAL_V2 = PROJECT_ROOT / "benchmarks" / "real_v2"
CAND = REAL_V2 / "candidates.json"
GOLD_REAL = REAL_V2 / "gold_real.json"
ART_REAL = REAL_V2 / "articles_real.json"
BUNDLE = REAL_V2 / "review_bundle.json"
RESULT_REAL = ROOT / "real_benchmark_v2_real_results.json"

DIMENSIONS = ["rumor_to_confirmed", "same_company_diff_event", "multi_source_3_5", "contradiction"]


def _map_article(a: dict) -> dict:
    """Map a candidate-embedded article into the engine's minimal input schema."""
    return {
        "id": a["id"],
        "title": a.get("title"),
        "url": a.get("source_url"),
        "published_at": a.get("published_at"),
        "source_name": a.get("source_name"),
        "research_topic": a.get("research_topic"),
        "tags": a.get("tags", ""),
    }


def _engine_ev_of(articles: list[dict]) -> dict:
    """Map each article id -> engine event id (empty if engine errors)."""
    try:
        res = intelligence.build({"news": _rows(articles)})
    except Exception:  # engine may choke on sparse metadata; treat as unknown
        return {}
    ev_of: dict = {}
    for ev in res.get("events", []):
        for aid in ev.get("article_ids", []):
            ev_of[aid] = ev["event_id"]
    return ev_of


def _engine_agrees(articles: list[dict], proposed_relation: str) -> bool:
    """Does the engine's actual clustering match the proposed relation?"""
    if len(articles) < 2:
        return False
    ev_of = _engine_ev_of(articles)
    present = {a["id"] for a in articles} & set(ev_of)
    if not present:
        return False
    distinct = {ev_of[a["id"]] for a in articles if a["id"] in ev_of}
    if proposed_relation == "same_event":
        return len(distinct) == 1  # all articles collapsed into one engine event
    return len(distinct) >= 2  # articles spread across >=2 engine events


def prepare() -> dict:
    cand = json.loads(CAND.read_text(encoding="utf-8"))
    bundle = {
        "version": "real-v2.0-review-bundle",
        "generated_from": "candidates.json",
        "review_status": "pending_human",
        "note": "decision must be set to 'approve' or 'reject' per entry before apply. Never auto-validated.",
        "entries": [],
    }
    for c in cand["candidates"]:
        mapped = [_map_article(a) for a in c["articles"]]
        ids = [a["id"] for a in mapped]
        rel = c["proposed_relation"]
        agrees = _engine_agrees(mapped, rel)
        str_ids = [str(i) for i in ids]
        if len(ids) >= 2:
            pairs = [list(p) for p in itertools.combinations(str_ids, 2)]
        else:
            pairs = []
        if rel == "same_event":
            same_pairs, diff_pairs = pairs, []
        else:
            same_pairs, diff_pairs = [], pairs
        entry = {
            "candidate_id": c["id"],
            "dimension": c["dimension"],
            "proposed_relation": rel,
            "primary_entity": c.get("primary_entity"),
            "rationale": c.get("rationale"),
            "article_ids": ids,
            "engine_agrees_with_proposal": agrees,
            "decision": "pending",
            "suggested_same_event_pairs": same_pairs,
            "suggested_different_event_pairs": diff_pairs,
            "suggested_claim_cases": [],
            "suggested_decision_safety_cases": [],
            "notes": "claim/decision cases require human truth labeling; add before apply if relevant.",
        }
        bundle["entries"].append(entry)
    BUNDLE.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    total = len(bundle["entries"])
    agree = sum(1 for e in bundle["entries"] if e["engine_agrees_with_proposal"])
    promotable = sum(1 for e in bundle["entries"] if e["engine_agrees_with_proposal"] and e["article_ids"])
    print(f"[prepare] entries={total} engine_agrees={agree} (of which >=2 articles={promotable})")
    print(f"[prepare] review bundle -> {BUNDLE}")
    return bundle


def _approve_summary(entries: list[dict]) -> dict:
    same = sum(len(e["suggested_same_event_pairs"]) for e in entries)
    diff = sum(len(e["suggested_different_event_pairs"]) for e in entries)
    arts = {aid for e in entries for aid in e["article_ids"]}
    by_dim: dict = {}
    for e in entries:
        by_dim[e["dimension"]] = by_dim.get(e["dimension"], 0) + 1
    return {
        "approved_entries": len(entries),
        "distinct_articles": len(arts),
        "same_event_pairs": same,
        "different_event_pairs": diff,
        "by_dimension": by_dim,
    }


def apply(dry_run: bool = False) -> None:
    if not BUNDLE.exists():
        raise SystemExit("ERROR: review_bundle.json not found. Run `prepare` first.")
    bundle = json.loads(BUNDLE.read_text(encoding="utf-8"))
    entries = bundle["entries"]
    approved = [e for e in entries if e["decision"] == "approve"]
    pending = [e for e in entries if e["decision"] == "pending"]
    rejected = [e for e in entries if e["decision"] == "reject"]

    summary = _approve_summary(approved)
    print(f"[apply] approved={len(approved)} rejected={len(rejected)} pending={len(pending)}")
    print(f"[apply] projected: {json.dumps(summary, ensure_ascii=False)}")

    if not dry_run and pending:
        raise SystemExit(
            f"ERROR: {len(pending)} entries still 'pending'. Human review required before promotion; "
            "refusing to auto-validate. Set decision='approve' or 'reject' for every entry."
        )

    if dry_run:
        print("[apply] --dry-run: no files written.")
        return

    # Build the real-data corpus + gold from approved entries only.
    corpus_map: dict = {}
    same_pairs: list = []
    diff_pairs: list = []
    claim_cases: list = []
    decision_cases: list = []
    for e in approved:
        cand = json.loads(CAND.read_text(encoding="utf-8"))
        src = next((c for c in cand["candidates"] if c["id"] == e["candidate_id"]), None)
        if src is None:
            continue
        for a in src["articles"]:
            if a["id"] not in corpus_map:
                corpus_map[a["id"]] = _map_article(a)
        same_pairs += e["suggested_same_event_pairs"]
        diff_pairs += e["suggested_different_event_pairs"]
        claim_cases += e.get("suggested_claim_cases", [])
        decision_cases += e.get("suggested_decision_safety_cases", [])

    articles_real = list(corpus_map.values())
    gold_real = {
        "version": "real-v2.0-real",
        "review_status": "validated",
        "annotation_policy": {
            "unit": "article pair / event cluster / proposition",
            "source": "promoted from candidates.json after human review",
            "production_data_never_auto_labeled": True,
        },
        "same_event_pairs": same_pairs,
        "different_event_pairs": diff_pairs,
        "singletons": [],
        "claim_cases": claim_cases,
        "decision_safety_cases": decision_cases,
        "dimension_coverage": sorted({e["dimension"] for e in approved}),
    }
    ART_REAL.write_text(json.dumps(articles_real, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    GOLD_REAL.write_text(json.dumps(gold_real, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[apply] wrote {ART_REAL} ({len(articles_real)} articles) + {GOLD_REAL}")

    # Run the runner on the real set; report (do not gate) quality.
    result = run_benchmark(ART_REAL, GOLD_REAL, RESULT_REAL)
    print(f"[apply] real macro_quality={result['macro_quality']}")
    print(f"[apply] real false_merge={result['event']['false_merge_rate']} "
          f"false_split={result['event']['false_split_rate']} "
          f"single_source_false_cross={result['claim_evidence']['single_source_false_cross_check_rate']}")
    print(f"[apply] real results -> {RESULT_REAL}")


def main() -> None:
    parser = argparse.ArgumentParser(description="P1-4.1 real-data candidate promotion (human-in-loop)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prepare", help="candidates.json -> review_bundle.json (decision=pending)")
    ap = sub.add_parser("apply", help="promote approved entries -> gold_real.json + articles_real.json")
    ap.add_argument("--dry-run", action="store_true", help="report projected promotion without writing")
    args = parser.parse_args()
    if args.cmd == "prepare":
        prepare()
    elif args.cmd == "apply":
        apply(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
