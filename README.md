# Label Verifier

A prototype that checks an alcohol label photo against its TTB label application. It reads the label with a vision model, compares every required field with plain, tested rules, and shows the agent a checklist: **All clear**, **Needs review** or **Issues found**, with a reason for every line. It handles one label at a time or batches of hundreds.

> The original assignment brief is in [`docs/ASSIGNMENT.md`](docs/ASSIGNMENT.md).

- **Live demo:** _URL to be added after deployment_ (see [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md))
- **Try it locally without an API key:** `uv sync && LV_PROVIDER=fixture uv run uvicorn --factory app.main:create_app`, then open http://localhost:8000 and pick an example.

## What it does

| Need from the interviews | How the prototype answers it |
|---|---|
| "Half their day is just matching" (Sarah) | Brand, class/type, alcohol content, net contents, bottler, country of origin and the health warning are checked automatically. Problems are listed first, each with the reason. |
| Results in about 5 seconds, or nobody uses it | One fast model call per label (Claude Haiku 5.5, low effort), images shrunk before sending, a 3.5 s budget for the model call. |
| "Something my mother could figure out" | One page, one button, large type, plain words, works on a phone and without JavaScript, results shown by icon and word as well as colour. |
| Batches of 200–300 from importers (Janet) | Upload the photos plus one CSV. Labels are checked 8 at a time; results appear live with problems first; export to CSV. One bad row never blocks the batch. |
| "You need judgment" – STONE'S THROW vs Stone's Throw (Dave) | Case and punctuation differences count as a match with a note. Near misses go to review. In batches, agents can override any verdict with a reason; the tool's original verdict stays visible. |
| Warning must be exact, all caps, bold (Jenny) | Word-for-word comparison with the regulation text, with differences highlighted. "GOVERNMENT WARNING:" must be in capitals. Bold is checked but never auto-passed without a caveat. |
| Bad photos: angles, glare (Jenny) | The model reports image problems. Unreadable fields go to review rather than being guessed. The evaluation includes simulated phone photos. |
| Firewall blocks cloud ML endpoints; nothing sensitive stored (Marcus) | The model provider sits behind one interface (an in-tenant Microsoft Foundry option is a small addition), and a keyless demo mode exists. Nothing is written to a database; batch results are deleted after an hour. |

## How it works

```
photo ──► prepare (validate, fix rotation, strip metadata, shrink)
      ──► extract (one Claude call → fixed JSON schema; never sees the application)
      ──► rules (plain Python: normalize, compare, diff) ──► checklist + overall status
```

1. **The model only reads.** It transcribes the label exactly as printed into a strict schema, including how legible each field is. It is never shown the application values, so it can't "see" what it expects to see.
2. **Code decides.** `app/rules/` compares each field with the application:

| Field | Rule |
|---|---|
| Brand name, class/type | Exact → Match. Only case or punctuation differs → Match (noted). Very similar → Needs review. Otherwise → Mismatch. |
| Alcohol content | ABV numbers must be equal, and printed proof must be 2 × ABV. Optional for wine and beer. |
| Net contents | Compared in mL across units (750 mL = 75 cL), with 0.5% rounding tolerance between units. |
| Bottler, country of origin | Any difference → Needs review (addresses vary in format). Country of origin only for imports. |
| Health warning wording | Word for word against 27 CFR §16.21. Any word changed → Mismatch, with a word diff. Punctuation only → Needs review. |
| "GOVERNMENT WARNING:" capitals | Must be all caps. Title case → Mismatch. |
| "GOVERNMENT WARNING:" bold | "Looks bold" → Match (noted), never a plain Match. Otherwise → Needs review. |

3. **Uncertainty goes to a person.** A partly legible field, a refused or cut-off model answer, or a near miss becomes **Needs review**. A false "All clear" is the worst error this tool can make, and the evaluation counts it separately.

## Tools and why

