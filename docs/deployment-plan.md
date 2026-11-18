# Deployment Plan: Vercel (dashboard) + GitHub Actions (weekly pipeline)

Sources: [architecture.md](architecture.md) · [implementation-plan.md](implementation-plan.md) · [../frontend/README.md](../frontend/README.md)

The dashboard stays a static site and the pipeline stays a batch job; there is no API. A scheduled GitHub Actions workflow runs the pipeline once a week, exports `dashboard.json`, builds the frontend and pushes the build to Vercel. Run history lives in a separate private `pulse-data` repo. Review data never goes into this repo.

```
GitHub Actions cron (Mon 09:00 IST)  ·  .github/workflows/weekly.yml
  ├─ checkout this repo, and pulse-data into data/   (run history: themes.json, publish_result.json, ...)
  ├─ scripts/weekly.sh
  │    1. pulse run --week <last week>   ──MCP──►  Google Doc + email   (skipped if already published)
  │    2. pulse dashboard --week <last week>  →  frontend/public/dashboard.json
  │    3. npm run build                       →  frontend/dist
  │    4. vercel deploy dist --prod      ──────►  Vercel (static, behind Vercel Authentication)
  └─ commit data/ back to pulse-data   (always, even when a step failed)
```

**Change of plan (2026-11-18).** The first plan ran the job on Railway. Railway refused to create the project ("Free plan resource provision limit exceeded"), and Streamlit Community Cloud was ruled out: it hosts web apps only, with no scheduler, no endpoints other services can call, and a disk that is wiped on restart. GitHub Actions replaces Railway: the repo is already there, the private-repo free tier covers a weekly run of a few minutes, and no Docker image is needed.

Items marked **verify** need a quick test.

## Phase Overview

| Phase | Name | Outcome |
|---|---|---|
| 0 | Decisions and prerequisites | Plans, run time and repos settled |
| 1 | Repo changes | Workflow committed, Railway files removed |
| 2 | Vercel project | Protected project, deploy token (done) |
| 3 | Data repo and secrets | `pulse-data` seeded, secrets set |
| 4 | First runs | Deploy path proven on W45, then a real W46 run |
| 5 | Operations | Runbook for failures, re-runs and frontend-only changes |

---

## Phase 0: Decisions and Prerequisites

1. **Vercel plan.** On Hobby, *All Deployments* protection with Vercel Authentication is free, but a Hobby account has no team members, so only you can open the dashboard. Hobby is also for non-commercial use. If managers or PMs need access, or this is company work, use **Pro** ($20 per seat per month).
2. **GitHub Actions minutes.** Private repos on the Free plan get 2,000 Linux minutes a month. A weekly run of under 10 minutes uses about 40.
3. **Run time.** Monday 09:00 IST = `30 3 * * 1` (Actions cron is UTC). The run covers the **previous** ISO week. Scheduled runs can start late when GitHub is busy, which is fine for a weekly job; `:30` avoids the top-of-hour rush.
4. **Repos.** Code: `raviiitb0606-pm/groww-review-pulse` (private, pushed 2026-11-18). Run history: a new private `raviiitb0606-pm/pulse-data` repo. Keeping data in a separate repo means review text never enters the code repo's history.

**Exit check**: plans chosen, both repos exist.

---

## Phase 1: Repo Changes

Already in the repo and unchanged: [scripts/weekly.sh](../scripts/weekly.sh), [scripts/published.py](../scripts/published.py), [frontend/public/vercel.json](../frontend/public/vercel.json), and the `PULSE_MCP_COMMAND` override in `load_config` (set to `""` to use the hosted `mcp.url` with `MCP_AUTH_TOKEN`).

