"""Phase 6: publishing through MCP, against an in-process fake server that records calls."""

import asyncio
import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult, TextContent

from pulse import cli, mcp_gateway, pipeline
from pulse.config import Doc, Email, Mcp
from pulse.mcp_gateway import McpGateway, PublishError
from tests.test_validate import CFG, LEAKY, RUN, pulse, seed_run

DOC_ID = "1AbCdoc"
LIVE = CFG.model_copy(update={"doc": Doc(document_id=DOC_ID)})


def reply(payload: dict | str, error: bool = False) -> CallToolResult:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return CallToolResult(content=[TextContent(type="text", text=text)], is_error=error)


class FakeWorkspace:
    """The two tools of basic-google-workspace-mcp, recording every call made to them."""

    def __init__(
        self, fail: dict[str, str] | None = None, tools=("append_google_doc", "send_gmail")
    ):
        self.calls: list[tuple[str, dict]] = []
        self.fail = fail or {}
        self.server = MCPServer("fake-workspace")
        handlers = {"append_google_doc": self.append_google_doc, "send_gmail": self.send_gmail}
        for name in tools:
            self.server.tool(name=name)(handlers[name])

    def _result(self, name: str, args: dict, ok: dict) -> CallToolResult:
        self.calls.append((name, args))
        return reply(self.fail[name], error=True) if name in self.fail else reply(ok)

    def append_google_doc(self, documentId: str, text: str) -> CallToolResult:
        url = f"https://docs.google.com/document/d/{documentId}/edit"
        return self._result(
            "append_google_doc",
            {"documentId": documentId, "text": text},
            {"success": True, "documentId": documentId, "documentUrl": url},
        )

    def send_gmail(self, to: str, subject: str, body: str) -> CallToolResult:
        return self._result(
            "send_gmail",
            {"to": to, "subject": subject, "body": body},
            {"success": True, "messageId": "18c-msg", "threadId": "18c-thr"},
        )

    def connect(self, cfg: Mcp):
        @asynccontextmanager
        async def session():
            async with Client(self.server) as client:
                yield McpGateway(client, cfg.tools)

        return session()

    def names(self) -> list[str]:
        return [name for name, _ in self.calls]


def no_mcp(cfg):
    raise AssertionError("no MCP call expected")


def validated_run(tmp_path, text=None):
    rdir = seed_run(tmp_path, text or pulse())
    pipeline.stage_validate(CFG, RUN, tmp_path)
    return rdir


def result_of(rdir) -> dict:
    return json.loads((rdir / pipeline.PUBLISH_FILE).read_text())


def test_doc_is_appended_before_the_email_with_the_pulse_and_link(tmp_path):
    rdir = validated_run(tmp_path)
    fake = FakeWorkspace()
    pipeline.stage_publish(LIVE, RUN, tmp_path, fake.connect)

    assert fake.names() == ["append_google_doc", "send_gmail"]
    (_, doc), (_, mail) = fake.calls
    text = pipeline.plain_text((rdir / "pulse.md").read_text())
    assert doc == {"documentId": DOC_ID, "text": "\n\n" + text}
    assert "#" not in doc["text"] and "Top themes" in doc["text"]
    assert mail["to"] == CFG.email.to
    assert mail["subject"] == text.splitlines()[0] and mail["subject"].startswith("Groww Weekly")
    assert mail["body"].startswith(text.rstrip())
    assert mail["body"].rstrip().endswith(f"https://docs.google.com/document/d/{DOC_ID}/edit")

    result = result_of(rdir)
    assert result["doc"]["status"] == result["email"]["status"] == pipeline.DONE
    assert result["email"]["message_id"] == "18c-msg"
    assert (
        result["pulse_sha256"] == json.loads((rdir / "validation.json").read_text())["pulse_sha256"]
    )


def test_dry_run_makes_no_mcp_calls(tmp_path, monkeypatch, capsys):
    validated_run(tmp_path)
    monkeypatch.setattr(pipeline, "DATA_DIR", tmp_path)
    monkeypatch.setattr(mcp_gateway, "connect", no_mcp)
    assert cli.main(["run", "--dry-run", "--week", RUN, "--from", "validate"]) == 0
    assert not (tmp_path / RUN / pipeline.PUBLISH_FILE).exists()


