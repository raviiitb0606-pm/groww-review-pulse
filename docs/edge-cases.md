# Edge Cases and Corner Scenarios: Groww Weekly Review Pulse

Sources: [problemStatement.md](problemStatement.md) · [architecture.md](architecture.md) · [implementation-plan.md](implementation-plan.md)

Each case lists the scenario, the expected behavior, and the stage where it is handled. IDs (for example `ING-3`) can be referenced from tests. Severity: **H** breaks a hard constraint (privacy, length, verbatim quotes, MCP-only), **M** degrades output quality or run reliability, **L** cosmetic or rare.

## 1. Ingest (Play Store)

| ID | Sev | Scenario | Expected behavior |
|---|---|---|---|
| ING-1 | M | Fetch returns zero reviews | Abort with a clear message and ingest exit code. Publish nothing |
| ING-2 | M | Fetch returns far fewer reviews than the minimum (default 50) | Abort rather than publish a thin pulse; message states the count and threshold |
| ING-3 | M | Rate limiting, HTTP 429 or 5xx, timeout mid-pagination | Retry with backoff up to a cap. If still failing, abort. Never publish from a partial fetch unless the partial result still meets the minimum and is flagged in the footer |
| ING-4 | M | Library or listing format changes and the parser throws or returns an unexpected shape | Fail fast with a schema error naming the missing field; do not guess |
| ING-5 | L | Pagination never reaches the window boundary (app has few reviews) | Stop when pages run out; use whatever exists in the window |
| ING-6 | M | Reviews arrive out of order or the "newest first" assumption breaks | Do not stop at the first out-of-window review; require N consecutive out-of-window items, or filter after fetch |
| ING-7 | L | A runaway fetch (huge review volume) | Cap on pages or total reviews per run; log that the cap was hit |
| ING-8 | M | Review dates in a different timezone, or exactly at the window boundary | Compare in one fixed timezone (IST). Boundary is inclusive at the start and exclusive at the end, documented and tested |
| ING-9 | L | Review edited after posting; the same source id appears with new text | Keep the latest version, deduped on the hashed id |
| ING-10 | H | The fetch path would require a login or a ToS-violating technique | Out of scope; not implemented. The fetcher reads only public endpoints |

## 2. Normalize

| ID | Sev | Scenario | Expected behavior |
|---|---|---|---|
| NRM-1 | M | Empty text, whitespace-only text, or rating-only review | Dropped |
| NRM-2 | L | Text shorter than the minimum length ("good", "ok") | Dropped from theming, counted in a `dropped_short` stat |
| NRM-3 | M | Exact duplicate texts across different reviewers (spam, copy-paste) | Deduped to one; counted in stats so volume is not inflated |
| NRM-4 | M | Near-duplicate spam campaigns (same text with a changed digit) | Optional near-duplicate collapse; if not implemented, listed as a known limitation |
| NRM-5 | M | Non-English, Hinglish or mixed-script reviews (Hindi, Tamil, transliterated Hindi) | Kept for theming. Excluded from quote candidates unless English |
| NRM-6 | L | Emoji-only or emoji-heavy text | Emoji-only is dropped as empty. Emoji inside a quote is kept as-is |
| NRM-7 | L | Very long reviews (thousands of characters) | Truncated for LLM input with a marker. Quote eligibility uses the 20–200 character rule on the selected span |
| NRM-8 | M | Unicode oddities: smart quotes, zero-width characters, combining marks, mixed normalization forms | Normalize to NFC once at this stage. Quote substring checks run against the normalized text |
| NRM-9 | L | Missing optional fields (no title, no app version) | Allowed as null. Nothing downstream assumes they exist |
| NRM-10 | M | Rating outside 1–5 or non-integer | Row rejected and counted |
| NRM-11 | M | All reviews are the same rating (all 5 or all 1) | Pipeline proceeds; severity score is degenerate, and the ranking falls back to volume |
| NRM-12 | L | Hash collision or the same source id reused across stores | Id includes the store prefix. A collision is treated as a duplicate |

## 3. PII Scrubbing

