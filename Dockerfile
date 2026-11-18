# Weekly pulse job for Railway: Python pipeline + Node frontend build + Vercel CLI in one image.
# Runs scripts/weekly.sh and exits; Railway's cron schedule starts it. Mount a volume at /app/data.
FROM node:24-slim AS node

FROM python:3.12-slim
COPY --from=node /usr/local/bin/node /usr/local/bin/
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv
RUN npm install -g vercel@65.16.0

WORKDIR /app
ENV UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    PULSE_MCP_COMMAND=""
# PULSE_MCP_COMMAND="" ignores config's local stdio server and uses the hosted `mcp.url`.

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY frontend/package.json frontend/package-lock.json frontend/
RUN cd frontend && npm ci

COPY . .
# Editable install (uv's default): pipeline.ROOT must resolve to /app, where data/ is mounted.
RUN uv sync --frozen --no-dev

CMD ["sh", "scripts/weekly.sh"]