def test_run_publishes_and_prints_the_doc_link(tmp_path, monkeypatch, capsys):
    validated_run(tmp_path)
    fake = FakeWorkspace()
    monkeypatch.setattr(pipeline, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cli, "load_config", lambda *a: LIVE)
    monkeypatch.setattr(mcp_gateway, "connect", fake.connect)
    assert cli.main(["run", "--week", RUN, "--from", "publish"]) == 0
    out = capsys.readouterr().out
    assert f"/d/{DOC_ID}/edit" in out and "email: sent to" in out
    assert fake.names() == ["append_google_doc", "send_gmail"]


def test_unvalidated_or_edited_pulse_is_never_published(tmp_path):
    rdir = seed_run(tmp_path, pulse())
    with pytest.raises(PublishError, match="NOT_VALIDATED"):
        pipeline.stage_publish(LIVE, RUN, tmp_path, no_mcp)
    pipeline.stage_validate(CFG, RUN, tmp_path)
    (rdir / "pulse.md").write_text(pulse() + "\nAn extra line nobody checked.\n")
    with pytest.raises(PublishError, match="NOT_VALIDATED"):
        pipeline.stage_publish(LIVE, RUN, tmp_path, no_mcp)
    assert not (rdir / pipeline.PUBLISH_FILE).exists()


def test_failed_gate_is_never_published(tmp_path):
    seed_run(tmp_path, pulse(LEAKY))
    with pytest.raises(pipeline.ValidateError):
        pipeline.stage_validate(CFG, RUN, tmp_path, llm=_LeakyWriter())
    with pytest.raises(PublishError, match="NOT_VALIDATED"):
        pipeline.stage_publish(LIVE, RUN, tmp_path, no_mcp)


class _LeakyWriter:
    def structured(self, *, schema, **kw):
        return schema.model_validate({"themes": [c.model_dump() for c in LEAKY]})


def test_missing_document_id_fails_before_connecting(tmp_path):
    validated_run(tmp_path)
    with pytest.raises(PublishError, match="NO_DOCUMENT"):
        pipeline.stage_publish(
            CFG.model_copy(update={"doc": Doc(document_id="")}), RUN, tmp_path, no_mcp
        )


def test_missing_tool_fails_fast_before_any_write(tmp_path):
    validated_run(tmp_path)
    fake = FakeWorkspace(tools=("append_google_doc",))
    with pytest.raises(PublishError, match=r"TOOLS_MISSING.*send_gmail"):
        pipeline.stage_publish(LIVE, RUN, tmp_path, fake.connect)
    assert fake.calls == []


def test_send_disabled_appends_the_doc_only(tmp_path):
    rdir = validated_run(tmp_path)
    fake = FakeWorkspace(tools=("append_google_doc",))  # the mail tool is not even needed
    cfg = LIVE.model_copy(update={"email": Email(to=CFG.email.to, send=False)})
    pipeline.stage_publish(cfg, RUN, tmp_path, fake.connect)
    assert fake.names() == ["append_google_doc"]
    assert result_of(rdir)["email"]["status"] == pipeline.SKIPPED


def test_doc_failure_aborts_before_gmail(tmp_path, monkeypatch, capsys):
    rdir = validated_run(tmp_path)
    fake = FakeWorkspace(fail={"append_google_doc": "DOC_NOT_FOUND: no such document"})
    monkeypatch.setattr(pipeline, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cli, "load_config", lambda *a: LIVE)
    monkeypatch.setattr(mcp_gateway, "connect", fake.connect)
    assert cli.main(["run-stage", "publish", "--week", RUN]) == cli.EXIT_PUBLISH
    assert "DOC_NOT_FOUND" in capsys.readouterr().err
    assert fake.names() == ["append_google_doc"]
    assert "doc" not in result_of(rdir)


