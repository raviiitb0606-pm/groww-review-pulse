"""Composition: render the one-page pulse from the selection (architecture.md §3.6).

Everything factual is computed and rendered in code: the date range, counts, shares, average
rating, theme names and the verbatim quotes (CMP-2, CMP-3). The model writes only one summary
and one action per top theme, within a word budget left over by the fixed parts.
"""

import json
import logging
import re
from datetime import date, timedelta
from pathlib import Path

from pydantic import BaseModel

from pulse.config import Config
from pulse.llm import Llm
from pulse.models import CleanReview, window_for
from pulse.select import Quote, Selection
from pulse.textfilter import word_count
from pulse.themes import MAX_REVIEW_CHARS, load_prompts

log = logging.getLogger(__name__)

PROMPTS = Path(__file__).resolve().parents[2] / "prompts" / "compose.md"
STORE_LABEL = {"play": "Play Store"}
SECTIONS = ("Top themes", "What users said", "Action ideas")
SLACK_WORDS = 10  # headroom under the cap, so a model that runs slightly long still fits
SUMMARY_SHARE = 0.4  # of each theme's word budget; the rest goes to the action
# Statistics come from code only; the model must not add its own (CMP-3).
INVENTED_STAT = re.compile(
    r"\d\s*%|\bper\s?cent\b|\b\d[\d,]*\s+(?:users|reviews|reviewers|people|customers|complaints"
    r"|ratings)\b",
    re.I,
)
QUOTE_MARKS = re.compile(r"[\"“”]")


class ComposeError(Exception):
    """The fixed parts of the note leave no room for the model's copy."""


class ThemeCopy(BaseModel):
    summary: str
    action: str


class Composed(BaseModel):
    themes: list[ThemeCopy]


def date_range(start: date, end: date) -> str:
    """ "3–9 Nov 2026", "26 Oct – 1 Nov 2026" or "29 Dec 2025 – 4 Jan 2026" (CMP-8)."""
    if start.year != end.year:
        return f"{start.day} {start:%b %Y} – {end.day} {end:%b %Y}"
    if start.month != end.month:
        return f"{start.day} {start:%b} – {end.day} {end:%b %Y}"
    return f"{start.day}–{end.day} {end:%b %Y}"


def quote_body(q: Quote) -> str:
    """The verbatim span with ellipses where it was cut."""
    end = (" …" if q.text[-1] in ".!?…" else "…") if q.cut_end else ""
    return ("…" if q.cut_start else "") + q.text + end


def render_quote(q: Quote) -> str:
    return f"“{quote_body(q)}” — {q.rating}★, {STORE_LABEL.get(q.store, q.store)}"


def render(sel: Selection, copy: list[ThemeCopy], cfg: Config) -> str:
    monday = date.fromisoformat(f"{sel.run_id}-1")
    window = window_for(sel.run_id, cfg.window_weeks)
    stores = sorted({STORE_LABEL.get(q.store, q.store) for q in sel.quotes})
    lines = [
        f"# {cfg.app.name} Weekly Review Pulse — {date_range(monday, monday + timedelta(6))}",
        "",
        f"{sel.total_reviews:,} reviews · "
        f"{date_range(window.start.date(), window.end.date() - timedelta(1))} · "
        f"avg rating {sel.avg_rating:.1f} · {', '.join(stores)}",
        "",
        f"## {SECTIONS[0]}",
        "",
        *(
            f"{i}. {t.name} ({round(t.share * 100)}%) — {c.summary}"
            for i, (t, c) in enumerate(zip(sel.top, copy, strict=True), 1)
        ),
        "",
        f"## {SECTIONS[1]}",
        "",
        *(f"- {render_quote(q)}" for q in sel.quotes),
        "",
        f"## {SECTIONS[2]}",
        "",
        *(
            f"{i}. {t.name}: {c.action}"
            for i, (t, c) in enumerate(zip(sel.top, copy, strict=True), 1)
        ),
    ]
    return "\n".join(lines) + "\n"


