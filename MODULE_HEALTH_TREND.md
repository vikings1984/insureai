# Module Health Trend

Module health is a quality-observation layer, not a production decision signal.

The trend model compares the current `module_health.json` snapshot with the most recent historical snapshot and labels each module:

- `baseline`: no prior observation exists
- `stable`: change is below the materiality threshold
- `improving`: error rate decreased by at least 0.05
- `worsening`: error rate increased by at least 0.05

History is capped at 90 snapshots. The trend layer must not alter intelligence scores, trust, urgency, or action triggers.
