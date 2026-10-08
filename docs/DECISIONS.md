# Decision Log

Short records of the decisions that shape this prototype, newest last. Each entry gives the decision, the reason, and what it costs. Requirement IDs refer to [`PRD.md`](./PRD.md); section numbers (§) refer to [`TECHNICAL_DESIGN.md`](./TECHNICAL_DESIGN.md).

---

### D1. The model reads; code decides
**Decision:** The vision model only transcribes the label into a fixed schema. Plain Python rules (`app/rules/`) compare that transcription with the application and issue every verdict.
**Why:** Verdicts must be explainable, testable and consistent. An LLM judging "match or not" is non-deterministic and can't be unit-tested.
**Cost:** Matching nuance (e.g. "STONE'S THROW" vs "Stone's Throw") has to be written as explicit rules.

### D2. The model never sees the application values
**Decision:** The extraction prompt contains the image and the beverage type only. A test enforces this.
**Why:** A model shown "expect 45%" tends to read 45%. Blind transcription is the main defence against false matches.
**Cost:** None of consequence. The model can't use the application as a hint for hard-to-read text, which is exactly the behaviour we want.

### D3. A false "Match" is the worst error
**Decision:** Anything uncertain becomes **Needs Review**: partly legible fields, punctuation-only warning differences, refusals, truncated model output, and near-miss brand names.
**Why:** A missed violation costs far more than a few seconds of human checking (PRD §8).
**Cost:** Some labels that are actually fine will be sent for review.

### D4. Bold can be a noted match, never a plain match
**Decision:** If the model says the "GOVERNMENT WARNING:" prefix looks bold, the bold check is **Match (noted)** with a caveat. "Not bold" or "unsure" is Needs Review.
**Why:** The first design always returned Needs Review, which meant **no label could ever be All Clear** and would have trained agents to ignore the tool.
**Cost:** A photo can't actually prove font weight. The caveat is shown on screen.

### D5. Claude Haiku 5.5 at low effort, one structured-output call
**Decision:** Default model is `claude-haiku-5-5` with `effort: low`. One `messages.parse` call returns the Pydantic schema; every field is required.
**Why:** The 5-second limit (N-1) is the adoption gate; the last vendor tool failed at 30–40 s. Cost is negligible at TTB volume (~$70/year). Required fields stop the model from silently skipping one.
**Cost:** The smallest model may misread more than larger ones. The evaluation harness decides whether to step up to Sonnet 5.5 (§5.4).

### D6. Swappable provider; keyless demo mode
**Decision:** Extraction sits behind a `LabelExtractor` interface. `LV_PROVIDER=fixture` replays recorded readings of the five sample labels; `anthropic` calls Claude.
**Why:** It addresses Marcus's firewall concern (an in-tenant provider such as Microsoft Foundry can be added behind the same interface), and the app can be built, tested and demoed without a key or any spend.
**Cost:** Demo mode only works for the sample labels, so the app shows a banner whenever it runs on recorded readings.

### D7. `LV_`-prefixed settings and an explicit API base URL
**Decision:** The app reads `LV_ANTHROPIC_API_KEY` etc. and always passes `https://api.anthropic.com` explicitly.
**Why:** Development shells (including this cloud environment) often set `ANTHROPIC_*` variables for other tools. Reusing them could send the app's traffic to the wrong place or bill the wrong account.
**Cost:** Slightly non-standard variable names, documented in the README.

### D8. Nothing is stored
**Decision:** Uploads are processed in memory and metadata is stripped. The result page embeds the checked photo as a data URI instead of saving it.
**Why:** Marcus flagged PII and records-retention rules (N-4). The simplest compliant prototype keeps nothing.
**Cost:** Results can't be revisited after the page is closed. Batch results live in memory for a limited time only.

### D9. Server-rendered pages, no front-end framework
**Decision:** Jinja2 templates with plain form posts and one small script for enhancements. HTMX was planned but dropped.
**Why:** It's the simplest UI to build and maintain, works without JavaScript, and loads nothing from external CDNs (blocked networks).
**Cost:** Less interactive than a single-page app. That's acceptable for a form-and-checklist workflow.

### D10. No pixel-based blur detection
**Decision:** Image quality problems (blur, glare, angle) are reported by the model's `quality_issues`, not by image statistics.
**Why:** A measured edge-variance check couldn't tell sharp from blurred labels; the printed borders dominated the score.
**Cost:** Quality judgement depends on the model; the evaluation set includes degraded photos to measure it.

### D11. Synthetic sample labels with known ground truth
**Decision:** `scripts/make_samples.py` draws five labels, each with one planted issue (or none), and records exactly what is printed on them.
**Why:** It provides demo content, end-to-end test fixtures and evaluation ground truth from one source, without depending on copyrighted real labels.
**Cost:** Clean digital labels are easier to read than real bottle photos. The evaluation adds degraded variants to compensate.

### D12. Batch: one bad row never blocks the batch
**Decision:** There's no blocking pre-flight step. Rows with problems (missing fields, no matching photo) and photos without a row appear in the results as **Not checked**, with the reason. Everything else is checked straight away.
**Why:** For a 300-label importer drop, holding up 299 good labels for one typo would be worse than listing the typo with the results. It also removes a step for the user.
**Cost:** Problems are reported after the upload rather than before it. They are sorted to the top of the results, so they're the first thing seen.

### D13. Batch: CSV only, in-memory jobs, bounded concurrency
**Decision:**
- The spreadsheet must be CSV (Excel saves it). XLSX isn't parsed.
- Jobs live in process memory: 8 labels are checked at once, with at most 300 files or 300 MB per batch.
- Results are deleted 1 hour after the batch finishes.
- Uploads that hit a temporary model failure are kept so "Retry failed labels" can re-run just those.
- The results table refreshes every 1.5 s, or by page reload when JavaScript is off.

**Why:** It meets the 300-labels-in-minutes target (N-2) with no queue, database or extra service to run.
**Cost:**
- The app must run as a single instance, and a restart loses unfinished batches. The production path is a durable queue (§7).
- The web framework (Starlette) writes uploads larger than 1 MB to a temporary file, which is deleted when the request ends. So "nothing stored" (D8) holds only at the application level. This is acceptable for the prototype and worth noting for a security review.

### D14. Spreadsheet export is protected against formula injection
**Decision:** Any exported cell starting with `=`, `+`, `-`, `@`, a tab or a carriage return is prefixed with `'`.
**Why:** Label text comes from applicants. A brand name such as `=HYPERLINK(...)` would otherwise run as a formula when an agent opens the export in Excel.
**Cost:** Values that genuinely start with those characters show a leading apostrophe in the CSV.

### D15. Agent overrides are recorded on batch results only
**Decision:** On a batch item's detail page, an agent can mark any field "It matches" or "It doesn't match", with a required reason, and can undo it. The override changes the label's status, the results table and the CSV export, which records what the tool said, what the agent said and why. The tool's original verdict stays visible.
**Why:** Dave's point that "you need judgment" (PRD F-13). Keeping the tool's verdict next to the agent's makes disagreements reviewable, and they could later feed back into the evaluation set.
**Cost:** Single-label checks store nothing (D8), so there is nowhere to record an override there; the agent's own judgement is the record. An override can't turn an unreadable image into a pass.