| ID | Sev | Scenario | Expected behavior |
|---|---|---|---|
| PII-1 | H | Email in text | Replaced with `[redacted]` |
| PII-2 | H | Phone formats: `9876543210`, `+91 98765 43210`, `098765-43210`, spaced or hyphenated | All redacted |
| PII-3 | H | PAN (`ABCDE1234F`), Aadhaar (12 digits, spaced or grouped 4-4-4) | Redacted |
| PII-4 | H | Account, folio, demat or client id style digit runs, UPI ids (`name@bank`) | Redacted |
| PII-5 | H | Order, transaction or reference ids ("ref no 8837261") | Redacted |
| PII-6 | H | URLs, including ones with the user's handle or a tracking token | Redacted |
| PII-7 | H | A person's name in a greeting or sign-off ("Regards, Rahul", "Hi Priya") | Replaced with `[name]`. Imperfect recall accepted, so the final validate gate and quote preference reduce exposure |
| PII-8 | M | Over-redaction: a date, price or percentage that resembles an ID ("₹10,000", "12 digit") | Patterns tuned so ordinary numbers, prices, and short numerics survive. Covered by negative tests |
| PII-9 | M | PII obfuscated to evade filters ("nine eight seven six..." or "name at gmail dot com") | Best effort. Known limitation; validate gate catches the standard forms |
| PII-10 | M | Redaction changes more than the configured share of a review | Review marked `quote_eligible = false`; still usable for theming |
| PII-11 | H | Raw file with reviewer names left on disk after a crash mid-run | Raw file is written to a temp location and deleted in a `finally`. Startup cleans stale raw files from previous runs |
| PII-12 | H | PII appears in logs or exception messages | Logs hold counts and ids only. Exceptions never include review text. A test greps fixture-run logs |
| PII-13 | H | PII that was missed is chosen as a quote | Final validate runs the detector on the finished pulse; any hit blocks publish |
| PII-14 | M | The brand name or a public figure's name is flagged as a person's name | The allowlist (Groww, the product feature names) is excluded from name redaction |
| PII-15 | M | Reviews mentioning a third party's personal details (a family member's account) | Treated the same as any PII under the patterns; text-level mentions without identifiers are retained |

## 4. Theming

| ID | Sev | Scenario | Expected behavior |
|---|---|---|---|
| THM-1 | H | LLM proposes more than 5 themes | The cap is enforced in code: merge down to 5, remainder to `other` |
| THM-2 | M | LLM returns fewer than 3 themes | The pulse still needs 3. Fall back to splitting the largest theme, or abort with a clear message if the data cannot support 3 |
| THM-3 | M | A review is missing from the assignments, assigned twice, or assigned an unknown id | Output rejected with the validator error fed back; bounded retry, then abort |
| THM-4 | M | A single theme dominates (90% of reviews) | Allowed. The pulse notes the concentration; the other two top themes are still taken from the next ranked |
| THM-5 | M | Most reviews fall in `other` | If `other` exceeds a threshold (default 40%), warn in the footer and log. Consider a re-cluster pass |
| THM-6 | M | Malformed JSON, truncated output, or a refusal from the LLM | Bounded retry with the error. Abort on repeated failure |
| THM-7 | M | Corpus too large for one call | Batched. Candidate themes consolidated in a second pass. Batch order must not change the result materially (temperature 0, stable sort by id) |
| THM-8 | L | Two themes with overlapping definitions (KYC vs. onboarding) | Consolidation prompt asked to merge near-duplicates. Overlap tolerated if the assignments are disjoint |
| THM-9 | M | Theme names are unstable between weeks | Names persisted per run; trend comparison deferred, noted as a known limitation |
| THM-10 | L | A review mentions several themes | Assigned to its dominant one only |
| THM-11 | M | Sarcasm or mismatched rating ("great app, can't withdraw", 5 stars) | Themed on content, not rating. Severity uses the star rating, so a known limitation is noted |
| THM-12 | H | Review text contains instructions aimed at the LLM ("ignore previous instructions...") | Treated strictly as data: reviews are delimited in the prompt and the system prompt states that review content is untrusted. Output is schema-validated, so injected output shapes are rejected |

## 5. Selection

| ID | Sev | Scenario | Expected behavior |
|---|---|---|---|
| SEL-1 | M | Tie between themes in score | Deterministic tiebreak: severity, then volume, then name |
| SEL-2 | M | A top theme has no `quote_eligible` reviews | Relax the length rule within bounds. If still none, take the next-ranked theme, or abort if fewer than 3 usable themes remain |
| SEL-3 | M | All three best quotes come from the same theme or have the same rating | Prefer one quote per top theme and a mix of ratings, where the data allows |
| SEL-4 | H | A quote is trimmed so that its meaning flips ("not working" cut to "working") | Trims only at sentence or clause boundaries. Never remove negations; a test asserts the trimmed span stays a contiguous substring |
| SEL-5 | M | Two selected quotes are near-duplicates of each other | Dedupe quotes across the three picks |
| SEL-6 | M | The quote contains profanity or abuse | Excluded from quote candidates (configurable word filter). Still counted for theming |
| SEL-7 | M | The quote includes a competitor's name or a legal or financial claim ("Groww stole my money") | Allowed only if verbatim, but flagged for human review in the draft context. Open question whether to exclude |
| SEL-8 | L | Theme share rounds to totals that do not add to 100 | Percentages shown for the top 3 only, rounded individually; never claimed to sum to 100 |
| SEL-9 | M | A quote relevant to the theme but from a review that spans two sentences | Select the sentence span that carries the theme, verbatim |

