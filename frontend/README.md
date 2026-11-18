# Review Pulse dashboard

A static React app for management and product managers, built from the Stitch designs in
`../stitch_overview_dashboard_redesign/`. It reads one file, `public/dashboard.json`, which the
pipeline exports. Every KPI, chart and filter is computed in the browser from that file
(`src/lib/metrics.ts`), so the dashboard needs no backend.

## Run it

```bash
# 1. Export the data (from the project root, after the pipeline has run for the week)
uv run pulse dashboard --week 2026-W44

# 2. Start the dashboard
cd frontend
npm install
npm run dev        # http://localhost:5173
```

For a deployable build, run `npm run build` and serve `dist/` from any static host, with
`dashboard.json` next to `index.html`. The file holds scrubbed review text, so host it where only
your team can reach it.

## Pages

| Route | What it shows |
|---|---|
| `#/` Overview | Hero headline, 4 KPIs, top 3 themes this week, then trends, themes breakdown, the pulse's quotes and actions, release watch and rating breakdown |
| `#/themes/t1` Theme detail | One theme: KPIs, weekly share and negative trend, rating split, top versions, representative quotes, the pulse action, a filterable feed |
| `#/reviews` Reviews explorer | Search, rating and theme chips, week scope and sort, with a cohort summary panel |

The week picker sets which week the KPIs describe. Filters (lookback, rating, theme, app
version) apply to every page.

## Data notes

- Theme names come from the clustering model (e.g. "Update / Chart / Option"). Display labels
  and colours are set in `config/pulse.yaml` under `dashboard.themes`.
- Sentiment is taken from the rating: 1–2★ negative, 3★ neutral, 4–5★ positive.
- Quotes and actions come from the published, validated pulse. Other weeks show short,
  high-confidence reviews instead.
- Review ids are shortened, redactions show as grey `redacted` / `name` pills, and the email
  recipient is never exported.

## Checks

```bash
npm test           # metrics unit tests (Vitest)
npm run typecheck
```
