# Label Verifier

An AI-assisted tool that checks alcohol label images against the values in a TTB label application. The model reads the label, and a deterministic rule engine decides **Match / Needs Review / Mismatch** for each field, with a reason for every verdict.

> Prototype for a take-home assignment. The original brief is in [`docs/ASSIGNMENT.md`](docs/ASSIGNMENT.md).

## Status

| Milestone | State |
|---|---|
| Project scaffold, CI, Docker | ✅ |
| Rule engine (all field and warning rules) with tests | ✅ |
| Image preparation and model extraction | ⏳ next |
| Single-label UI | ⏳ |
| Batch upload | ⏳ |
| Evaluation harness and model selection | ⏳ |

## Documentation

- [`docs/PRD.md`](docs/PRD.md): problem, users, requirements, success metrics, and how each stakeholder remark maps to a requirement.
- [`docs/TECHNICAL_DESIGN.md`](docs/TECHNICAL_DESIGN.md): architecture, latency budget, model selection, rule definitions, testing and trade-offs.

## Setup

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                                   # install dependencies
uv run uvicorn app.main:app --reload      # http://localhost:8000/healthz
```

Or with Docker:

```bash
docker build -t label-verifier .
docker run -p 8000:8000 label-verifier
```

## Development

```bash
uv run pytest          # tests
uv run ruff check .    # lint
uv run ruff format .   # format
uv run mypy            # type check (strict)
```

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
