# Concepts

Shared domain vocabulary for this project — entities, named processes, and status concepts with project-specific meaning. Seeded with core domain vocabulary, then accretes as ce-compound and ce-compound-refresh process learnings; direct edits are fine. Glossary only, not a spec or catch-all.

## Content Classification

### Category Dedication
A classification pattern where a category is reserved exclusively for content of a specific *origin* (e.g., manually curated reports), not merely a specific *topic*. Daily news matching the category's keywords is routed to a general-purpose sibling category so that the dedicated category's contents are homogeneous in structure, lifecycle, and presentation requirements. In this project, the `research` category is dedicated to curated authoritative reports.

### Research Report Registry
A curated JSON registry (`data/research_reports.json`) of 19 authoritative insurance industry research reports from international and domestic institutions. Loaded into `data.json` on each collection cycle and injected as `category="research"` items with `is_research_report=True` and a fixed `ai_score=95`. Distinct from daily news in origin (manual curation vs algorithmic aggregation), lifecycle (evergreen vs ephemeral), and rendering (card grid vs timeline).

### Three-Layer Coverage
The structural organization of the Research Report Registry into three tiers: international reinsurance institutions (Swiss Re, Munich Re, Lloyd's — macro market data), global consulting firms (McKinsey, BCG, Deloitte, etc. — strategic trends), and domestic research institutions (NFRA, 清华五道口, 头豹, etc. — local market perspective). Each layer is labeled in the `source_type` field and color-coded in the frontend card grid.

### Daily News vs Research Reports
The fundamental content dichotomy in this platform. Daily news is algorithmically collected, recency-weighted, and rendered in a timeline. Research reports are manually curated, fixed-scored, and rendered in a card grid. The two populations never mix within a single category or rendering path.
