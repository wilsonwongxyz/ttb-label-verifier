# PRD: AI-Assisted Alcohol Label Verification (Prototype)

| | |
|---|---|
| **Status** | Draft v0.1 |
| **Owner** | Wilson Wong |
| **Source** | `README.md` (discovery interviews + technical brief) |
| **Type** | Standalone proof-of-concept that may inform a future procurement decision. Not a production system. |

---

## 1. Summary

TTB compliance agents spend about half their day checking by eye that the values on a label image match the values in the label application: brand name, ABV, net contents, government warning, and so on. This prototype automates that check. An agent uploads a label image (or a batch of them) with the expected application values. Within about 5 seconds they get a field-by-field verdict (**Match / Needs Review / Mismatch**) with the evidence for each verdict.

The tool **assists** the agent and does not make the decision. It handles the routine matching so agents can spend their time on cases that need judgment.

## 2. Problem

- **Volume vs. capacity.** About 150,000 applications a year are handled by 47 agents, roughly 3,200 per agent per year. A simple review takes 5–10 minutes.
- **Most of the work is routine matching.** Sarah: *"a lot of what we do is just... matching… My agents spend half their day doing what's essentially data entry verification."*
- **The last automation attempt failed because it was slow.** At 30–40 s per label, agents went back to doing it by hand. Speed decides whether people use the tool at all.
- **Peak-season bulk submissions.** Importers submit 200–300 applications at once, and these are currently processed one at a time.

## 3. Goals and non-goals

### Goals
1. **G1, Accurate field verification.** Extract the key label fields from an image and compare them to the application values, with judgment-aware matching.
2. **G2, Strict government warning check.** Verify the health warning word for word, including the all-caps "GOVERNMENT WARNING:" prefix.
3. **G3, Speed.** ≤ 5 s from upload to result for a single label (p95 target).
4. **G4, Extremely simple UX.** Usable without training by a low-tech user ("my mother could figure out… she's 73").
5. **G5, Batch processing.** Verify hundreds of labels in one submission, with results streamed back as each label finishes.

### Non-goals (this prototype)
- Integration with COLA or its authorization model (Marcus: "a whole different beast").
- Final approve/reject decisions. The agent always decides.
- Persisting labels, applications, or results. Nothing sensitive is stored.
- Production-grade FedRAMP / PII / records-retention compliance (documented as future work in §11).
- Full regulatory coverage of every TTB rule for every beverage type (e.g., type-size minimums, placement rules).

## 4. Users and personas

| Persona | From | Needs | Design implication |
|---|---|---|---|
| **Low-tech senior agent** ("Dave", 28 yrs) | Dave, Sarah | Not slower than doing it by eye; clear results; nothing to "fight with." Skeptical after past failed tools. | One obvious primary action. Large type, high contrast. No jargon. Show *why* for every verdict so he can trust or overrule it. |
| **Tech-savvy junior agent** ("Jenny", 8 mo) | Jenny | Replaces the printed checklist. Strict warning check. Copes with poor photos. | The checklist becomes the results view. Warning diff is shown precisely. |
| **Peak-season processor** ("Janet", Seattle) | Sarah | Bulk importer drops of 200–300 labels. | Batch upload with a progress view and a sortable/filterable results table, exceptions first. |
| **Deputy Director** (Sarah) | Sarah | Throughput, adoption, a credible proof-of-concept. | Simple metrics (time saved, % auto-matched) and clear trade-off documentation. |
| **IT / Security** (Marcus) | Marcus | Fits the restricted Azure network. No sensitive data stored. | Minimal outbound dependencies, a swappable model provider, stateless processing. |

**Accessibility baseline:** about half the team is over 50. Target WCAG 2.1 AA, a minimum 18 px base font, full keyboard operation, and verdicts conveyed by **text and icon**, never by color alone.

## 5. User stories

