#!/bin/sh
# Railway cron entry point: publish last week's pulse, then rebuild and deploy the dashboard.
# Env: VERCEL_TOKEN, VERCEL_ORG_ID, VERCEL_PROJECT_ID, the LLM key and MCP_AUTH_TOKEN.
# Optional: PULSE_WEEK (run id, default last ISO week in IST), PULSE_FROM (first stage, e.g.
# `publish` to retry a failed email without composing a new pulse).
set -eu
cd "$(dirname "$0")/.."

WEEK="${PULSE_WEEK:-$(python -c 'from datetime import datetime, timedelta
from pulse.models import IST, run_id_for
print(run_id_for(datetime.now(IST).date() - timedelta(weeks=1)))')}"

if python scripts/published.py "$WEEK"; then
  echo "weekly: $WEEK is already published, skipping the pipeline"
else
  pulse run --week "$WEEK" ${PULSE_FROM:+--from "$PULSE_FROM"}
fi

pulse dashboard --week "$WEEK"
cd frontend
npm run build
vercel deploy dist --prod --yes --token "$VERCEL_TOKEN"
echo "weekly: deployed the $WEEK dashboard"
