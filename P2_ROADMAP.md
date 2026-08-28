# P2 Intelligence Operating Loop

## Target loop

`Daily Intelligence Brief -> Personalized Watchlist -> Continuous Monitoring -> Decision Feedback Loop`

P2 turns the existing event/evidence/insight engine into a repeatable operating workflow. The core intelligence engine already follows `Article -> Event -> Evidence -> Insight -> Decision`; P2 adds the user-facing state machine around it. fileciteturn39file0L2-L3

## v1.0 implemented

### 1. Daily Intelligence Brief

`p2_intelligence.py::daily_brief()` runs the existing intelligence engine, sorts events by a daily priority score and returns the top 20 items. Priority combines the existing intelligence score, watchlist priority boost and historical feedback.

Output: `p2_daily_brief.json`.

### 2. Personalized Watchlist

Watchlists are first-class state objects:

- id / name
- enabled
- topics
- keywords
- priority_boost

Example: `p2_state.example.json`.

A watchlist hit is attached to each brief item through `watchlist_matches`.

### 3. Continuous Monitoring

Monitoring state tracks `(watchlist_id, event_id)` with:

- active
- snoozed
- resolved

This is deliberately event-centric rather than article-centric: a new article about an existing event should update the same monitored object rather than create noise.

### 4. Decision Feedback Loop

Feedback labels:

- useful
- important
- noise
- irrelevant
- incorrect
- acted_on

Current v1.0 feedback changes future daily priority by a bounded +/-15 points. This is intentionally a transparent heuristic, not opaque model retraining.

## v1.0 acceptance

- deterministic and dependency-free
- existing intelligence engine reused rather than duplicated
- watchlist personalization works without changing source truth
- monitoring is event-level
- feedback is persisted separately from evidence
- regression tests cover watchlist, monitoring and brief ordering
- CI should execute `python3 -m unittest tests.test_p2 -v`

## P2.1 next step

Replace local JSON state with a versioned persistence/API layer and add scheduled execution. The product loop should then become:

`ingest -> cluster -> score -> personalize -> monitor -> notify -> user decision -> feedback -> next brief`

## P2.2 decision learning

Do not directly fine-tune a model from clicks. First aggregate feedback into measurable signals:

- hit rate
- dismiss rate
- action rate
- repeat exposure
- false-positive rate
- time-to-decision

Only after sufficient labeled history should the priority model be learned from feedback.
