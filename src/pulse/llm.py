"""LLM client wrappers (Claude or Groq): structured JSON output, schema validation, bounded retry
with feedback. Only scrubbed review text is ever sent.

Reviews are untrusted data. Callers delimit them in the prompt and the system prompt says so;
the schema-validated output rejects injected output shapes (THM-12).
"""

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

import anthropic
import groq
from pydantic import BaseModel, ValidationError

from pulse.config import Llm as LlmConfig

log = logging.getLogger(__name__)

FALLBACK_BETA = "server-side-fallback-2026-07-01"

type Validator[T] = Callable[[T], list[str]]


class LlmError(Exception):
    """The model could not produce valid output within the retry budget.

    `last` holds the final parsed (schema-valid but rule-breaking) output, when there was one.
    Messages hold counts, keys and theme names only, never review text.
    """

    def __init__(self, message: str, last: BaseModel | None = None):
        super().__init__(message)
        self.last = last


class Llm(Protocol):
    def structured[T: BaseModel](
        self,
        *,
        system: str,
        prompt: str,
        schema: type[T],
        effort: str,
        validate: Validator[T] | None = None,
    ) -> T: ...


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    retries: int = 0
    by_schema: dict[str, int] = field(default_factory=dict)


class ClaudeLlm:
    def __init__(self, cfg: LlmConfig, client: anthropic.Anthropic | None = None):
        self.model = cfg.model
        self.max_retries = cfg.max_retries
        if client is None:
            client = anthropic.Anthropic()
            if client.api_key is None and client.auth_token is None:
                raise LlmError(
                    "no LLM credentials; set ANTHROPIC_API_KEY in the environment or .env"
                )
        self.client = client
        self.usage = Usage()

    def structured[T: BaseModel](
        self,
        *,
        system: str,
        prompt: str,
        schema: type[T],
        effort: str,
        validate: Validator[T] | None = None,
    ) -> T:
        messages: list = [{"role": "user", "content": prompt}]
        last: T | None = None
        errors: list[str] = []
        for attempt in range(self.max_retries + 1):
            if attempt:
                self.usage.retries += 1
            try:
                response = self.client.beta.messages.parse(
                    model=self.model,
                    max_tokens=16000,
                    system=system,
                    messages=messages,
                    output_format=schema,
                    output_config={"effort": effort},
                    betas=[FALLBACK_BETA],
                    fallbacks="default",  # re-run on another model if a classifier declines
                )
            except anthropic.AuthenticationError as exc:
                raise LlmError("LLM authentication failed; set ANTHROPIC_API_KEY") from exc
            except (anthropic.BadRequestError, anthropic.NotFoundError) as exc:
                raise LlmError(f"LLM request rejected: {exc.message}") from exc
            except ValidationError as exc:
                errors = [f"output did not match the schema: {exc.error_count()} errors"]
                messages += [
                    {"role": "assistant", "content": "(invalid output)"},
                    {"role": "user", "content": _feedback(errors)},
                ]
                continue
            self._count(response, schema)

            if response.stop_reason == "refusal":
                raise LlmError(f"{schema.__name__}: the model declined the request")
            if response.stop_reason == "max_tokens":
                errors = ["output was cut off at max_tokens; return a shorter answer"]
            elif response.parsed_output is None:
                errors = ["no JSON output was returned"]
            else:
                last = response.parsed_output
                errors = validate(last) if validate else []
                if not errors:
                    return last
            log.warning(
                "%s attempt %d rejected: %d errors", schema.__name__, attempt + 1, len(errors)
            )
            messages += [
                {"role": "assistant", "content": _replay(response.content)},
                {"role": "user", "content": _feedback(errors)},
            ]
        raise LlmError(f"{schema.__name__}: invalid after retries: {errors[:5]}", last)

    def _count(self, response, schema: type[BaseModel]) -> None:
        self.usage.calls += 1
        self.usage.input_tokens += response.usage.input_tokens
        self.usage.output_tokens += response.usage.output_tokens
        name = schema.__name__
        self.usage.by_schema[name] = self.usage.by_schema.get(name, 0) + 1


def _replay(content) -> list[dict]:
    """The assistant turn as request params; `parsed_output` is a client-side field only."""
    return [
        b.model_dump(mode="json", exclude={"parsed_output"}, exclude_none=True) for b in content
    ]


def _feedback(errors: list[str]) -> str:
    lines = "\n".join(f"- {e}" for e in errors)
    return f"Your previous output was rejected:\n{lines}\nReturn the full corrected JSON."


class GroqLlm:
    """Groq chat completions with a JSON-schema response format, under the same retry contract.

    `effort` maps to `reasoning_effort` on the gpt-oss models, the only ones that take it.
    """

    def __init__(self, cfg: LlmConfig, client: groq.Groq | None = None):
        self.model = cfg.model
        self.max_retries = cfg.max_retries
        if client is None:
            if not os.environ.get("GROQ_API_KEY"):
                raise LlmError("no LLM credentials; set GROQ_API_KEY in the environment or .env")
            client = groq.Groq(max_retries=5)  # the SDK backs off on 429s from the free tier
        self.client = client
        self.usage = Usage()

    def structured[T: BaseModel](
        self,
        *,
        system: str,
        prompt: str,
        schema: type[T],
        effort: str,
        validate: Validator[T] | None = None,
    ) -> T:
        messages: list = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
        extra = {"reasoning_effort": effort} if "gpt-oss" in self.model else {}
        response_format = {
            "type": "json_schema",
            "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema()},
        }
        last: T | None = None
        errors: list[str] = []
        for attempt in range(self.max_retries + 1):
            if attempt:
                self.usage.retries += 1
            content = ""
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    response_format=response_format,
                    max_completion_tokens=16000,
                    **extra,
                )
            except groq.AuthenticationError as exc:
                raise LlmError("LLM authentication failed; set GROQ_API_KEY") from exc
            except groq.BadRequestError as exc:
                if "json_validate_failed" not in str(exc):
                    raise LlmError(f"LLM request rejected: {exc.message}") from exc
                errors = ["output did not match the JSON schema"]
            except groq.NotFoundError as exc:
                raise LlmError(f"LLM model not found: {self.model}") from exc
            else:
                self._count(response, schema)
                choice = response.choices[0]
                content = choice.message.content or ""
                if choice.finish_reason == "length":
                    errors = ["output was cut off at max tokens; return a shorter answer"]
                else:
                    try:
                        last = schema.model_validate_json(content)
                    except ValidationError as exc:
                        errors = [f"output did not match the schema: {exc.error_count()} errors"]
                    else:
                        errors = validate(last) if validate else []
                        if not errors:
                            return last
            log.warning(
                "%s attempt %d rejected: %d errors", schema.__name__, attempt + 1, len(errors)
            )
            messages += [
                {"role": "assistant", "content": content or "(invalid output)"},
                {"role": "user", "content": _feedback(errors)},
            ]
        raise LlmError(f"{schema.__name__}: invalid after retries: {errors[:5]}", last)

    def _count(self, response, schema: type[BaseModel]) -> None:
        self.usage.calls += 1
        if response.usage:
            self.usage.input_tokens += response.usage.prompt_tokens
            self.usage.output_tokens += response.usage.completion_tokens
        name = schema.__name__
        self.usage.by_schema[name] = self.usage.by_schema.get(name, 0) + 1


def new_llm(cfg: LlmConfig) -> Llm:
    """The configured provider's client."""
    return GroqLlm(cfg) if cfg.provider == "groq" else ClaudeLlm(cfg)