def word_budget(sel: Selection, cfg: Config) -> tuple[int, int]:
    """Words per summary and per action that the fixed parts leave under the cap (CMP-6)."""
    blank = [ThemeCopy(summary="", action="")] * len(sel.top)
    left = cfg.note.max_words - word_count(render(sel, blank, cfg)) - SLACK_WORDS
    per_theme = left // len(sel.top)
    summary = int(per_theme * SUMMARY_SHARE)
    if summary < 8 or per_theme - summary < 10:
        raise ComposeError(
            f"fixed parts leave {left} words for {len(sel.top)} themes; quotes are too long"
        )
    return summary, per_theme - summary


def _theme_blocks(sel: Selection, reviews: dict[str, CleanReview]) -> str:
    blocks = []
    for i, (t, q) in enumerate(zip(sel.top, sel.quotes, strict=True), 1):
        lines = []
        for rid in t.grounding_ids:
            r = reviews[rid]
            text = r.text if len(r.text) <= MAX_REVIEW_CHARS else r.text[:MAX_REVIEW_CHARS]
            line = {"rating": r.rating, "text": text + (" [cut]" if text != r.text else "")}
            lines.append(json.dumps(line, ensure_ascii=False))
        blocks.append(
            f"Theme {i}: {t.name}\n"
            f"Definition: {t.definition} Includes: {t.includes}\n"
            f"Reviews in this theme are {round(t.severity * 100)}% rated 1-2 stars, "
            f"average {t.avg_rating:.1f} stars.\n"
            f"Quote the note shows for this theme: {q.text}\n"
            f"Sample reviews:\n<reviews>\n" + "\n".join(lines) + "\n</reviews>"
        )
    return "\n\n".join(blocks)


def compose(
    llm: Llm,
    sel: Selection,
    reviews: list[CleanReview],
    cfg: Config,
    feedback: list[str] | None = None,
) -> str:
    """The pulse as Markdown. The model's copy is checked against the note's rules and retried.

    `feedback` is the validation gate's error list from a rejected draft (Phase 5).
    """
    prompts = load_prompts(PROMPTS)
    summary_words, action_words = word_budget(sel, cfg)
    count = len(sel.top)

    def check(out: Composed) -> list[str]:
        if len(out.themes) != count:
            return [f"return exactly {count} entries, one per theme, got {len(out.themes)}"]
        errors = []
        for i, c in enumerate(out.themes, 1):
            for field in ("summary", "action"):
                value = getattr(c, field).strip()
                if not value:
                    errors.append(f"theme {i}: {field} is empty")
                if "\n" in value:
                    errors.append(f"theme {i}: {field} must be a single line")
                if INVENTED_STAT.search(value):
                    errors.append(f"theme {i}: {field} contains a number or percentage; remove it")
                if QUOTE_MARKS.search(value):
                    errors.append(f"theme {i}: {field} contains quotation marks; remove them")
        if not errors:
            n = word_count(render(sel, _clean(out), cfg))
            if n > cfg.note.max_words:
                errors.append(
                    f"the note is {n} words; the limit is {cfg.note.max_words}. "
                    f"Shorten the summaries first, then the actions, by {n - cfg.note.max_words}"
                    " words or more"
                )
        return errors

    prompt = prompts["compose"].substitute(
        count=count,
        summary_words=summary_words,
        action_words=action_words,
        max_words=cfg.note.max_words,
        themes=_theme_blocks(sel, {r.id: r for r in reviews}),
    )
    if feedback:
        errors = "\n".join(f"- {e}" for e in feedback)
        prompt += "\n\n" + prompts["retry"].substitute(errors=errors)
    out = llm.structured(
        system=prompts["system"].substitute(app=cfg.app.name),
        prompt=prompt,
        schema=Composed,
        effort="medium",
        validate=check,
    )
    pulse = render(sel, _clean(out), cfg)
    log.info("compose: %d words", word_count(pulse))
    return pulse


def _clean(out: Composed) -> list[ThemeCopy]:
    return [ThemeCopy(summary=c.summary.strip(), action=c.action.strip()) for c in out.themes]