1. As an agent, I upload one label image, enter (or paste) the application values, and see each field marked Match / Needs Review / Mismatch within about 5 seconds.
2. As an agent, when a field is flagged I see the label value next to the application value, with differences highlighted, so I can decide quickly.
3. As an agent, I can overrule any verdict (e.g., accept "STONE'S THROW" vs "Stone's Throw").
4. As an agent, I see exactly where the government warning deviates from the required text: wrong words, missing parts, title-case prefix.
5. As an agent, I'm told plainly when an image is too poor to read, instead of getting a confident wrong answer.
6. As a peak-season processor, I upload many images plus one spreadsheet of application data and watch results arrive, with the problem labels at the top.
7. As a processor, I export batch results (CSV) for my records or hand-off.

## 6. Functional requirements

Priority: **P0** = must ship, **P1** = should ship, **P2** = stretch.

### 6.1 Input
| ID | Requirement | Pri |
|---|---|---|
| F-1 | Upload a single label image (JPG/PNG/WebP; PDF first page is P2) by drag-and-drop or a file picker. Max ~10 MB. | P0 |
| F-2 | Enter the expected application values in a simple form: brand name, class/type, alcohol content, net contents, bottler name/address, country of origin (optional), beverage type (spirits / wine / beer). | P0 |
| F-3 | "Load sample" button that pre-fills a demo label and its data, so evaluators and new users can try the tool immediately. | P0 |
| F-4 | Batch mode: upload N images plus a CSV/XLSX of application rows keyed by image filename. Provide a downloadable template. | P1 |
| F-5 | Validate inputs up front with plain-language errors ("This file isn't an image", "Row 12 has no matching image"). | P0 |

