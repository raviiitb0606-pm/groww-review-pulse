from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from pulse.config import Llm as LlmConfig
from pulse.llm import ClaudeLlm, GroqLlm, LlmError, new_llm


class Out(BaseModel):
    n: int


class FakeMessages:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.requests = []

    def parse(self, **kwargs):
        self.requests.append(kwargs)
        stop, parsed = self.outputs.pop(0)
        return SimpleNamespace(
            stop_reason=stop,
            parsed_output=parsed,
            content=[],
            usage=SimpleNamespace(input_tokens=10, output_tokens=2),
        )


def client(outputs):
    messages = FakeMessages(outputs)
    return SimpleNamespace(beta=SimpleNamespace(messages=messages)), messages


def test_validator_error_fed_back_then_success():
    c, msgs = client([("end_turn", Out(n=1)), ("end_turn", Out(n=2))])
    llm = ClaudeLlm(LlmConfig(model="m"), c)
    out = llm.structured(
        system="s",
        prompt="p",
        schema=Out,
        effort="low",
        validate=lambda o: [] if o.n == 2 else ["n must be 2"],
    )
    assert out.n == 2
    second = msgs.requests[1]
    assert "n must be 2" in second["messages"][-1]["content"]
    assert "temperature" not in second and second["output_format"] is Out
    assert llm.usage.calls == 2 and llm.usage.retries == 1


def test_gives_up_after_retries_and_keeps_last():
    c, _ = client([("end_turn", Out(n=1))] * 3)
    llm = ClaudeLlm(LlmConfig(model="m", max_retries=2), c)
    with pytest.raises(LlmError) as exc:
        llm.structured(
            system="s", prompt="p", schema=Out, effort="low", validate=lambda o: ["always bad"]
        )
    assert exc.value.last == Out(n=1)


def test_refusal_aborts_without_retry():
    c, msgs = client([("refusal", None)])
    with pytest.raises(LlmError, match="declined"):
        ClaudeLlm(LlmConfig(model="m"), c).structured(
            system="s", prompt="p", schema=Out, effort="low"
        )
    assert len(msgs.requests) == 1


def test_truncated_output_retried():
    c, _ = client([("max_tokens", None), ("end_turn", Out(n=3))])
    out = ClaudeLlm(LlmConfig(model="m"), c).structured(
        system="s", prompt="p", schema=Out, effort="low"
    )
    assert out.n == 3


def test_missing_credentials_fail_fast(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    with pytest.raises(LlmError, match="ANTHROPIC_API_KEY"):
        ClaudeLlm(LlmConfig(model="m"))


# --- Groq ------------------------------------------------------------------------------


class FakeCompletions:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        finish, content = self.outputs.pop(0)
        message = SimpleNamespace(content=content)
        return SimpleNamespace(
            choices=[SimpleNamespace(finish_reason=finish, message=message)],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=2),
        )


def groq_client(outputs):
    completions = FakeCompletions(outputs)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions)), completions


def groq_cfg(**kw):
    return LlmConfig(provider="groq", model="openai/gpt-oss-120b", **kw)


def test_groq_sends_the_schema_and_feeds_errors_back():
    c, calls = groq_client([("stop", '{"n": 1}'), ("stop", '{"n": 2}')])
    llm = GroqLlm(groq_cfg(), c)
    out = llm.structured(
        system="s",
        prompt="p",
        schema=Out,
        effort="low",
        validate=lambda o: [] if o.n == 2 else ["n must be 2"],
    )
    assert out.n == 2
    first, second = calls.requests
    assert first["messages"][0] == {"role": "system", "content": "s"}
    assert first["response_format"]["json_schema"]["schema"] == Out.model_json_schema()
    assert first["reasoning_effort"] == "low"
    assert second["messages"][-2] == {"role": "assistant", "content": '{"n": 1}'}
    assert "n must be 2" in second["messages"][-1]["content"]
    assert llm.usage.calls == 2 and llm.usage.retries == 1 and llm.usage.input_tokens == 20


def test_groq_retries_bad_json_and_truncation_then_gives_up():
    c, calls = groq_client([("stop", "not json"), ("length", '{"n"'), ("stop", '{"m": 1}')])
    with pytest.raises(LlmError, match="invalid after retries"):
        GroqLlm(groq_cfg(max_retries=2), c).structured(
            system="s", prompt="p", schema=Out, effort="low"
        )
    assert len(calls.requests) == 3


def test_groq_sends_no_reasoning_effort_to_other_models():
    c, calls = groq_client([("stop", '{"n": 1}')])
    cfg = LlmConfig(provider="groq", model="llama-3.3-70b-versatile")
    GroqLlm(cfg, c).structured(system="s", prompt="p", schema=Out, effort="low")
    assert "reasoning_effort" not in calls.requests[0]


def test_groq_missing_key_fails_fast(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(LlmError, match="GROQ_API_KEY"):
        new_llm(groq_cfg())


def test_factory_picks_the_configured_provider(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert isinstance(new_llm(groq_cfg()), GroqLlm)
    assert isinstance(new_llm(LlmConfig(model="claude-sonnet-5-5")), ClaudeLlm)