## 6. Composition

| ID | Sev | Scenario | Expected behavior |
|---|---|---|---|
| CMP-1 | H | The note exceeds 250 words | Validate fails; retry compose with the word count in the error; abort after 2 retries |
| CMP-2 | H | The LLM rewrites, "cleans up" or paraphrases a quote | Quotes are injected as fixed strings; validate checks exact substring. A mismatch fails the gate |
| CMP-3 | H | The LLM invents a quote, statistic or trend | Statistics (counts, shares, average rating) are computed in code and injected. Validate rejects any quote not in the corpus |
| CMP-4 | M | Actions are generic ("improve the app") | Validate requires each action to name a listed theme. Prompt requires a concrete next step |
| CMP-5 | M | Fewer or more than 3 actions or quotes | Validate fails; retry |
| CMP-6 | M | Quotes themselves push the note over 250 words | Selection prefers shorter spans. If still over, trim the summaries first, never the quotes |
| CMP-7 | L | Word counting differs between code and the spec (hyphens, bullets, symbols) | A single shared counter is used everywhere, with a documented rule |
| CMP-8 | L | The week label spans a year boundary (week 1 and week 52/53) | ISO week used consistently; labelled with an explicit date range |
| CMP-9 | M | Markdown characters in a quote break the formatting (`*`, `_`, `#`) | Escaped at render time without altering the stored quote |
| CMP-10 | L | The note is accurate but sounds alarming or overstated | The prompt requires neutral wording and counts attributed to the sample, not "all users" |

## 7. Validation Gate

| ID | Sev | Scenario | Expected behavior |
|---|---|---|---|
| VAL-1 | H | Any check fails after the retry limit | Exit non-zero with the validation exit code, write `validation.json`, make no MCP calls |
| VAL-2 | M | The validator itself has a bug and passes everything | Each rule has a test that fails when the rule is broken (Phase 5) |
| VAL-3 | M | A fix for one rule breaks another on retry (shortening drops a required section) | All rules re-run on every attempt, not only the failed one |
| VAL-4 | M | The text validated differs from the text sent to MCP (post-processing, escaping) | Validate runs on the exact payload handed to the gateway |
| VAL-5 | L | A required section is present but empty or out of order | Structure check covers presence, order and non-empty content |

## 8. MCP Publishing

| ID | Sev | Scenario | Expected behavior |
|---|---|---|---|
| MCP-1 | M | The MCP server is not running, the endpoint is unreachable, or startup hangs | Timeout, clear error, publish exit code. Nothing partially created |
| MCP-2 | M | The expected tool is missing, or its name or schema differs from the adapter | Fail fast at startup by listing tools, before any content is created |
| MCP-3 | M | The MCP server's Google authorization expired or was revoked | Surface the server's auth error and tell the user to re-authorize the server. The pipeline never handles tokens |
| MCP-4 | M | Docs succeeds, Gmail fails | `publish_result.json` records the doc URL. A re-run resumes at the draft step without creating a second doc |
| MCP-5 | M | Docs call fails | Abort before Gmail, so no draft points at a missing doc |
| MCP-6 | M | The re-run for the same week after a successful publish | Idempotent: skip or update. `--force` overrides |
| MCP-7 | M | A crash between the MCP call returning and `publish_result.json` being written | Can cause a duplicate on re-run. Mitigate by writing a "pending" marker before the call and checking for the doc by title on resume |
| MCP-8 | M | The doc title collides with an existing doc | Title includes the ISO week. The lookup is by stored id, not by title alone |
| MCP-9 | L | The Doc renders Markdown literally (raw `##`, `**`) | Use a format the server supports. Fall back to plain headings and bullets |
| MCP-10 | M | The draft body is too long or contains characters the Gmail server mishandles | The note is short by design. Non-ASCII (₹, smart quotes) tested in the live smoke test |
| MCP-11 | H | The MCP call would send the email rather than create a draft | The adapter only maps to draft-creating tools. A test asserts that no send tool is ever called |
| MCP-12 | M | The recipient is empty or malformed | Config validation fails at startup, not at publish |
| MCP-13 | M | The user has multiple Google accounts and the MCP server is bound to a different one | Print the authorized account's identity (if the server exposes it) before creating anything on a live run |
| MCP-14 | H | An MCP tool response contains instructions or unexpected content | Treated as data. The pipeline reads only the fields it needs (URL, id) |
| MCP-15 | L | `--dry-run` is combined with `--force` | Dry run wins; no MCP calls |