1. **`.github/workflows/weekly.yml`**:

   ```yaml
   name: weekly-pulse
   on:
     schedule:
       - cron: "30 3 * * 1"   # Mon 09:00 IST
     workflow_dispatch:
       inputs:
         week: { description: "Run id, e.g. 2026-W46 (blank = last week)", required: false }
         from: { description: "First stage, e.g. publish (blank = full run)", required: false }

   concurrency: { group: weekly-pulse, cancel-in-progress: false }
   permissions: { contents: read }

   jobs:
     weekly:
       runs-on: ubuntu-latest
       timeout-minutes: 30
       env:
         PULSE_WEEK: ${{ inputs.week }}
         PULSE_FROM: ${{ inputs.from }}
         PULSE_MCP_COMMAND: ""
         GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
         MCP_AUTH_TOKEN: ${{ secrets.MCP_AUTH_TOKEN }}
         VERCEL_TOKEN: ${{ secrets.VERCEL_TOKEN }}
         VERCEL_ORG_ID: ${{ secrets.VERCEL_ORG_ID }}
         VERCEL_PROJECT_ID: ${{ secrets.VERCEL_PROJECT_ID }}
       steps:
         - uses: actions/checkout@v4
         - uses: actions/checkout@v4
           with:
             repository: raviiitb0606-pm/pulse-data
             path: data
             ssh-key: ${{ secrets.PULSE_DATA_DEPLOY_KEY }}
         - uses: astral-sh/setup-uv@v6
           with: { version: "0.13.5" }
         - run: uv sync --frozen --no-dev && echo "$PWD/.venv/bin" >> "$GITHUB_PATH"
         - uses: actions/setup-node@v4
           with: { node-version: 24, cache: npm, cache-dependency-path: frontend/package-lock.json }
         - run: npm ci --prefix frontend && npm install -g vercel@65.16.0
         - run: sh scripts/weekly.sh
         - name: Save run history
           if: always()
           working-directory: data
           run: |
             git config user.name "pulse-bot"
             git config user.email "pulse-bot@users.noreply.github.com"
             git add -A
             git diff --cached --quiet || git commit -m "run ${PULSE_WEEK:-scheduled} $(date -u +%FT%TZ)"
             git push
   ```

   Notes:
   - `pipeline.DATA_DIR` is `<repo root>/data` (editable install), so checking `pulse-data` out at `data/` puts the history where the pipeline expects it.
   - On a scheduled run the inputs are empty. `weekly.sh` uses `${PULSE_WEEK:-...}` and `${PULSE_FROM:+...}`, so empty means "last week, full run".
   - **Save run history runs even when the pipeline fails.** If the Doc was appended and the email then failed, `publish_result.json` must still be saved, or the next run would publish the Doc again.
   - `VERCEL_ORG_ID` and `VERCEL_PROJECT_ID` must be set. Without them `vercel deploy dist` creates a new, unprotected project named `dist` (seen on 2026-11-18).
   - `concurrency` queues a second run instead of overlapping it.
   - The deploy key gives write access to `pulse-data` only; the workflow's own token stays read-only.
2. **Remove the Railway files**: [Dockerfile](../Dockerfile) and [.dockerignore](../.dockerignore). Update the header comment of `weekly.sh` ("Railway cron entry point" → "GitHub Actions entry point").
3. **`data/.gitkeep`**: remove it and make `data/` fully ignored. `data/` is now a checkout of `pulse-data`, not a folder of this repo.

**Exit check**: the workflow is on `main` and shows under the Actions tab. Scheduled workflows only run from the default branch.

---

## Phase 2: Vercel Project (done 2026-11-18)

1. Created with the CLI from `frontend/` (`vercel link`). The GitHub repo is **not** connected: a git-triggered build would ship without `dashboard.json`, because the file is gitignored. Every deploy comes from the workflow.
2. Framework *Other*, no build command. The deploy uploads the already-built `dist/`.
3. **Deployment Protection → Vercel Authentication → All Deployments** is on. *Standard Protection* leaves the production domain open, so it is not enough for review text.

Project `groww-review-pulse` (Hobby), production URL https://groww-review-pulse-five.vercel.app. `VERCEL_ORG_ID` = `team_t1ERqsvyiHySfsr5ghYs47ai`, `VERCEL_PROJECT_ID` = `prj_Di5j9eZpHpaEYwefd8KuPROZJ3hN` (also in `frontend/.vercel/project.json`).