- **Python 3.12, FastAPI, Jinja2 templates, a little vanilla JS:** server-rendered pages are the simplest thing that works for a form and a checklist, and nothing loads from external CDNs.
- **Claude Haiku 5.5 via the Anthropic SDK, structured outputs:** fast enough for the 5-second budget at about $0.0005 per label (roughly $70/year at TTB's volume). Larger models can be swapped in with `LV_MODEL` if the evaluation shows they're needed.
- **Pillow** for image preparation, **rapidfuzz** for near-miss matching.
- **pytest, ruff, mypy (strict), GitHub Actions** for tests, lint, types and the Docker build on every push.

## Assumptions

- Application values are typed in by the agent, or supplied as a CSV for batches. There is no COLA integration (per Marcus).
- The checks cover matching and the health warning, not every TTB rule. Type size, placement and misleading claims are out of scope.
- Bold type can't be measured reliably from a photo, so it's reported with a caveat rather than proven.
- The tool assists; the agent decides.

## Trade-offs and limitations

- **Accuracy is measured on synthetic labels** (rendered text plus simulated phone-photo effects). Real bottles, with curved surfaces and decorative fonts, will be harder. Real public COLA images are the next thing to add to the evaluation set.
- **Single instance.** Batch jobs live in memory: a restart loses unfinished batches, and the app can't be scaled out without a durable queue.
- **Overrides only in batches.** Single checks store nothing, so there's nowhere to record an override there.
- **CSV only for batches.** XLSX isn't parsed, though Excel saves CSV.
- **"Nothing stored" is at the application level.** The web framework writes large uploads to a temporary file that is deleted when the request ends.
- **The network question isn't solved, only prepared for.** Calling Claude needs outbound access to `api.anthropic.com`, or Microsoft Foundry inside TTB's Azure tenant via a small extra adapter.

Every decision, its reason and its cost is in [`docs/DECISIONS.md`](docs/DECISIONS.md).

## Evaluation

`evals/` holds 34 cases, built by `uv run python -m evals.build_dataset`:
- 11 labels with planted defects (wrong ABV, proof mismatch, reworded, truncated or missing warning, title-case lead-in, wrong net contents, misspelled brand, and three clean labels);
- each as a clean scan plus two simulated phone photos (angle, glare, blur, dim light, compression);
- one "not a label" control.

The headline metric is **false clears**, which must be 0. Results are in [`evals/RESULTS.md`](evals/RESULTS.md); method in [`evals/README.md`](evals/README.md).

## Setup

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env                                    # then add your key
uv run uvicorn --factory app.main:create_app --reload   # http://localhost:8000
```

Without a key, set `LV_PROVIDER=fixture` for the offline demo. It only recognizes the built-in example labels and says so on every page.

| Variable | Default | Purpose |
|---|---|---|
| `LV_ANTHROPIC_API_KEY` | (none) | Required unless `LV_PROVIDER=fixture`. |
| `LV_PROVIDER` | `anthropic` | `fixture` for the keyless demo. |
| `LV_MODEL` | `claude-haiku-5-5` | Extraction model. |
| `LV_EFFORT` | `low` | Model effort. |
| `LV_ACCESS_CODE` | (none) | If set, visitors must enter it once. Use it for a public URL. |

The `LV_` prefix keeps the app's key separate from any `ANTHROPIC_*` variables your shell sets for other tools.

**Getting an API key:**
1. At [console.anthropic.com](https://console.anthropic.com), add a small prepaid credit.
2. Set a monthly spend limit.
3. Create a key.
4. Check it with `uv run python scripts/smoke_extract.py`. This reads the five sample labels for about $0.003.

**Deploying:** see [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) (Render blueprint, Azure Container Apps, or plain Docker).

## Development

```bash
uv run pytest                              # all tests (never call the API)
uv run ruff check . && uv run ruff format --check .
uv run mypy                                # strict
uv run python -m evals.run --extractor oracle   # free harness check
uv run python -m evals.run                 # real model evaluation (~$0.02)
```

```
app/
  imaging/    image validation and preparation
  extract/    model interface, Claude extractor, keyless fixture extractor, prompt, schema
  rules/      normalization, field rules, warning rules, overall status, overrides
  services/   prepare → extract → rules for one label
  batch/      CSV in/out, in-memory batch jobs
  web/        routes, templates, CSS/JS, access and size guards
  samples/    the five example labels and their recorded readings
evals/        dataset builder, runner, scoring, results
scripts/      sample generator, real-API smoke test
docs/         assignment, PRD, technical design, decision log, deployment
```

## Documents

- [`docs/PRD.md`](docs/PRD.md): problem, users, requirements and how each interview remark maps to them.
- [`docs/TECHNICAL_DESIGN.md`](docs/TECHNICAL_DESIGN.md): architecture, latency budget, model selection, rules, testing.
- [`docs/DECISIONS.md`](docs/DECISIONS.md): decision log.
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md): hosting options and settings.
- [`evals/README.md`](evals/README.md): evaluation method.
