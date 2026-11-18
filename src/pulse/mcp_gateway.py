"""The pipeline's only route to Google Docs and Gmail: a thin MCP client (architecture.md §4).

The server (basic-google-workspace-mcp) exposes two tools, named in `mcp.tools`:
`append_google_doc` adds plain text to the end of an existing Doc, and `send_gmail` sends one
plain-text email. It has no create-doc or create-draft tool, so the pulse goes into one standing
Doc, and the email is sent (not drafted) only when `email.send` is true. Google credentials stay
in the server; the pipeline holds only its URL and reads the bearer token from the environment.
"""

import json
import os
import re
import shlex
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager

import httpx2
from mcp import Client, StdioServerParameters
from mcp.client.streamable_http import streamable_http_client

from pulse.config import Mcp, McpTools

ERROR_TEXT = re.compile(r"(?P<code>[A-Z][A-Z_]+): (?P<message>.*)", re.S)
# The server's codes for a call that may have taken effect without a reply (README §7).
UNKNOWN_CODES = {"SEND_STATUS_UNKNOWN", "APPEND_STATUS_UNKNOWN"}
NO_REPLY = "STATUS_UNKNOWN"


class PublishError(Exception):
    def __init__(self, message: str, code: str = "PUBLISH_FAILED"):
        super().__init__(f"{code}: {message}")
        self.code = code

    @property
    def status_unknown(self) -> bool:
        """The call may have gone through, so it must not be retried automatically."""
        return self.code in UNKNOWN_CODES or self.code == NO_REPLY


class McpGateway:
    """The two operations the pipeline needs, mapped to the server's tools."""

    def __init__(self, client: Client, tools: McpTools):
        self.client = client
        self.tools = tools

    async def check_tools(self, *names: str) -> None:
        """Fail fast, before any write, when the server lacks a tool the run will call."""
        listed = {t.name for t in (await self.client.list_tools()).tools}
        if missing := [n for n in names if n not in listed]:
            raise PublishError(
                f"server lacks tools {missing}; it lists {sorted(listed)}", "TOOLS_MISSING"
            )

    async def publish_doc(self, document_id: str, text: str) -> str:
        """Append `text` to the Doc as a new section; returns the Doc URL."""
        out = await self._call(
            self.tools.docs_append, {"documentId": document_id, "text": "\n\n" + text}
        )
        return out.get("documentUrl") or f"https://docs.google.com/document/d/{document_id}/edit"

    async def send_email(self, to: str, subject: str, body: str) -> str:
        """Send one plain-text email; returns the Gmail message id."""
        out = await self._call(self.tools.gmail_send, {"to": to, "subject": subject, "body": body})
        return str(out.get("messageId", ""))

    async def _call(self, name: str, arguments: dict) -> dict:
        try:
            result = await self.client.call_tool(name, arguments)
        except Exception as exc:  # a write may have landed without its reply
            raise PublishError(f"no reply from {name}: {type(exc).__name__}", NO_REPLY) from exc
        text = "\n".join(getattr(c, "text", "") for c in result.content)
        if result.is_error:
            m = ERROR_TEXT.match(text)
            raise PublishError(*((m["message"], m["code"]) if m else (text or "tool error",)))
        try:  # the server replies with a JSON object as text (README §7)
            payload = json.loads(text)
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            return payload
        return dict(result.structured_content or {})


def _leaves(exc: BaseException) -> Iterator[BaseException]:
    if isinstance(exc, BaseExceptionGroup):
        for sub in exc.exceptions:
            yield from _leaves(sub)
    else:
        yield exc


def as_publish_error(exc: BaseException) -> PublishError:
    """The PublishError inside a session's exception group, or one describing the failure."""
    leaves = list(_leaves(exc))
    for leaf in leaves:
        if isinstance(leaf, PublishError):
            return leaf
    detail = "; ".join(f"{type(e).__name__}: {e}" for e in leaves)
    return PublishError(f"MCP session failed ({detail})", "MCP_UNAVAILABLE")


@asynccontextmanager
async def connect(cfg: Mcp) -> AsyncIterator[McpGateway]:
    """Open a session: stdio to a local server when `mcp.command` is set, else Streamable HTTP
    authenticated with the bearer token."""
    if cfg.command:
        parts = shlex.split(cfg.command)
        params = StdioServerParameters(command=parts[0], args=parts[1:])
        async with Client(params, read_timeout_seconds=cfg.timeout_seconds) as client:
            yield McpGateway(client, cfg.tools)
        return
    token = os.environ.get(cfg.token_env, "").strip()
    if not token:
        raise PublishError(
            f"{cfg.token_env} is not set; add the server's token to .env", "NO_TOKEN"
        )
    http = httpx2.AsyncClient(
        headers={"Authorization": f"Bearer {token}"},
        timeout=httpx2.Timeout(30, read=cfg.timeout_seconds),
    )
    async with http, Client(streamable_http_client(cfg.url, http_client=http)) as client:
        yield McpGateway(client, cfg.tools)
