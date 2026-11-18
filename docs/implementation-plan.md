# Implementation Plan: Groww Weekly Review Pulse

Sources: [problemStatement.md](problemStatement.md) · [architecture.md](architecture.md)

The plan builds the pipeline from the data end forward. Each phase ends with something runnable and a clear exit check, so the project is never in a half-wired state. Scope is Play Store only (App Store is out of scope for now).

## Phase Overview

| Phase | Name | Outcome |
|---|---|---|
| 0 | Decisions and setup | Open questions settled, repo scaffolded, tooling working |
| 1 | Ingest and normalize | A clean review file for the last 8–12 weeks |
| 2 | PII scrubbing | Verified-safe corpus, raw data deleted |
| 3 | Theming (ML) | At most 5 themes from TF-IDF + NMF, every review assigned |
| 4 | Selection and composition | A one-page pulse draft |
| 5 | Validation gate | Pulse is checked against every rule before publish |
| 6 | MCP publishing | Doc created and Gmail draft made through MCP |
| 7 | Hardening and ops | Idempotent, scheduled, documented |

Phases are sequential, but 2 (PII) can be built in parallel with 1 using fixture data, and the MCP spike in Phase 0 de-risks Phase 6 early.

---

## Phase 0: Decisions and Setup

**Goal**: remove the unknowns that would otherwise cause rework.

**Tasks**
1. Settle the open questions in architecture.md §11:
   - Play Store access method. Default: a library reading the public listing. Record the decision against the "public exports only" constraint.
   - Which Docs and Gmail MCP servers will be used.
   - Doc strategy (new doc per week or one standing doc) and recipient (self or alias).
   - Language and LLM provider. Assumed: Python and a Claude model (used for selection and composition; theming is ML).
2. Scaffold the repo per architecture.md §5: `src/pulse/`, `config/`, `prompts/`, `tests/`, and a gitignored `data/`.
3. Set up dependencies, a linter and formatter, a test runner, and a `.env.example` (LLM key only; no Google secrets).
4. Create `config/pulse.yaml` with the structure from architecture.md §6.
5. **MCP spike**: connect to the chosen Docs and Gmail MCP servers, list their tools, create a throwaway doc and a throwaway draft by hand. Record the real tool names and argument shapes.

**Exit check**: `pytest` runs (even with no tests), and the spike produced a real test doc and draft through MCP.

**Risks**: the MCP servers don't expose "create doc" or "create draft". Surface this now and pick different servers.

---

## Phase 1: Ingest and Normalize

**Goal**: a clean, deduplicated review file for the lookback window.

**Tasks**
1. Define `models.py`: `RawReview`, `Review` (schema from architecture.md §3.2).
2. Define the `ReviewSource` interface in `ingest/base.py`.
3. Implement `ingest/play_store.py` for `com.nextbillion.groww`, locale `en_IN`:
   - Page newest-first and stop at the window boundary.
   - Throttle and retry with backoff.
4. Implement `normalize.py`:
   - Map to the common schema and drop reviewer identity fields at this boundary.
   - Hash the id, filter to the window, dedupe, and drop reviews under the minimum length.
5. Implement the run directory handling in `pipeline.py` (`data/<run_id>/`, with `run_id` as `YYYY-Www`) and a CLI command `run-stage ingest`.
6. Tests: parse recorded fixture responses (no network), the date window edge cases, and dedupe.

**Exit check**: running the ingest and normalize stages produces `reviews.jsonl` with the expected count, dates inside the window, and no identity fields.

**Risks**: library breakage or rate limiting. Mitigate with fixtures for tests and a cap on pages per run.

---

## Phase 2: PII Scrubbing

**Goal**: guarantee that nothing downstream can contain reviewer PII.

**Tasks**
1. Implement `pii.py` with two functions sharing one pattern set: `scrub(text)` and `detect(text)`.
   - Patterns: email, phone, URL, PAN, Aadhaar, account or folio-like digit runs, UPI id, order or reference ids.
   - Name redaction pass for greeting-style names.