## 9. Configuration and Environment

| ID | Sev | Scenario | Expected behavior |
|---|---|---|---|
| CFG-1 | M | `window_weeks` outside 8–12, zero or negative | Config validation error at startup |
| CFG-2 | M | `themes.max` set above 5 | Rejected. The problem statement caps themes at 5 |
| CFG-3 | M | `note.max_words` raised above 250 | Rejected or warned, because 250 is a stated constraint |
| CFG-4 | M | The LLM API key is missing or invalid | Fail at startup before the fetch, with a clear message (no key echoed) |
| CFG-5 | H | Secrets placed in `pulse.yaml` | Config loader rejects known secret-shaped keys. `.env` and `data/` are gitignored |
| CFG-6 | L | Missing optional config keys | Documented defaults apply |
| CFG-7 | L | The run executes in a different timezone or locale | Dates computed in IST regardless of host timezone |
| CFG-8 | M | The disk is full or `data/` is not writable | Fail at startup with a clear error rather than mid-run |

## 10. Scheduling and Operations

| ID | Sev | Scenario | Expected behavior |
|---|---|---|---|
| OPS-1 | M | The scheduler fires twice (overlapping runs) | A lock file or run-level lock; the second run exits cleanly |
| OPS-2 | M | The run is missed for a week (machine off) | A later run covers the current window. It does not backfill by default; a `--week` flag allows a manual backfill |
| OPS-3 | M | The scheduled run fails silently | Distinct exit codes per failure class drive alerts |
| OPS-4 | L | A manual re-run mid-week | Run id is by ISO week, so it updates or skips rather than duplicating |
| OPS-5 | M | The app is renamed, or the package id changes | Config change only. Documented in the README |
| OPS-6 | M | The LLM model is deprecated or its output style changes | The model id is config. Golden-file tests on a stubbed LLM catch rule regressions. A manual smoke test follows any model change |
| OPS-7 | L | An LLM cost spike from a large corpus | Review count capped per run and batch sizes bounded; token usage logged |

## 11. Data Quality and Interpretation

| ID | Sev | Scenario | Expected behavior |
|---|---|---|---|
| DQ-1 | M | A release or an outage causes a one-week review spike dominated by a single issue | Reported as the top theme; the pulse does not suppress it. A trend view is a later extension |
| DQ-2 | M | Review bombing or a coordinated campaign skews sentiment | Duplicate collapse reduces it. A known limitation otherwise; the footer states the sample size |
| DQ-3 | L | Reviews referencing a competitor or unrelated product | Themed as `other` |
| DQ-4 | M | Reviews about the developer's reply or about the store, not the app | Themed as `other` |
| DQ-5 | L | The window includes a store-wide outage unrelated to the app | Left as-is. Not detectable from review text alone |
| DQ-6 | M | Small samples cause a misleading percentage | The pulse shows the sample size next to shares, and warns below a threshold |

## 12. Priority Test Matrix

Cases to cover in automated tests before the first live run (the hard-constraint set):

| Constraint | Cases |
|---|---|
| No PII anywhere | PII-1 to PII-7, PII-11, PII-12, PII-13 |
| Verbatim quotes | CMP-2, CMP-3, SEL-4, NRM-8 |
| 250-word limit | CMP-1, CMP-6, CMP-7 |
| At most 5 themes, top 3 shown | THM-1, THM-2, SEL-2 |
| Exactly 3 quotes and 3 actions | CMP-5, VAL-3 |
| MCP-only, draft-only | MCP-2, MCP-11, MCP-15 |
| Safe to re-run | MCP-4, MCP-6, MCP-7, OPS-1 |

## 13. Known Limitations (accepted for v1)

- Name redaction has imperfect recall; the final gate and quote selection reduce, but cannot remove, that risk.
- Obfuscated PII (spelled-out digits, "at/dot" forms) is only partly handled (PII-9).
- Near-duplicate spam is only partly collapsed (NRM-4).
- Sarcasm and rating mismatch are not corrected for (THM-11).
- No week-over-week trend comparison (THM-9, DQ-1).
- The Play Store is the only source. Apple App Store reviews are out of scope for now.