**Still to do**: create a token (Account Settings → Tokens), scoped to the `raviiitb0606` team, with an expiry. It becomes the `VERCEL_TOKEN` secret.

---

## Phase 3: Data Repo and Secrets

1. **Create `pulse-data`** (private, empty).
2. **Seed it** with `data/2026-W44/` and `data/2026-W45/` from this machine. Both weeks are fully published (Doc and email `done`). Seeding them stops a run from publishing them again, and W46 reuses W45's theme names.

   ```sh
   cd data && git init -b main && git add 2026-W44 2026-W45 && git commit -m "Seed W44, W45"
   git remote add origin git@github.com:raviiitb0606-pm/pulse-data.git && git push -u origin main
   ```

3. **Deploy key**: `ssh-keygen -t ed25519 -N "" -f pulse-data-key`. Add the public key to `pulse-data` → Settings → Deploy keys with **write access**. Add the private key to this repo as the secret `PULSE_DATA_DEPLOY_KEY`, then delete both key files.
4. **Secrets** (this repo → Settings → Secrets and variables → Actions): `GROQ_API_KEY`, `MCP_AUTH_TOKEN`, `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`, `PULSE_DATA_DEPLOY_KEY`. `load_dotenv()` is a no-op without a `.env`, so the pipeline reads these from the environment as-is.

**Exit check**: `pulse-data` holds W44 and W45, and all six secrets are listed.

---

## Phase 4: First Runs

1. **Deploy path only**: Actions → weekly-pulse → *Run workflow* with `week = 2026-W45`. W45 is already published, so the pipeline is skipped and nothing is sent. Check that the dashboard shows W45 and that the run pushed nothing new to `pulse-data` (or only the refreshed export).
2. **Real run**: *Run workflow* with `week` blank. On 2026-11-18 that covers **W46**, which has not been run yet. This appends to the Google Doc and **sends the email** to `email.to`. Set `email.send: false` in `config/pulse.yaml` first if you want the first Actions run to publish the Doc only.
3. After that, the schedule takes over: the run on Monday 2026-11-23 covers W47.

**Exit check**: the dashboard shows W46, the Doc has the new section, the email arrived once, and `data/2026-W46/` is in `pulse-data`.

---

## Phase 5: Operations

| Situation | What to do |
|---|---|
| Run failed before publish (exit 2–7) | Fix the cause, then *Run workflow* with the week. No `publish_result.json` exists yet, so a full re-run is safe |
| Doc done, email failed (exit 8) | Do **not** re-run from ingest (new pulse → `REPUBLISH`). *Run workflow* with `week = <w>` and `from = publish` |
| `STATUS_UNKNOWN` on a step | Check the Doc or inbox by hand, then remove that step from `publish_result.json` in `pulse-data` as the error says, and commit |
| Frontend code changed | Push to `main`, then *Run workflow* with the latest published week. Only export, build and deploy run |
| Dashboard looks stale | Check the last run under Actions. A failed pipeline leaves the previous week's deploy live, as intended |
| Run overlaps another | `concurrency` queues the second run until the first finishes |

**Alerting**: GitHub emails the person who last changed the workflow's `cron` line when a scheduled run fails (**verify** on the first failure). Run logs are visible to anyone with access to this repo, so keep it private.

## Risks

- **Run history is in git.** A failed push in *Save run history* loses that run's `publish_result.json`. The step fails loudly; check `pulse-data` after any red run before re-running.
- **Vercel access**: Hobby means a single viewer, you. Sharing with the team needs Pro.
- **Token sprawl**: this repo's secrets hold the Groq, MCP and Vercel tokens and the data deploy key. Give the Vercel token an expiry and scope it to the one team.
- **Inactive schedules**: GitHub disables scheduled workflows after 60 days without repo activity on public repos. This repo is private, so it should not apply (**verify** if the repo is ever made public).
