# InsureAI Canonical Intelligence Model

InsureAI now treats the following objects as the core semantic contract:

```text
Article → Claim → Evidence → Event → Trend → Insight → Decision
```

- **Article**: an externally published source item.
- **Claim**: a factual statement extracted from one or more articles.
- **Evidence**: a traceable source supporting a claim or event.
- **Event**: a real-world change assembled from related source items.
- **Trend**: a time-based pattern across events.
- **Insight**: an interpretation of an event with explicit evidence and uncertainty.
- **Decision**: bounded, advisory-only guidance derived from evidence-backed intelligence.

The schemas deliberately allow additional properties during the transition period. Production generators should add fields only when they preserve the semantic distinction above.

## Non-negotiable rules

1. Similar articles are not automatically the same event.
2. A missing artifact is not evidence of failure.
3. A single source must not be represented as cross-checked evidence.
4. Regulatory, claims, rating, and low-coverage intelligence should surface a human-review boundary.
5. Decision support never executes underwriting, investment, compliance, or operational actions.
