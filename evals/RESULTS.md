# Evaluation results

One row per `uv run python -m evals.run` against a real model (appended automatically). The dataset and the scoring are described in [`README.md`](./README.md).

- **False clear:** "All clear" on a label with a real problem. Must be 0.
- **Status exact:** overall status is exactly the expected one.
- **Acceptable:** exact, or a cautious Needs review / Can't read on a degraded photo.
- **Fields:** share of per-field verdicts that match the ground truth.
- **p50 / p95:** model-call plus image-preparation time per label, in seconds.

| Date | Model | Prompt | Cases | False clear | Status exact | Acceptable | Fields | p50 s | p95 s | $/label |
|---|---|---|---|---|---|---|---|---|---|---|
| 20261008 | claude-haiku-5-5 effort=low | 2026-10-08.1 | 68 | 0 | 88% | 91% | 97% | 2.2 | 3.66 | 0.00058 |
| 20261008 | claude-haiku-5-5 effort=low | 2026-10-08.2 | 68 | 0 | 98% | 100% | 100% | 1.82 | 2.95 | 0.00059 |
| 20261008 | claude-sonnet-5-5 effort=low | 2026-10-08.2 | 34 | 0 | 100% | 100% | 100% | 2.97 | 3.29 | 0.01127 |

## Notes

- **Prompt 2026-10-08.1 → .2:** the first real run showed the model sometimes reporting the "GOVERNMENT WARNING:" lead-in only in its own field and leaving it out of the full statement. The rules then saw the statement as missing two words (6 wrong "Issues found", never a false pass). The rules now put a separately reported lead-in back before comparing, and the schema says the statement must include it. A label with no lead-in at all is still caught.
- **Model choice:** Haiku 5.5 stays the default. It matches Sonnet 5.5 on the safety metrics (0 false clears, 100% acceptable) and is 1.1 s faster at the median and 19× cheaper. Its only miss was one cautious "Needs review" on a degraded photo. See DECISIONS.md D19.
- **Caveat:** these are synthetic labels. Real bottle photos (curved surfaces, decorative fonts) will be harder; the next step is adding public COLA images.
