# Label Verifier

An AI-assisted tool that checks alcohol label images against the values in a TTB label application. The model reads the label, and a deterministic rule engine decides **Match / Needs Review / Mismatch** for each field, with a reason for every verdict.

> Prototype for a take-home assignment. The original brief is in [`docs/ASSIGNMENT.md`](docs/ASSIGNMENT.md).

## Status

| Milestone | State |
|---|---|
| Project scaffold, CI, Docker | ✅ |
| Rule engine (all field and warning rules) with tests | ✅ |
| Image preparation and Claude extraction, offline demo mode | ✅ |
| Single-label web page | ✅ |
| Batch upload with live results and CSV export | ✅ |
| Evaluation harness and model selection | ⏳ |

## Documentation

- [`docs/PRD.md`](docs/PRD.md): problem, users, requirements, success metrics, and how each stakeholder remark maps to a requirement.
- [`docs/TECHNICAL_DESIGN.md`](docs/TECHNICAL_DESIGN.md): architecture, latency budget, model selection, rule definitions, testing and trade-offs.
- [`docs/DECISIONS.md`](docs/DECISIONS.md): log of the key design decisions, each with its reason and cost.

## Setup

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                                   # install dependencies
LV_PROVIDER=fixture uv run uvicorn --factory app.main:create_app --reload   # offline demo at http://localhost:8000
```

Or with Docker:

```bash
docker build -t label-verifier .
docker run -p 8000:8000 -e LV_ANTHROPIC_API_KEY label-verifier
```

## Configuration

Settings come from `LV_`-prefixed environment variables or a `.env` file (see [`.env.example`](.env.example)).

| Variable | Default | Purpose |
|---|---|---|
| `LV_PROVIDER` | `anthropic` | `anthropic` calls Claude. `fixture` is a keyless offline demo that only recognizes the sample labels in `app/samples/`. |
| `LV_ANTHROPIC_API_KEY` | (none) | Required when `LV_PROVIDER=anthropic`. |
| `LV_MODEL` | `claude-haiku-5-5` | Extraction model. |
| `LV_EFFORT` | `low` | Model effort; low keeps latency inside the 5-second budget. |

The `LV_` prefix keeps the app's key separate from any `ANTHROPIC_*` variables your shell already sets for other tools.

### Getting an API key

1. Sign in at [console.anthropic.com](https://console.anthropic.com) and add a small prepaid credit under **Billing**.
2. Under **Limits**, set a monthly spend limit (for example $10), so a public demo can never cost more than that.
3. Under **API keys**, create a key and set it as `LV_ANTHROPIC_API_KEY`.
4. Check it with `uv run python scripts/smoke_extract.py`, which reads the five sample labels and compares the results with what is actually printed on them (about $0.003 in total).

Without a key, run the offline demo with `LV_PROVIDER=fixture`.

## Development

```bash
uv run pytest          # tests
uv run ruff check .    # lint
uv run ruff format .   # format
uv run mypy            # type check (strict)
uv run python scripts/make_samples.py   # regenerate the synthetic sample labels
```

Tests never call the API: the Claude extractor is tested against a fake client, and everything else uses recorded readings of the sample labels.

## How verification works

1. **Extract.** A vision model transcribes the label verbatim into a fixed schema. It is never shown the application values, so it can't be biased toward "seeing" them.
2. **Compare.** `app/rules/` compares each field with the application in plain, unit-tested Python:

| Field | Rule |
|---|---|
| Brand name, class/type | Exact → Match. Differs only in case or punctuation (`STONE'S THROW` vs `Stone's Throw`) → Match (noted). Very similar → Needs Review. Otherwise Mismatch. |
| Alcohol content | ABV numbers must be equal. Printed proof must be 2 × ABV. Optional for wine and beer. |
| Net contents | Compared in mL across units (`750 mL` = `75 cL`), with 0.5% rounding tolerance between units. |
| Bottler, country of origin | Any difference → Needs Review (addresses vary in format). Country only for imports. |
| Health warning wording | Word-for-word against 27 CFR §16.21. Any wording change → Mismatch, with a word diff. Punctuation-only differences → Needs Review. |
| `GOVERNMENT WARNING:` capitals | Must be all caps. Title case → Mismatch. |
| `GOVERNMENT WARNING:` bold | "Looks bold" → Match (noted), never a plain Match. Otherwise Needs Review. |

Any field the model could only partly read becomes **Needs Review**. A false "Match" is the worst error this tool can make.
