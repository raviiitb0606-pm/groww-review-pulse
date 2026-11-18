# Problem Statement: Weekly Review Pulse for Groww

## Overview

Build a pipeline for the **Groww** platform (Stocks, Mutual Funds, IPO) that turns raw mobile-store reviews into a **weekly pulse** a team can scan in minutes: what users care about, what they actually said, and what to do next.

- Play Store listing: https://play.google.com/store/apps/details?id=com.nextbillion.groww&hl=en_IN
- Reviews are already public. The job is to aggregate, theme, summarize and deliver them.
- Delivery surfaces: **Google Docs** (the written pulse) and **Gmail** (a draft email to self or an alias).

## End-to-End Flow ("done" looks like)

1. Pull recent Play Store reviews for the product (within the constraints below). Apple App Store reviews are out of scope for now.
2. Cluster them into a small set of themes and distill a one-page weekly note.
3. Put the note where stakeholders can read it (Google Docs).
4. Create a draft email to yourself (or an alias) that contains or links to the pulse (Gmail).

## Deliverables

**Weekly one-page pulse** containing:

- **Top themes**: what people are talking about most.
- **Real user quotes**: verbatim snippets from reviews, with no invented wording.
- **Three action ideas**: concrete next steps grounded in the themes.

Plus a **draft email** to self containing the note, or a clear pointer to it.

## Who This Helps

| Audience | Why |
|---|---|
| Product / Growth | Prioritize fixes and improvements from real signals |
| Support | Align messaging with what users are actually saying |
| Leadership | One-page health check without drowning in raw reviews |

## What Must Be Built

1. **Import reviews** from roughly the last 8–12 weeks (rating, title, text, date, or whatever the export provides).
2. **Group reviews into at most 5 themes** (e.g. onboarding, KYC, payments, statements, withdrawals; pick what fits the product).
3. **Generate a weekly one-page note** with:
   - Top 3 themes (a subset of the themes as appropriate)
   - 3 user quotes
   - 3 action ideas
4. **Draft an email** with the note to yourself or an alias.

## Integrations: Google Docs & Gmail via MCP

- Use **MCP (Model Context Protocol) servers** for Google Docs and Gmail, for example to create or update the pulse document and to create the draft message.
- Do **not** integrate Google APIs directly. No bespoke OAuth client or REST client code as the primary integration path.
- MCP servers expose tools that the agent or app calls. This keeps Docs and Gmail consistent with the course tooling and avoids duplicating auth and HTTP plumbing.
- Choose whichever MCP servers or connectors the environment provides. The requirement is **MCP-first**, not "call Google APIs manually."

## Key Constraints

- **Reviews**: public review exports only. No scraping behind store logins and no ToS-violating automation.
- **Themes**: maximum 5 for clustering; the written pulse highlights the top 3.
- **Length**: keep the note scannable, **≤250 words** where applicable.
- **Privacy**: no PII in any artifact (no usernames, emails, device IDs or other identifiable reviewer data). Quotes must be anonymous or stripped as needed.
