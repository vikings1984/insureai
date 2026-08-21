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
- `claims`, `temporal`, `decisions`, and `radar` are module outputs, but the contract validates their minimum structure before publishing.

## Lineage

`data_contract.components` contains short SHA-256 fingerprints for the major sections of the generated intelligence document. These are integrity fingerprints, not source authenticity proofs.

## Compatibility policy

The GitHub Actions pipeline must run `contract.py` before publishing generated data. A contract validation failure blocks publication. This keeps feature work additive and prevents a new intelligence module from silently breaking older UI consumers.
