# Evaluation

Measures how well the whole pipeline (image preparation → model extraction → rules) does on labels whose correct answer is known. This is how the model and prompt are chosen (TECHNICAL_DESIGN.md §5.4 and §9.2).

## Dataset

`evals/dataset/`: 34 cases built by `uv run python -m evals.build_dataset`.

| Label | Planted problem | Expected |
|---|---|---|
| old_tom_bourbon | none | All clear |
| stones_throw_gin | brand in capitals, ABV worded differently | All clear |
| hop_harbor_ipa_no_abv | beer with no ABV (allowed) | All clear |
| harbor_light_rum_title_case | "Government Warning:" in title case, not bold | Issues found |
| copper_ridge_vodka_wrong_abv | 40% on label, 45% in application | Issues found |
| domaine_viale_wine_reworded | warning reworded ("should avoid drinking") | Issues found |
| granite_peak_proof_mismatch | 45% ABV printed as 95 proof | Issues found |
| blue_heron_truncated_warning | warning's second clause missing | Issues found |
| night_owl_missing_warning | no warning at all | Issues found |
| silver_creek_net_contents | 700 mL on label, 750 mL in application | Issues found |
| maple_hollow_brand_typo | "MAPLE HOLOW" vs "MAPLE HOLLOW" | Needs review |
| grocery_list | not a label | Can't read |

Every label except the grocery list appears three times: a clean scan, and two simulated phone photos that each apply one effect: angled, glare, blur, dim lighting, or heavy compression. Ground truth is the exact text drawn on each label.

## Scoring

- **False clear:** "All clear" on a label that has a real problem. This is the error that matters most (PRD §8). Target: **0**.
- **Status exact:** overall status equals the expected one.
- **Acceptable:** exact, *or* a cautious "Needs review" / "Can't read" on a degraded photo. Asking a person to look at a bad photo is fine; passing it is not.
- **Field verdicts:** per-field verdicts that match what the ground truth produces.
- **Text exact:** extracted text identical to what is printed (a stricter, diagnostic measure).
- **Latency:** image preparation plus model call per label (p50, p95). Target: p95 ≤ 3.5 s, leaving headroom under the 5 s budget.

## Running

```bash
uv run python -m evals.run --extractor oracle      # free: checks the harness with the ground truth
uv run python -m evals.run                         # Claude, using LV_MODEL / LV_EFFORT (~$0.02 on Haiku 5.5)
uv run python -m evals.run --model claude-sonnet-5-5 --runs 2
```

Each real run appends one row to [`RESULTS.md`](./RESULTS.md). Full per-case details go to `evals/results/` (git-ignored). The oracle run is part of the test suite.
