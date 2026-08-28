# InsureAI Intelligence Data Contract

`intelligence.json` is the canonical product data contract between the ingestion pipeline and every UI/intelligence module.

## Contract hierarchy

```text
news → events → intelligence → trust → claims → temporal → decisions
                       ↘ radar
```

## Versioning rules

- `intelligence.json.version` is the generated-data version. A breaking field change requires a version bump.
- `data_contract.schema_version` is the contract format version. Additive fields are backward-compatible; changing meaning or removing required fields requires a schema version bump.
- Every event must keep a stable unique `event_id` for the lifetime of the event record.
- Scores are numeric and use a 0–100 scale.
- Trust levels are exactly `high`, `medium`, or `low`.
- Decision urgency is exactly `now`, `soon`, or `watch`.
- Decision roles are exactly the 8 keys of `decision.ROLE_ACTIONS` (`executive`, `product`, `underwriting`, `actuarial`, `investment`, `technology`, `claims`, `distribution`).
- `claims`, `temporal`, `decisions`, and `radar` are module outputs, but the contract validates their minimum structure before publishing.

## Decision cards (v8)

Since version 8 every decision card carries a `context` object whose six elements are mappings of existing event signals — the pipeline never fabricates facts inside a decision card:

- `business_impact` — facet strengths 0–100 for `strategic` / `product` / `underwriting` / `investment` / `compliance`. A facet whose `event_type` directly hits the function equals the intelligence score; a facet activated only by signal scores is scaled at 45% and capped below primary facets.
- `affected_functions` — facets at or above the 28 presence threshold (same threshold as `intelligence_signal.py`), each as `{function, label, impact}`; weak-signal events fall back to the single highest facet instead of inventing functions.
- `potential_opportunity` / `potential_risk` — templates keyed by `event_type`, with evidence qualifiers (single source, conflict, low trust) appended to the risk list.
- `what_to_monitor` — inherited verbatim from `insight.what_to_watch`.
- `recommended_next_step` — urgency prefix + the role action, plus a human-review qualifier when `human_review_required` is true.

`intelligence.json.decisions` stays the executive-lens flat list for downstream consumers; `intelligence.json.decisions_by_role` groups the top 12 cards per role. `decision_stats.decision_context_coverage` reports the six-element completeness rate across all role cards and the production quality gate requires it ≥ 0.9.

## Knowledge graph (v3)

`knowledge_graph.json` is a derived, provenance-first artifact built from `intelligence.json` + `claims.json`:

- Since version 3 every `Event` node carries `published_at`, and `stats` carries `node_types` (per-type counts) and `latest_event_at` (max event timestamp).
- The query layer (`kg_query.py`) is read-only: `entity_recent` anchors its 90-day window on the graph's own `latest_event_at` so answers are reproducible regardless of query time; claims without timestamps inherit the time of the event they `INVOLVES`.
- `module_health.json` carries a `knowledge_graph` module row sourced from the graph stats; an empty graph (node or edge count 0) is `critical` with priority 100, and the daily workflow asserts `node_count > 0` before release (kg_nonempty_gate).

## Lineage

`data_contract.components` contains short SHA-256 fingerprints for the major sections of the generated intelligence document. These are integrity fingerprints, not source authenticity proofs.

## Compatibility policy

The GitHub Actions pipeline must run `contract.py` before publishing generated data. A contract validation failure blocks publication. This keeps feature work additive and prevents a new intelligence module from silently breaking older UI consumers.