2. Implement the exclusion rule: a review whose redaction changes more than the configured share of its text is flagged `quote_eligible = false`.
3. Write `reviews_clean.jsonl`, then delete `raw_reviews.jsonl`.
4. Tests: a table of positive and negative examples per pattern, including Indian formats (10-digit mobile with and without +91, PAN `ABCDE1234F`, 12-digit Aadhaar with spaces).
5. Manually review a sample of about 100 scrubbed reviews for leaks and over-redaction, and tune.

**Exit check**: `detect()` finds nothing on the entire cleaned corpus, the raw file is gone, and the manual sample review is clean.

**Risks**: name redaction misses or over-fires. Accept imperfect recall on names, and rely on the final validate gate and on quote selection preferring reviews without redaction.

---

## Phase 3: Theming

**Goal**: assign every review to at most 5 themes.

### What the W44 corpus looks like (drives the strategy)

Read from `reviews_clean.jsonl` (1,596 reviews, 2026-08-10 to 2026-10-31):

- **Small**: median 20 words, p90 63, about 45k words in total. A scikit-learn topic model handles it in seconds; no vector store or GPU is needed.
- **Polarised**: 671 one-star (42%) and 555 five-star (35%), with few in between. Complaints and praise are about the same products, so a theme must describe a *topic*, not a sentiment. Sentiment already lives in the rating, and Phase 4 uses it for severity.
- **Many reviews touch more than one topic**: a keyword probe found about 45% mention two or more areas, and about 14% (227) match none, mostly short praise or feature requests. Single-label assignment therefore needs a "primary topic" rule, and `other` must be expected.
- **Dominant topics** (keyword probe, indicative only): trading and F&O (charts, orders, scalper, stop-loss; about 550), app performance and bugs (about 420), support and service (about 250), money movement (payments, withdrawals, margin; about 215), charges and brokerage (about 200), mutual funds and SIP (about 225), ease of use (about 360, mostly 4-5 stars). KYC and onboarding is small (about 90) but 80% of it is negative.
- **Complaints cluster**: of the 759 reviews rated 1-2, trading, performance, and support dominate (about 270, 270, 200).

### Strategy: TF-IDF + NMF topic modelling, with bisection and a hard cap (no LLM)

Theming uses machine learning, not an LLM. The algorithm was chosen by running candidates on the W44 corpus and scoring each on agreement with the independent keyword buckets (NMI), stability across random seeds (ARI), how strongly clusters split by sentiment, and cluster balance:

| Method | Keyword agreement (NMI) | Seed stability (ARI) | Notes |
|---|---|---|---|
| **TF-IDF + NMF** | 0.49–0.55 | 1.00 | Readable topics, least sentiment split. Chosen |
| TF-IDF → LSA + k-means | 0.44 | 0.52–0.98 | One junk cluster holding about half the reviews |
| LDA (counts) | 0.29 | 0.10–0.24 | Unstable and mixed topics |
| NMF with KL loss | 0.34–0.36 | 0.93 | Balanced sizes, but less coherent topics |
| Fine NMF (k=10–12), keep the top 5 | 0.42–0.46 | 0.72–0.96 | Cleanest themes, but `other` grows to 31–44% |
| Merge fine topics by term or co-occurrence similarity | 0.38–0.48 | – | Chains into one blob, or groups complaints together (sentiment again) |

Sentence embeddings were not adopted: they add torch (about 1 GB) and a model download, and on this polarised corpus embedding clusters tend to split by sentiment.

Chosen pipeline (`themes.py`):

