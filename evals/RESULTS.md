# Evaluation results

One row per `uv run python -m evals.run` against a real model (appended automatically). The dataset and the scoring are described in [`README.md`](./README.md).

- **False clear:** "All clear" on a label with a real problem. Must be 0.
- **Status exact:** overall status is exactly the expected one.
- **Acceptable:** exact, or a cautious Needs review / Can't read on a degraded photo.
- **Fields:** share of per-field verdicts that match the ground truth.
- **p50 / p95:** model-call plus image-preparation time per label, in seconds.

| Date | Model | Prompt | Cases | False clear | Status exact | Acceptable | Fields | p50 s | p95 s | $/label |
|---|---|---|---|---|---|---|---|---|---|---|
