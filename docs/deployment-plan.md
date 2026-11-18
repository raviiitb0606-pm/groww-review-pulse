# Deployment Plan: Vercel (dashboard) + Railway (weekly pipeline)

Sources: [architecture.md](architecture.md) · [implementation-plan.md](implementation-plan.md) · [../frontend/README.md](../frontend/README.md)

The dashboard stays a static site and the pipeline stays a batch job; there is no API. Railway runs the pipeline once a week as a cron job, exports `dashboard.json`, builds the frontend and pushes the build to Vercel. Review data never goes into git.

```
Railway cron (Mon 09:00 IST)
  └─ scripts/weekly.sh
       1. pulse run --week <last week>   ──MCP──►  Google Doc + email   (skipped if already published)
       2. pulse dashboard --week <last week>  →  frontend/public/dashboard.json
       3. npm run build                       →  frontend/dist
       4. vercel deploy dist --prod      ──────►  Vercel (static, behind Vercel Authentication)
  └─ volume mounted at /app/data (run history: themes.json, publish_result.json, ...)
```

Doc facts below were checked on 2026-11-09. Items marked **verify** were not covered by the docs and need a quick test.

## Phase Overview

| Phase | Name | Outcome |
|---|---|---|
| 0 | Decisions and prerequisites | Plan, run time and repo settled |
| 1 | Repo changes | Dockerfile, weekly script, Vercel headers committed |
| 2 | Vercel project | Empty protected project, deploy token |
| 3 | Railway service | Cron service with volume, secrets and schedule |
| 4 | First runs | Deploy path proven on W44, then a real W45 run |
| 5 | Operations | Runbook for failures, re-runs and frontend-only changes |

---

## Phase 0: Decisions and Prerequisites

1. **Vercel plan.** On Hobby, *All Deployments* protection with Vercel Authentication is free, but a Hobby account has no team members, so only you can open the dashboard. Hobby is also for non-commercial use. If managers or PMs need access, or this is company work, use **Pro** ($20 per seat per month). Password Protection is not available on Hobby and is a $20/month add-on on Pro.
2. **Railway plan.** Hobby is enough: a weekly run of a few minutes and a 5 GB volume. Check current pricing on railway.com.
3. **Run time.** Monday 09:00 IST = `30 3 * * 1` (Railway cron is UTC). The run covers the **previous** ISO week, matching how W44 was run on 2026-11-08. `--week` is passed explicitly because `pulse run` defaults to the *current* week.
4. **Repo.** This folder is not a git repo yet. Create a **private** GitHub repo; Railway builds from it. `data/`, `.env` and `frontend/public/dashboard.json` are already gitignored.

**Exit check**: plans chosen, private repo pushed.

---

## Phase 1: Repo Changes (done 2026-11-18)

Built as described below. The final versions are in the repo: [Dockerfile](../Dockerfile), [.dockerignore](../.dockerignore), [scripts/weekly.sh](../scripts/weekly.sh), [scripts/published.py](../scripts/published.py), [frontend/public/vercel.json](../frontend/public/vercel.json). One addition: `config/pulse.yaml` launches a local MCP server (`mcp.command`) that only exists on the dev machine, so `load_config` now reads a `PULSE_MCP_COMMAND` override. The image sets it to `""`, which makes the pipeline use the hosted `mcp.url` with `MCP_AUTH_TOKEN`. Local runs are unchanged.

1. **`Dockerfile`** at the root. Railway always builds from a Dockerfile when one exists. One image holds Python (pipeline), Node (frontend build) and the Vercel CLI:

   ```dockerfile
   FROM node:24-slim AS node
   FROM python:3.12-slim
   COPY --from=node /usr/local/bin/node /usr/local/bin/
   COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
   RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx
   COPY --from=ghcr.io/astral-sh/uv:<pinned-version> /uv /usr/local/bin/uv
   WORKDIR /app
   COPY pyproject.toml uv.lock ./
   RUN uv sync --frozen --no-dev --no-install-project
   COPY frontend/package.json frontend/package-lock.json frontend/
   RUN cd frontend && npm ci
   RUN npm install -g vercel@<pinned-version>
   COPY . .
   RUN uv sync --frozen --no-dev
   CMD ["sh", "scripts/weekly.sh"]
   ```

2. **`.dockerignore`**: `.env`, `data/`, `.venv/`, `**/node_modules/`, `frontend/dist/`, `frontend/public/dashboard.json`, caches. Secrets come from Railway variables, never from the image.

3. **`scripts/weekly.sh`**: the cron entry point. It must exit when done, because Railway skips the next run while one is still active.

   ```sh
   #!/bin/sh
   set -eu
   WEEK="${PULSE_WEEK:-$(uv run python -c 'from datetime import datetime, timedelta
   from pulse.models import IST, run_id_for
   print(run_id_for(datetime.now(IST).date() - timedelta(weeks=1)))')}"

   # Re-running a published week would regenerate the pulse and fail with REPUBLISH,
   # so skip the pipeline when doc and email are already done.
   if uv run python scripts/published.py "$WEEK"; then
     echo "pulse: $WEEK already published, skipping pipeline"
   else
     uv run pulse run --week "$WEEK"
   fi

   uv run pulse dashboard --week "$WEEK"
   cd frontend && npm run build
   vercel deploy dist --prod --yes --token "$VERCEL_TOKEN"
   ```

   `scripts/published.py` reads `data/<week>/publish_result.json` and exits 0 when `doc` is `done` and `email` is `done` or `skipped`. If the pipeline fails, `set -e` stops the script before the deploy, so the dashboard keeps last week's data. Railway shows the pipeline's exit code (2–9, see `cli.py`).