1. **Vectorize**: TF-IDF over unigrams and bigrams (`min_df` 4, `max_df` 0.4, sublinear tf). Sentiment, praise and filler words are removed from the vocabulary because the rating already carries sentiment and Phase 4 uses it for severity. A review with no topic words (about 1%, e.g. "nice app") goes to `other`.
2. **Topics**: NMF with `themes.max` (5) components and deterministic `nndsvda` initialisation. Each review takes its highest-weighted topic.
3. **Bisect**: plain NMF at k=5 leaves one 40% catch-all ("update / chart / working"). Any topic holding more than `split_share` (30%) of the reviews is split with a 2-topic NMF over its members, at most `max_splits` times, and only when both halves are at least `min_theme_share`. If a split goes over the cap, the smallest topic is folded into `other` (THM-1).
4. **Confidence**: `high` when the best topic holds at least `high_confidence` (50%) of the review's topic weight, otherwise `low`.
5. **Names**: the top three terms by weight, skipping repeats by five-letter stem and weak words ("high", "open"), e.g. "Charges / Brokerage / Profit". A theme reuses the previous run's name when their top-10 terms overlap by Jaccard 0.3 or more, so trend names stay stable.

W44 result: 5 themes (update / chart / option 27%, customer support 21%, friendly / mutual funds 18%, trading / market 13%, charges / brokerage 12%), `other` 8%, low confidence 18%, one split, about 3 seconds, no API key.

### Tasks

1. Implement `themes.py`: vectorize, NMF, bisection and cap, confidence, naming, name reuse from the previous run. Sorting reviews by id makes the result independent of input order (THM-7).
2. Persist `themes.json` (name, definition, top terms, review ids, low-confidence ids, `method`) and `themes_stats.json` (counts, shares, `other` share, low-confidence share, exit checks, clustering diagnostics).
3. Tests on a synthetic corpus with planted topics: every planted topic recovered as one theme, generic praise to `other`, themes contain all ratings (topic, not sentiment), cap and fold, bisection, order independence, confidence, naming, name reuse, abort on no vocabulary or too few themes.
4. **Independent check**: compare assignments against the coarse keyword bucket map and report agreement per theme. This is a diagnostic, not a gate; a low-agreement theme prompts a manual read.
5. Manual check: read about 15 reviews per theme plus 30 `other` reviews and confirm the assignments look right.

**Exit check**: `themes.json` has 5 or fewer themes, 100% of reviews are assigned, `other` is at most about 20% of the corpus, no theme is under about 5%, and a human spot check agrees with the assignments (at least 80% of sampled reviews judged correct).

**Risks**
- *Bag-of-words cannot merge synonyms*: "withdrawal stuck" and "money not credited" share no words. Bigrams and the vocabulary filter help; the keyword cross-check exposes systematic misses.
- *Mixed themes when the corpus has more natural topics than the cap*: W44 has about 8 natural topics, so some themes combine two (ease of use with mutual funds). Accept this, or tune `split_share` and the generic-word list; never raise the cap above 5.
- *Names read as keyword lists*: they come from top terms, not prose. Name reuse keeps them stable week to week.
- *Unstable themes between runs*: deterministic initialisation and id-sorted input make a given corpus reproducible; name reuse handles corpus drift.

---

## Phase 4: Selection and Composition

**Goal**: produce a one-page pulse draft from the themed data.

**Tasks**
1. Implement `select.py`:
   - Score themes on volume and severity using the configured weights, then take the top 3.
   - Pick quote candidates from `quote_eligible` reviews of 20–200 characters, ranked by theme relevance and clarity, mixing ratings across the 3 quotes.
   - Quotes are verbatim substrings, trimmed only at sentence or clause boundaries with an ellipsis.
2. Write `prompts/compose.md` with the template from architecture.md §3.6. Quotes are injected as fixed strings. The model writes only theme summaries and 3 actions.
3. Implement `compose.py` and write `pulse.md`.
4. Add the `--dry-run` CLI path, which runs through compose and prints the pulse.
5. Tests: ranking math, quote substring property, template assembly with a stubbed LLM.

**Exit check**: a dry run on real data prints a pulse with 3 themes, 3 quotes and 3 actions that a reader finds coherent and useful.

