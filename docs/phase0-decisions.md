# Phase 0 Decisions

Resolves architecture.md §11. Items marked **OPEN** need the owner's input.

| # | Question | Decision |
|---|---|---|
| 1 | Play Store access | Use the `google-play-scraper` library on the public listing (no login, throttled, page cap). Console export needs owner access. **Accepted risk**: it reads the public web endpoints rather than an official export; owner should confirm this fits the "public exports only" constraint. |
| 2 | Docs and Gmail MCP servers | One server for both: `basic-google-workspace-mcp`, hosted at `https://basic-google-workspace-mcp.vercel.app/mcp` (Streamable HTTP, bearer token in `MCP_AUTH_TOKEN`). |
| 3 | Doc strategy | One standing doc (`doc.strategy: standing`, `doc.document_id`). The server can only append to an existing Doc, so each week is appended as a new section. |
| 4 | Recipient | Self (`srblr56@gmail.com`) for the first live run; switch to an alias later. |
| 5 | Language / LLM | Python 3.12, Anthropic API, `claude-sonnet-5-5`, temperature 0. |

## MCP server: tool shapes (from the server README, 2026-11-08)

`/health` returns `{"ok":true}`. `/mcp` without a token returns 401 `Unauthorized`.

| Tool | Arguments | Success payload (JSON text) |
|---|---|---|
| `append_google_doc` | `documentId`, `text` (inserted as-is before the final newline; no Markdown) | `{success, message, documentId, documentUrl}` |
| `send_gmail` | `to` (one plain address), `subject`, `body` (plain text), optional `cc`, `replyTo` | `{success, message, messageId, threadId}` |

Errors are `isError: true` with text `CODE: message`. `SEND_STATUS_UNKNOWN` and `APPEND_STATUS_UNKNOWN` mean the write may have happened, so the pipeline records them and never retries automatically.

### Deviations from architecture.md this server forces

- **No create-doc tool.** The pulse is appended to one standing Doc whose ID is in `doc.document_id`.
- **No create-draft tool.** The only mail tool *sends*. The pipeline sends only when `email.send: true`, only to `email.to` (your own address for now), and at most once per run (`publish_result.json`). Set `email.send: false` to publish the Doc only.
- **Plain text only.** Markdown heading marks are removed before publishing.

### Verify your token
`uv run python scripts/mcp_spike.py https://basic-google-workspace-mcp.vercel.app/mcp` lists the tools using `MCP_AUTH_TOKEN` from `.env`.
