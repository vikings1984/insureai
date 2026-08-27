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
- `affected_functions` — facets at or above the 28 presence threshold (same threshold as `signal.py`), each as `{function, label, impact}`; weak-signal events fall back to the single highest facet instead of inventing functions.
- `potential_opportunity` / `potential_risk` — templates keyed by `event_type`, with evidence qualifiers (single source, conflict, low trust) appended to the risk list.
- `what_to_monitor` — inherited verbatim from `insight.what_to_watch`.
- `recommended_next_step` — urgency prefix + the role action, plus a human-review qualifier when `human_review_required` is true.

`intelligence.json.decisions` stays the executive-lens flat list for downstream consumers; `intelligence.json.decisions_by_role` groups the top 12 cards per role. `decision_stats.decision_context_coverage` reports the six-element completeness rate across all role cards and the production quality gate requires it ≥ 0.9.

## Lineage

`data_contract.components` contains short SHA-256 fingerprints for the major sections of the generated intelligence document. These are integrity fingerprints, not source authenticity proofs.

## Compatibility policy

The GitHub Actions pipeline must run `contract.py` before publishing generated data. A contract validation failure blocks publication. This keeps feature work additive and prevents a new intelligence module from silently breaking older UI consumers.