def test_gmail_failure_keeps_the_doc_and_a_rerun_sends_only_the_email(tmp_path):
    rdir = validated_run(tmp_path)
    broken = FakeWorkspace(fail={"send_gmail": "AUTH_REQUIRED: sign-in expired"})
    with pytest.raises(PublishError, match="AUTH_REQUIRED"):
        pipeline.stage_publish(LIVE, RUN, tmp_path, broken.connect)
    result = result_of(rdir)
    assert result["doc"]["status"] == pipeline.DONE and "email" not in result

    fixed = FakeWorkspace()
    pipeline.stage_publish(LIVE, RUN, tmp_path, fixed.connect)
    assert fixed.names() == ["send_gmail"]
    assert result_of(rdir)["email"]["status"] == pipeline.DONE


def test_unknown_send_status_is_recorded_and_never_retried(tmp_path):
    rdir = validated_run(tmp_path)
    fake = FakeWorkspace(fail={"send_gmail": "SEND_STATUS_UNKNOWN: no response from Gmail"})
    with pytest.raises(PublishError, match="SEND_STATUS_UNKNOWN"):
        pipeline.stage_publish(LIVE, RUN, tmp_path, fake.connect)
    assert result_of(rdir)["email"]["status"] == pipeline.UNKNOWN
    with pytest.raises(PublishError, match="STATUS_UNKNOWN.*email"):
        pipeline.stage_publish(LIVE, RUN, tmp_path, no_mcp)


def test_rerun_after_success_makes_no_calls(tmp_path):
    validated_run(tmp_path)
    pipeline.stage_publish(LIVE, RUN, tmp_path, FakeWorkspace().connect)
    pipeline.stage_publish(LIVE, RUN, tmp_path, no_mcp)


def test_republishing_a_different_pulse_is_refused(tmp_path):
    rdir = validated_run(tmp_path)
    pipeline.stage_publish(LIVE, RUN, tmp_path, FakeWorkspace().connect)
    result = result_of(rdir) | {"pulse_sha256": "0" * 64}
    (rdir / pipeline.PUBLISH_FILE).write_text(json.dumps(result))
    with pytest.raises(PublishError, match="REPUBLISH"):
        pipeline.stage_publish(LIVE, RUN, tmp_path, no_mcp)


# --- gateway ------------------------------------------------------------------------------


def test_connect_without_a_token_fails_clearly(monkeypatch):
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)

    async def go():
        async with mcp_gateway.connect(Mcp(url="https://example.invalid/mcp")):
            pass

    with pytest.raises(PublishError, match="NO_TOKEN: MCP_AUTH_TOKEN is not set"):
        asyncio.run(go())


def test_session_failures_are_unwrapped_from_exception_groups():
    inner = PublishError("expired", "AUTH_REQUIRED")
    assert (
        mcp_gateway.as_publish_error(ExceptionGroup("g", [ExceptionGroup("h", [inner])])) is inner
    )
    err = mcp_gateway.as_publish_error(ExceptionGroup("g", [RuntimeError("Unauthorized")]))
    assert err.code == "MCP_UNAVAILABLE" and "RuntimeError: Unauthorized" in str(err)


def test_a_call_with_no_reply_counts_as_status_unknown():
    class Dropped:
        async def call_tool(self, name, arguments):
            raise TimeoutError

    gw = McpGateway(Dropped(), CFG.mcp.tools)
    with pytest.raises(PublishError) as exc:
        asyncio.run(gw.send_email("a@b.co", "s", "b"))
    assert exc.value.status_unknown


def test_stdio_command_publishes_through_a_local_server(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)  # stdio needs no bearer token
    rdir = validated_run(tmp_path)
    server = Path(__file__).parent / "fixtures" / "stdio_server.py"
    mcp = Mcp(command=f"{sys.executable} {server}", tools=CFG.mcp.tools)
    pipeline.stage_publish(LIVE.model_copy(update={"mcp": mcp}), RUN, tmp_path)
    result = result_of(rdir)
    assert result["doc"]["doc_url"].endswith(f"/d/{DOC_ID}/edit")
    assert result["email"]["message_id"].startswith("stdio-")