### 6.2 Extraction
| ID | Requirement | Pri |
|---|---|---|
| F-6 | Extract from the image: brand name, class/type, alcohol content (ABV and proof, if present), net contents, bottler/producer name and address, country of origin, and the full government warning text. | P0 |
| F-7 | Return a per-field confidence and a "not found" state. Never invent a value. | P0 |
| F-8 | Report an image-quality failure (blur, glare, too small, not a label) as its own outcome: **"Can't read: request a better image"**. | P0 |
| F-9 | Tolerate moderate rotation, perspective skew, and glare (Jenny's ask). | P2 |

### 6.3 Verification rules
The model extracts the values and deterministic code compares them. The model never issues the verdict, which keeps verdicts explainable, testable, and consistent.

| ID | Field | Rule | Pri |
|---|---|---|---|
| V-1 | Brand name | Normalize case, whitespace, curly vs. straight quotes, and punctuation. Exact after normalization → **Match**. Differs only by case/punctuation → **Match (noted)**. Small edit distance → **Needs Review**. Otherwise **Mismatch**. (Covers "STONE'S THROW" vs "Stone's Throw".) | P0 |
| V-2 | Class/type | Same normalization as V-1. | P0 |
| V-3 | Alcohol content | Parse the numeric ABV from formats such as "45% Alc./Vol.", "Alc. 45% by Vol.", "45% ABV". Numbers must be equal. If a proof value is present, check that proof = 2 × ABV. Unparseable → **Needs Review**. | P0 |
| V-4 | Net contents | Parse quantity and unit, convert to mL (mL, cL, L, fl oz), and compare values. "750 mL" = "75 cL" → **Match (noted)**. | P0 |
| V-5 | Government warning (text) | The text must match the 27 CFR §16.21 statement word for word, compared after normalizing whitespace and line breaks only. Any added, missing or changed word → **Mismatch**, with a word-level diff. Differences only in punctuation → **Needs Review** (it could be an OCR error). Missing → **Mismatch**. | P0 |
| V-6 | Government warning (prefix) | "GOVERNMENT WARNING:" must be all caps exactly as written. Title case or lower case → **Mismatch**. | P0 |
| V-7 | Government warning (bold) | Bold weight cannot be judged reliably from a photo, so report the model's assessment as **Needs Review**, never as Match. | P1 |
| V-8 | Bottler name/address, country of origin | Normalized fuzzy comparison. Default to **Needs Review** on any difference (addresses vary in format). Country of origin is required only when the item is marked as imported. | P1 |
| V-9 | Beverage-type rules | Apply type-specific requirements, e.g. ABV is optional for some wine and beer. A missing optional field → **N/A**, not Mismatch. | P1 |

Reference warning text (27 CFR §16.21):
> GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems.

### 6.4 Output and UX
| ID | Requirement | Pri |
|---|---|---|
| F-10 | One overall status per label: **All Clear**, **Needs Review**, **Issues Found**, or **Can't Read Image**, with text, icon, and color. | P0 |
| F-11 | A checklist view (one row per field) showing application value, label value, verdict, and a one-line reason. It mirrors Jenny's printed checklist. | P0 |
| F-12 | The image is shown next to the results, at a zoomable size. | P1 |
| F-13 | The agent can override any verdict. The override is shown visibly in the results and the export. | P1 |
| F-14 | Batch results table: per-label status, sorted with exceptions first, filter by status, and click a row for the detail view. | P1 |
| F-15 | Export results to CSV. | P1 |
| F-16 | Every error state tells the user what to do next, in plain English. | P0 |

## 7. Non-functional requirements

| ID | Category | Requirement |
|---|---|---|
| N-1 | **Latency** | Single label: p95 ≤ 5 s end to end. A visible progress indicator appears within 200 ms. This is the adoption gate ("If we can't get results back in about 5 seconds, nobody's going to use it"). |
| N-2 | **Batch throughput** | 300 labels finish in ≤ 5 min with bounded concurrency. The first result appears within about 5 s, and results stream in as they complete. One bad image never fails the whole batch. |
| N-3 | **Network constraints** | Keep outbound dependencies to a minimum and document them. The model provider sits behind one interface so it can be swapped for an in-tenant endpoint (e.g., Azure OpenAI or a self-hosted model) or a local OCR fallback without touching the rest of the app. No third-party front-end CDNs at runtime. |
| N-4 | **Privacy / data** | Stateless. Images and data are processed in memory and never written to disk or a database. Nothing sensitive is logged. Provider calls use no-retention settings where available. |
| N-5 | **Usability** | A first-time user completes a single-label check in under 1 minute with no instructions. No more than one primary action per screen. |
| N-6 | **Accessibility** | WCAG 2.1 AA, 18 px+ base font, verdicts never shown by color alone, keyboard navigable. |
| N-7 | **Reliability** | Model timeouts and errors degrade to "Needs Review / try again" and never to a false **Match**. |
| N-8 | **Deployability** | A public URL for evaluation. Containerized so it can be moved to Azure later (the existing platform). |

## 8. Accuracy and trust principles

1. **False "Match" is the worst error.** A missed violation costs more than a manual re-check, so whenever there is uncertainty the tool returns **Needs Review**.
2. **Show your work.** Every verdict comes with the extracted value and a reason.
3. **The human decides.** Overrides are first-class, which addresses Dave's point that "you need judgment."
4. **Be honest about limits.** Unreadable images and unverifiable properties (bold, type size) are labeled as such.

## 9. Success metrics

| Metric | Target (prototype) | How measured |
|---|---|---|
| p95 single-label latency | ≤ 5 s | Instrumented timings on the test set |
| Field-level verdict accuracy | ≥ 95% on the test set | Labeled evaluation set (see below) |
| False-Match rate on warning violations | 0 on the test set | Seeded violation cases |
| Batch: 300 labels | ≤ 5 min, 0 crashes | Load test |
| First-use task completion | < 1 min, unaided | Informal hallway test |

**Evaluation set:** about 20–40 labels made with AI image generation or sourced from public examples. It should include clean labels, case/punctuation variants (STONE'S THROW), wrong ABV, unit variants, a title-case "Government Warning", reworded and truncated warnings, a missing warning, and photos with glare or at an angle. Ground truth is kept in the repo and run as an automated test suite.

## 10. Technical approach (direction, not commitment)

- **Pipeline:** image → light preprocessing (resize, auto-orient) → **one** vision-model call returning structured JSON (fields, warning text, confidence, legibility flag) → deterministic rule engine (§6.3) → results.
- **Why a vision LLM rather than classic OCR:** labels are stylized (curved text, decorative fonts), and a single call that extracts and labels the fields avoids fragile layout heuristics. A fast model tier is required to fit the 5 s budget.
- **Why deterministic comparison:** it is explainable and unit-testable, and it can't hallucinate a "Match."
- **Provider abstraction:** this addresses Marcus's firewall concern. It also allows benchmarking several models for latency and accuracy.
- **Batch:** a server-side worker pool with a concurrency cap and per-item streaming (SSE or polling).
- Stack, model selection and detailed design: see [`TECHNICAL_DESIGN.md`](./TECHNICAL_DESIGN.md).

## 11. Risks and open questions

| Risk / question | Mitigation / assumption |
|---|---|
| The firewall may block the chosen cloud model endpoint in a real deployment | Provider interface plus a documented in-tenant/on-prem path. The prototype runs on a public host for evaluation. |
| A vision model may misread or "auto-correct" the warning text (hiding a violation) | The prompt asks for verbatim transcription with no correction. Seeded tests cover this. Low confidence → Needs Review. |
| Bold and type size can't be measured reliably from photos | Flag as Needs Review and document it as a limitation. |
| Where does application data come from without COLA? | **Assumption:** entered manually or provided as CSV for the prototype. |
| Are rules beyond matching in scope (e.g., misleading claims)? | **Assumption:** no. The prototype covers matching and the warning only. |
| Production PII, retention, and FedRAMP requirements | Out of scope. Stateless design keeps that path open. |
| Model latency variance | Fast model tier, image downscaling, timeouts with graceful fallback, and measurement in the test suite. |

## 12. Milestones

1. **M1, Core (P0):** single-label upload → extraction → rule engine → checklist results. Sample data. Deployed.
2. **M2, Trust and polish:** warning diff view, overrides, image viewer, error states, evaluation suite plus latency report.
3. **M3, Batch (P1):** multi-upload plus CSV, streaming results table, CSV export.
4. **M4, Stretch (P2):** robustness to skew and glare, PDF input, a local OCR fallback provider.

The order follows the brief: *"A working core application with clean code is preferred over ambitious but incomplete features."*

---

## Appendix A: Requirement traceability

| Source (README) | Signal | Requirement(s) |
|---|---|---|
| Sarah: "just... matching" | Core job to be done | G1, V-1–V-4 |
| Sarah: vendor pilot 30–40 s, "about 5 seconds" | Hard adoption gate | G3, N-1 |
| Sarah: "my mother could figure out", half the team over 50 | Usability and accessibility | G4, N-5, N-6, F-10, F-11 |
| Sarah / Janet: 200–300 at once | Batch | G5, F-4, F-14, N-2 |
| Marcus: standalone, no COLA | Scope boundary | Non-goals, F-2 |
| Marcus: Azure, outbound traffic blocked | Deployment constraint | N-3, N-8, §10 |
| Marcus: "not storing anything sensitive" | Data handling | N-4 |
| Dave: STONE'S THROW vs Stone's Throw, "you need judgment" | Fuzzy matching, human in the loop | V-1, F-13, §8 |
| Dave: 2008 phone system made things worse | Adoption risk | N-1, N-5, §8 |
| Jenny: warning must be exact, all caps, bold | Strict rule | G2, V-5–V-7 |
| Jenny: printed checklist | UI model | F-11 |
| Jenny: weird angles, glare | Robustness (stretch) | F-8, F-9 |
| Additional Context: field list, beverage types | Field scope | F-6, V-8, V-9 |
| Evaluation criteria: working core over ambition | Prioritization | §12 |

## Appendix B: Context intentionally not turned into requirements

The interviews include details that don't change the product: the school play, agent headcount in the 1980s, the $4.2M rebuild quote, FedRAMP paperwork time, and COLA's 2003 launch. They are useful background on organizational constraints (tight budget, slow procurement, history of failed tools), and they support the case for a small, low-risk, standalone prototype. They do not add functional scope.
