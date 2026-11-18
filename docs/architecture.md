# Architecture: Groww Weekly Review Pulse

Source requirements: [problemStatement.md](problemStatement.md)

## 1. Goals and Non-Goals

**Goals**
- Turn public Groww Play Store reviews (last 8–12 weeks) into a one-page weekly pulse of at most 250 words.
- The pulse has the top 3 themes (out of at most 5 clustered), 3 verbatim user quotes, and 3 action ideas.
- Publish the pulse to Google Docs and create a Gmail draft, both **through MCP servers**.
- Guarantee no PII appears in any stored or published artifact.

**Non-Goals**
- No direct Google API or OAuth client code. Auth lives in the MCP servers.
- No scraping behind store logins and no ToS-violating automation.
- No auto-sending email. The output is a draft only.
- No real-time or streaming analysis. This is a weekly batch job.
- No Apple App Store reviews in v1. Play Store is the only source for now (see §10).

## 2. System Context

```
 ┌──────────────┐   public data    ┌───────────────────────────┐
 │ Play Store   │ ───────────────► │   Pulse Pipeline (batch)  │
 └──────────────┘                  │                           │
                                   │   ┌─────────────────────┐ │   LLM API
                                   │   │ LLM (copy only)     │◄┼──────────────
                                   │   └─────────────────────┘ │
                                   │        MCP client         │
                                   └───────┬───────────┬───────┘
                                  MCP tools│           │MCP tools
                                   ┌───────▼──────┐ ┌──▼───────────┐
                                   │ Google Docs  │ │ Gmail        │
                                   │ MCP server   │ │ MCP server   │
                                   └───────┬──────┘ └──┬───────────┘
                                           ▼           ▼
                                      Pulse Doc    Draft email
```

The pipeline is a single batch program, run weekly by cron or a scheduler or on demand. It is an **MCP client**. The Docs and Gmail MCP servers own credentials and the Google API calls.

## 3. Pipeline Stages

Each stage reads and writes plain files under `data/<run_id>/`, so any stage can be re-run or inspected on its own.

```
 ingest ─► normalize ─► scrub PII ─► theme ─► select ─► compose ─► validate ─► publish
```

| # | Stage | Input | Output | Notes |
|---|---|---|---|---|
| 1 | **Ingest** | Config (app ids, window) | `raw_reviews.jsonl` | Play Store fetcher, behind a common source interface |
| 2 | **Normalize** | Raw records | `reviews.jsonl` | Common schema, date window filter, dedupe, drop empty text |
| 3 | **Scrub PII** | Normalized reviews | `reviews_clean.jsonl` | Remove reviewer identity fields and redact PII patterns in text |
| 4 | **Theme** | Clean reviews | `themes.json` | At most 5 themes, each review assigned to one theme |
| 5 | **Select** | Themes and reviews | `selection.json` | Rank to the top 3 themes and pick candidate quotes |
| 6 | **Compose** | Selection | `pulse.md` | One-page note: themes, 3 quotes, 3 actions |
| 7 | **Validate** | `pulse.md` | Pass/fail report | Word count, quote verbatim, PII, structure |
| 8 | **Publish** | Validated pulse | Doc URL, draft id | Docs MCP then Gmail MCP |

### 3.1 Ingest

- **Play Store**: package `com.nextbillion.groww`, locale `en_IN`. Fetch reviews within the lookback window (default 12 weeks, configurable from 8 to 12), newest first, and stop at the window boundary.
- The fetcher implements `fetch(window) -> Iterable[RawReview]`. A second store (for example the Apple App Store) can be added later as another class without touching later stages.
- The fetcher throttles requests, retry with backoff, and read only publicly accessible endpoints or exports. Anything requiring a store login is out of scope.
- Raw output is kept only transiently. It can contain reviewer names, so it is excluded from version control and deleted after the scrub stage (see §7).

### 3.2 Normalize

Common schema (reviewer identity fields are dropped at this boundary and never enter the model):

```json
{
  "id": "sha256(store + source_review_id)",
  "store": "play",
  "rating": 1,
  "title": "string | null",
  "text": "string",
  "date": "2026-10-20",
  "app_version": "string | null",
  "lang": "en"
}
```

- `id` is a one-way hash, so the stored id doesn't expose the store's review id.
- Filter to the date window, dedupe on `id` and on exact-text duplicates, and drop reviews with fewer than N characters (default 15).
- Non-English reviews are kept only if the theme stage can cluster them. Quotes are chosen from English reviews only so quotes stay verbatim and readable.

### 3.3 Scrub PII

Defense in depth, applied before any text reaches the LLM or any file that outlives the run:

1. **Structural**: no username, avatar, reviewer id or device fields exist in the normalized schema.
2. **Pattern redaction** in `title` and `text`: emails, phone numbers, URLs, PAN, Aadhaar, account or folio-like digit runs, UPI ids, and order or reference ids, replaced with `[redacted]`.
3. **Name redaction**: a name entity pass (for example "Hi Rahul, ...") replaces person names with `[name]`.
4. A review whose PII redaction changes more than a configured share of its text is **excluded from quote candidates**. A quote must not be a mangled string.

