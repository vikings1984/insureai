# Replay Metrics Note

Production replay is intentionally non-blocking when `data.json` is empty. An empty dataset is a data-availability condition, not evidence of quality. When real production news exists, replay reports stability and integrity metrics for the sampled corpus.