**Risks**: generic action ideas. Tune the prompt to require each action to name the theme and a concrete next step.

---

## Phase 5: Validation Gate

**Goal**: make it impossible to publish a note that breaks the rules.

**Tasks**
1. Implement `validate.py` with the checks from architecture.md §3.7:
   - Word count at most 250, using one shared counter.
   - Exactly 3 themes (drawn from the clustered set), 3 quotes (each an exact substring of the clean corpus) and 3 actions (each referencing a listed theme).
   - PII detector finds nothing in the final text.
   - Required sections present in order.
2. Wire the retry loop: on failure, re-run compose with the error list, at most 2 times, then exit non-zero and write `validation.json`.
3. Define distinct exit codes for ingest, validation and publish failures.
4. Tests: one failing case per rule, and the retry-then-abort path.

**Exit check**: each rule has a test that fails when the rule is broken, and a full dry run passes the gate.

---

## Phase 6: MCP Publishing

**Goal**: put the pulse in Google Docs and create the Gmail draft, with no direct Google API code.

**Tasks**
1. Implement `mcp_gateway.py` with two operations: `docs.publish(title, body) -> doc_url` and `gmail.create_draft(to, subject, body) -> draft_id`.
   - Map them to the real tool names found in the Phase 0 spike, through a small adapter.
   - On startup, list tools and fail fast if an expected one is missing.
2. Wire the publish stage: Docs first, then the Gmail draft with the pulse text and the Doc link, then write `publish_result.json`.
3. Never send mail. Create drafts only.
4. Tests against a fake MCP server that records calls: order (Doc before draft), arguments, and that `--dry-run` makes no calls.
5. **First live run**: real data, real servers, recipient set to your own address.

**Exit check**: one end-to-end run creates a readable Google Doc and a Gmail draft in your account that links to it, and the draft body matches the pulse.

**Risks**: Doc formatting from plain text or Markdown renders poorly. Try the MCP server's supported formats, and keep the pulse structure simple (headings and bullets).

---

## Phase 7: Hardening and Ops

**Goal**: make the weekly run safe to repeat and easy to operate.

**Tasks**
1. **Idempotency**: key on `run_id`. If `publish_result.json` exists, skip or update instead of duplicating, with `--force` to override. If the Doc exists but the draft failed, resume at the draft step.
2. **Failure handling** per architecture.md §8: abort below the minimum review count (default 50), abort if the Play Store fetch fails, and abort before Gmail if Docs fails.
3. **Logging**: counts and ids only, never review text. Check this with a test that greps the logs of a fixture run for review text.
4. **Scheduling**: a weekly cron or scheduler entry with failure alerts keyed on the exit codes.
5. **Docs**: a README with setup, config reference, how to run each stage, how to rotate or replace MCP servers, and troubleshooting.
6. **Final review**: run the full test suite, a clean-checkout run, and a final PII audit of the Doc and draft contents.

**Exit check**: two consecutive scheduled runs behave correctly (the second is a no-op or a clean update), and the README lets someone else set it up from scratch.

---

## Cross-Cutting Practices

- **Fixtures first**: every stage is testable offline with recorded or synthetic data and a stubbed LLM. Live calls are limited to manual smoke runs.
- **Stage isolation**: each stage reads and writes files in `data/<run_id>/`, so a stage can be re-run without redoing the earlier ones.
- **Privacy review at each phase boundary**: confirm nothing with reviewer identity is written to disk, logged, or sent to the LLM or MCP.
- **Prompts are versioned files** in `prompts/`. Changes to them get a before and after sample in the commit message.

## Definition of Done (from the problem statement)

- [ ] Reviews from the last 8–12 weeks imported
- [ ] At most 5 themes; the pulse highlights the top 3
- [ ] Pulse has 3 verbatim quotes and 3 grounded action ideas, in 250 words or fewer
- [ ] No PII in any artifact
- [ ] Pulse is in Google Docs and a Gmail draft contains it or links to it, both created via MCP