### 3.4 Theme (max 5)

Theming is machine learning, not an LLM: TF-IDF features and NMF topic modelling (scikit-learn).

- **Features**: TF-IDF over unigrams and bigrams. Sentiment and filler words ("good", "worst", "app") are left out of the vocabulary, so themes form around topics rather than star ratings. A review with no topic words ("nice app") goes to `other`.
- **Topics**: NMF with as many topics as the cap (5). Each review takes its highest-weighted topic. Any topic holding more than 30% of reviews is bisected with a 2-topic NMF over its members, so one catch-all topic cannot swallow the corpus; if that goes over the cap, the smallest topic is folded into `other`. The cap is enforced in code.
- Each theme has a `name`, a `definition`, its top terms and a list of assigned review ids. Each review is assigned to exactly one theme or to `other`, which doesn't count toward the 5. Confidence is `high` when the review's best topic holds at least half its topic weight.
- **Names** come from each theme's top terms (e.g. "Charges / Brokerage / Profit"). A theme reuses last run's name when their top terms overlap enough, so names stay stable for the week-over-week comparison (see §10).
- **Determinism**: NMF uses deterministic initialisation and reviews are sorted by id first, so the same corpus always gives the same themes. No network or API key is needed.

### 3.5 Select

- **Top 3 themes** are ranked by a score combining volume (share of reviews) and severity (share of ≤2-star reviews). Weights are in config. The default favors volume with severity as a tiebreaker.
- **Quote candidates**: for each top theme, take reviews with 20–200 characters of substantive text, rank by relevance to the theme definition and clarity, and prefer a mix of ratings across the three quotes.
- The quote is a **verbatim substring** of the cleaned review text. Trimming is allowed only at sentence or clause boundaries, marked with an ellipsis.

### 3.6 Compose

The LLM drafts the pulse from `selection.json`. Quotes are passed as fixed strings and the model is told to insert them unchanged. It never writes quote text itself.

Template (target ≤250 words total):

```
Groww Weekly Review Pulse — <week range>
<N> reviews · avg rating <x.x> · Play Store

Top themes
1. <Theme> (<share>%) — <one-line summary>
2. ...
3. ...

What users said
• "<verbatim quote>" — <rating>★, <store>
• "..."
• "..."

Action ideas
1. <concrete step tied to theme 1>
2. ...
3. ...
```

### 3.7 Validate (gate before publish)

Publishing is blocked unless every check passes. On failure the pipeline retries compose with the error list, up to 2 times, then exits non-zero without publishing.

| Check | Rule |
|---|---|
| Length | ≤250 words, counted the same way in code and in the spec |
| Themes | Exactly 3 listed, all drawn from the ≤5 clustered themes |
| Quotes | Exactly 3, each an exact substring of a cleaned review in the run's corpus |
| Actions | Exactly 3, each referencing a listed theme |
| PII | The scrubber's patterns find no match in the final text, and no reviewer fields appear |
| Structure | Required sections present in order |

### 3.8 Publish (MCP)

Order matters: the Doc is created first so the draft can link to it.

1. **Docs MCP**: create the pulse document (or append a new dated section to a standing "Groww Weekly Pulse" doc). Capture the returned doc URL.
2. **Gmail MCP**: create a **draft** to the configured recipient (self or alias). The body is the pulse text plus the Doc link. Capture the draft id.
3. Write `publish_result.json` with the doc URL, draft id and timestamp.

No step sends mail. The user reviews and sends the draft manually.

> **As built (Phase 6)**: the chosen server, `basic-google-workspace-mcp`, has only `append_google_doc` and `send_gmail`. So step 1 appends a dated section to a standing Doc (`doc.document_id`), and step 2 *sends* the email to `email.to` instead of drafting it, only when `email.send` is true and at most once per run. See [phase0-decisions.md](phase0-decisions.md).

## 4. MCP Integration Design

```
 Pipeline ── MCP client (stdio/HTTP transport) ──► Docs MCP server ──► Google Docs
                                              └──► Gmail MCP server ──► Gmail
```

- A thin `McpGateway` wraps the MCP client session and exposes only the two operations the pipeline needs:
  - `docs.publish(title, body) -> doc_url`
  - `gmail.create_draft(to, subject, body) -> draft_id`
- Tool names and argument shapes differ between MCP server implementations, so the mapping from these two operations to the server's actual tools lives in a small config or adapter. On startup the gateway lists the server's tools and fails fast if the expected ones are missing.
- Credentials are handled entirely by the MCP servers. The pipeline's config holds only server launch commands or endpoints, never tokens.
- **Idempotency**: the run id is `YYYY-Www` of the target week. Before creating, the gateway checks `publish_result.json` for that run. If a doc or draft already exists, it updates or skips instead of duplicating. A `--force` flag overrides this.
- **Dry run**: `--dry-run` runs every stage up to and including validate, prints the pulse, and makes no MCP calls.