4. **`frontend/public/vercel.json`**: Vite copies it into `dist/`, so it ships with every deploy. Routes are hash-based (`#/themes/...`), so no rewrites are needed.

   ```json
   {
     "headers": [
       { "source": "/(.*)", "headers": [{ "key": "X-Robots-Tag", "value": "noindex, nofollow" }] },
       { "source": "/dashboard.json", "headers": [{ "key": "Cache-Control", "value": "no-store" }] }
     ]
   }
   ```

5. Do **not** add `railway.json` / `railway.toml`. Railway's config-as-code is deprecated, and legacy files stop working on 2026-12-01. Set the schedule in the dashboard instead (Phase 3).

**Exit check**: `docker build .` succeeds locally, and `docker run --env-file .env -v "$PWD/data:/app/data" -e PULSE_WEEK=2026-W44 <image>` skips the pipeline, exports, builds and deploys. Do the deploy part of this check after Phase 2.

---

## Phase 2: Vercel Project

1. Create the project with the CLI from `frontend/`: `vercel link`. Do **not** connect the GitHub repo. A git-triggered build would ship without `dashboard.json`, because the file is gitignored. Every deploy comes from Railway.
2. Project settings: Framework *Other*, no build command. The deploy uploads the already-built `dist/`.
3. **Settings → Deployment Protection → Vercel Authentication → All Deployments.** *Standard Protection* leaves the production domain open, so it is not enough for review text.
4. Create a token (Account Settings → Tokens), scoped to this team, with an expiry. Copy `orgId` and `projectId` from `frontend/.vercel/project.json`. Keep `.vercel/` out of git.

**Exit check**: `vercel deploy dist --prod` from your machine serves the dashboard, and opening the production URL in a private window asks for a Vercel login.

---

## Phase 3: Railway Service

1. New project → deploy from the GitHub repo → one service (`pulse-weekly`). Railway picks up the Dockerfile.
2. **Volume** mounted at `/app/data`, which is where `pipeline.DATA_DIR` resolves inside the image. It keeps `themes.json` (so theme names stay stable week to week) and `publish_result.json` (so an email is never sent twice). **Verify** that a volume attaches to a cron-scheduled service; the docs neither confirm nor rule it out. Fallback: commit each `data/<week>/` to a separate private `pulse-data` repo at the end of the script and clone it at the start.
3. **Variables**: `GROQ_API_KEY`, `MCP_AUTH_TOKEN`, `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`. `load_dotenv()` is a no-op without a `.env`, so the pipeline reads these from the environment as-is. `PULSE_MCP_COMMAND` is already set in the image, so don't add it. The hosted MCP server was checked with the current token on 2026-11-16: it lists `append_google_doc` and `send_gmail`.
4. **Seed the volume** with `data/2026-W44/` so W45 reuses W44's theme names. Use `railway volume files` or sftp through the service (**verify** how this works while the cron service is idle). If seeding is awkward, skip it: you lose name continuity for one week only.
5. **Settings → Cron Schedule**: `30 3 * * 1`. Restart policy: *Never*, so a failed run is not retried. A retry after a failed publish could hit the `STATUS_UNKNOWN` guard or send twice.

**Exit check**: the service shows the next scheduled run, and the variables and volume are attached.

---

## Phase 4: First Runs

1. **Deploy path only**: set `PULSE_WEEK=2026-W44` and run once (`railway cron run`, or "Run now"). W44 is already published, so the pipeline is skipped, and nothing is sent. Check that the Vercel dashboard shows W44.
2. **Real run**: remove `PULSE_WEEK` and set it to `2026-W45` for a manual run today, or wait for the 2026-11-16 run, which covers W46. This appends to the Google Doc and **sends the email** to `email.to`. Set `email.send: false` in `config/pulse.yaml` first if you want the first Railway run to publish the Doc only.
3. Remove `PULSE_WEEK` afterwards, so scheduled runs compute the week themselves.

**Exit check**: the dashboard shows the new week, the Doc has the new section, the email arrived once, and `data/<week>/` is on the volume.

---

## Phase 5: Operations

| Situation | What to do |
|---|---|
| Run failed before publish (exit 2–7) | Fix the cause, then "Run now". No `publish_result.json` exists yet, so a full re-run is safe |
| Doc done, email failed (exit 8) | Do **not** re-run from ingest (new pulse → `REPUBLISH`). Set `PULSE_WEEK=<w>` and `PULSE_FROM=publish`, "Run now" once, then remove both |
| `STATUS_UNKNOWN` on a step | Check the Doc or inbox by hand, then remove that step from `publish_result.json` on the volume as the error says |
| Frontend code changed | Push, let Railway rebuild the image, then "Run now". The week is already published, so only export, build and deploy run |
| Dashboard looks stale | Check the last cron run's logs. A failed pipeline leaves the previous week's deploy live, as intended |
| Run overlaps the next schedule | Railway skips the new run while one is active. Ingest is capped at 150 pages, so a run should take minutes |

**Alerting** (**verify** whether Railway emails on a failed cron run). Fallback: ping a dead-man's-switch URL (e.g. healthchecks.io) as the last line of `weekly.sh`, so a missing ping means the run failed or never started.

## Risks

- **Volume on a cron service** is undocumented (Phase 3.2); the git fallback is ready if it fails.
- **Vercel access**: Hobby means a single viewer, you. Sharing with the team needs Pro.
- **Token sprawl**: the Railway service holds the Groq, MCP and Vercel tokens. Give the Vercel token an expiry and scope it to the one team.
