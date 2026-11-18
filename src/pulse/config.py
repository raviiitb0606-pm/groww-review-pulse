"""Typed loader for config/pulse.yaml."""

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator


class App(BaseModel):
    name: str
    play_package: str
    play_locale: str


class Ingest(BaseModel):
    page_size: int = Field(200, ge=1, le=200)
    max_pages: int = Field(150, ge=1)
    throttle_seconds: float = Field(1.0, ge=0)
    max_retries: int = Field(4, ge=0)
    stop_after_old: int = Field(50, ge=1)


class Scrub(BaseModel):
    min_words: int = Field(8, ge=0)  # keep reviews with MORE than this many words
    max_redaction_share: float = Field(0.2, ge=0, le=1)  # above this, not quote-eligible
    english_only: bool = True


class Weights(BaseModel):
    volume: float
    severity: float


class Themes(BaseModel):
    max: int = Field(5, ge=1, le=5)  # the problem statement caps themes at 5 (CFG-2)
    top_k: int = Field(3, ge=1)
    weights: Weights
    min_df: int = Field(4, ge=1)  # TF-IDF vocabulary: minimum reviews per term
    max_df: float = Field(0.4, gt=0, le=1)  # ...and maximum share of reviews per term
    split_share: float = Field(0.3, gt=0, le=1)  # bisect a topic larger than this share
    max_splits: int = Field(3, ge=0)
    high_confidence: float = Field(0.5, ge=0, le=1)  # best topic's share of a review's weight
    seed: int = 7  # NMF random state, so clustering is reproducible
    max_other_share: float = Field(0.2, ge=0, le=1)  # exit-check thresholds, reported in stats
    min_theme_share: float = Field(0.05, ge=0, le=1)


class Select(BaseModel):
    quote_chars: tuple[int, int] = (20, 200)  # verbatim span length bounds, inclusive
    relaxed_quote_chars: tuple[int, int] = (12, 240)  # SEL-2 fallback bounds
    rank_candidates: int = Field(8, ge=1)  # heuristic top-N per theme the LLM ranks
    grounding_sample: int = Field(12, ge=1)  # reviews per top theme shown to compose
    blocked_words: list[str] = []  # SEL-6: spans with these words are never quoted
    flag_words: list[str] = []  # SEL-7: competitor or legal-claim words, flagged for review


class Note(BaseModel):
    max_words: int = 250
    quotes: int = 3
    actions: int = 3
    compose_retries: int = Field(2, ge=0)  # gate failures re-run compose this many times


class Email(BaseModel):
    to: str = Field(pattern=r"^[^@\s,<>]+@[^@\s,<>]+\.[^@\s,<>]+$")  # one plain address
    send: bool = False  # the MCP server has no draft tool: true sends the pulse to `to`


class Doc(BaseModel):
    strategy: Literal["standing"] = "standing"  # the MCP server can append but not create a Doc
    document_id: str = ""  # from docs.google.com/document/d/<ID>/edit


class McpTools(BaseModel):
    """The server's real tool names, so a replacement server only changes config."""

    docs_append: str = "append_google_doc"
    gmail_send: str = "send_gmail"


class Mcp(BaseModel):
    url: str = ""  # Streamable HTTP endpoint
    command: str = ""  # stdio launch command for a local server; when set, used instead of `url`
    token_env: str = "MCP_AUTH_TOKEN"  # env var holding the bearer token; never the token itself
    timeout_seconds: float = Field(60, gt=0)
    tools: McpTools = McpTools()

    @model_validator(mode="after")
    def _one_transport(self) -> "Mcp":
        if not (self.url or self.command):
            raise ValueError("mcp needs a `url` (HTTP) or a `command` (stdio)")
        return self


class DashboardTheme(BaseModel):
    label: str
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")


class Dashboard(BaseModel):
    out: str = "frontend/public/dashboard.json"  # relative to the project root
    themes: dict[str, DashboardTheme] = {}  # display label and colour per theme name


class Llm(BaseModel):
    """No temperature: current Claude models reject non-default sampling parameters."""

    provider: Literal["anthropic", "groq"] = "anthropic"
    model: str
    max_retries: int = Field(2, ge=0)  # re-asks with the validator error fed back


class Config(BaseModel):
    app: App
    window_weeks: int = Field(12, ge=8, le=12)
    min_review_chars: int = 15
    min_reviews: int = 50
    ingest: Ingest = Ingest()
    scrub: Scrub = Scrub()
    themes: Themes
    select: Select = Select()
    note: Note
    email: Email
    doc: Doc
    mcp: Mcp
    llm: Llm
    dashboard: Dashboard = Dashboard()


DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "pulse.yaml"
MCP_COMMAND_ENV = "PULSE_MCP_COMMAND"  # overrides `mcp.command`; empty switches to the hosted `url`


def load_config(path: Path = DEFAULT_PATH) -> Config:
    raw = yaml.safe_load(path.read_text())
    if MCP_COMMAND_ENV in os.environ:  # the deploy image has no local MCP server to launch
        raw.setdefault("mcp", {})["command"] = os.environ[MCP_COMMAND_ENV]
    return Config.model_validate(raw)