## 5. Proposed Repository Layout

```
MCP/
├── docs/
│   ├── problemStatement.md
│   └── architecture.md
├── config/
│   └── pulse.yaml            # app ids, window, weights, recipient, MCP servers
├── src/pulse/
│   ├── cli.py                # entry point: run, run-stage, dry-run
│   ├── pipeline.py           # stage orchestration, run directory handling
│   ├── models.py             # Review, Theme, Selection, Pulse (typed schemas)
│   ├── ingest/
│   │   ├── base.py           # ReviewSource interface
│   │   └── play_store.py
│   ├── normalize.py
│   ├── pii.py                # scrubber and PII detector (shared with validate)
│   ├── llm.py                # LLM client wrapper, structured output, retries
│   ├── themes.py             # TF-IDF + NMF clustering (no LLM)
│   ├── select.py
│   ├── compose.py
│   ├── validate.py
│   └── mcp_gateway.py        # Docs and Gmail via MCP
├── prompts/                  # select.md, compose.md (versioned prompt text)
├── data/                     # per-run artifacts (gitignored)
└── tests/
```

Language is not fixed by the problem statement. Python is the assumed default because of the ecosystem for review fetching, the MCP client SDK and structured LLM output.

## 6. Configuration

```yaml
app:
  name: Groww
  play_package: com.nextbillion.groww
  play_locale: en_IN
window_weeks: 12            # 8–12
min_review_chars: 15
themes:
  max: 5
  top_k: 3
  weights: { volume: 0.6, severity: 0.4 }
note:
  max_words: 250
  quotes: 3
  actions: 3
email:
  to: "<self or alias>"
mcp:
  docs:  { command: "<launch command or URL>" }
  gmail: { command: "<launch command or URL>" }
llm:
  model: "<model id>"
  temperature: 0
```

Secrets, including the LLM API key, come from the environment and are never written to the config file.

## 7. Data and Privacy

- **PII boundary**: reviewer identity is dropped in the normalize stage, text is redacted in the scrub stage, and only scrubbed data goes to the LLM, to disk (beyond the transient raw file) and to MCP.
- `raw_reviews.jsonl` is written to a temp location, deleted when the scrub stage completes, and never committed.
- `data/` is gitignored. Retained per-run artifacts are `reviews_clean.jsonl`, `themes.json`, `selection.json`, `pulse.md`, `validation.json` and `publish_result.json`.
- The final validate step re-runs the PII detector on the exact text sent to Docs and Gmail.
- Logs record counts and ids only, never review text.

## 8. Error Handling

| Failure | Behavior |
|---|---|
| The Play Store fetch fails or returns zero reviews | Abort with a clear message |
| Fewer than a minimum number of reviews (default 50) | Abort with a clear message rather than publishing a thin pulse |
| LLM output fails schema validation | Retry with the validator error, max 2 retries, then abort |
| Validation fails after retries | Abort, write `validation.json`, publish nothing |
| Docs MCP call fails | Abort before Gmail so no draft points at a missing doc |
| Gmail MCP call fails after the Doc exists | Record the doc URL in `publish_result.json`. A re-run resumes at the draft step |

Exit codes are distinct for ingest, validation and publish failures so a scheduler can alert accordingly.

## 9. Testing Strategy

- **Unit**: PII scrubber (positive and negative patterns), normalize and dedupe, word counter, theme-cap enforcement, quote substring check, ranking math.
- **Contract**: fixtures of recorded Play Store responses, so parsing is tested without network calls.
- **Pipeline**: a golden-file run on a small synthetic review set with a stubbed LLM, asserting that the pulse meets every validate rule.
- **MCP**: tests against a fake MCP server that records tool calls, asserting call order (Doc before draft), idempotency, and that the dry run makes none.
- **Manual smoke test**: one real run with the draft sent to the author's own address.

## 10. Extensions (out of scope for v1)

- Apple App Store reviews via Apple's public customer-reviews feed, as a second `ReviewSource` (needs the Groww iOS app id).
- Week-over-week trend: persist taxonomies and compare theme share to the previous run.
- A rating and version breakdown (for example, which app version drove a spike).
- Scheduled execution with failure notifications.
- A Slack or other delivery surface behind the same `McpGateway` interface.

## 11. Open Questions

1. **Play Store access method**: the Play Console export needs owner access. Without it, a third-party library reading the public listing is the practical option, and its compliance with the "public exports only, no ToS-violating automation" constraint should be explicitly accepted or replaced.
2. **Which Docs and Gmail MCP servers** the environment provides, which settles the tool names the adapter maps to.
3. **Doc strategy**: a new doc per week or one standing doc with a new section per week.
4. **Recipient**: self or a shared alias.
5. **Implementation language and LLM provider** (assumed Python and a Claude model).
