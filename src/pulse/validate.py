"""Validation gate: the rules a pulse must pass before publish (architecture.md §3.7).

The checks parse the rendered Markdown, the exact payload the publish stage sends (VAL-4).
They do not trust the selection or the composer's structured output. Every rule runs on every
attempt (VAL-3). Error messages hold rule names, positions and theme names only, never review
text, so they are safe to log and to write to `validation.json`.
"""

import re
from dataclasses import dataclass, field

from pulse.compose import SECTIONS, STORE_LABEL
from pulse.config import Config
from pulse.models import CleanReview
from pulse.pii import detect
from pulse.textfilter import word_count
from pulse.themes import OTHER

CHECKS = ("length", "structure", "themes", "quotes", "actions", "pii")

ITEM = re.compile(r"(\d+)\. (.*)")
THEME_LINE = re.compile(r"(?P<name>.+?) \((?P<share>\d+)%\) — (?P<summary>.*)")
QUOTE_LINE = re.compile(r"- “(?P<body>.*)” — (?P<rating>[1-5])★, (?P<store>.+)")
# A review id or another long hex token in the note means a reviewer field leaked.
REVIEWER_FIELD = re.compile(r"\b[0-9a-f]{32,}\b")
STORE_KEY = {label: key for key, label in STORE_LABEL.items()}


class ValidateError(Exception):
    """The pulse failed the gate after the compose retries. Nothing is published."""


@dataclass
class Report:
    word_count: int = 0
    errors: dict[str, list[str]] = field(default_factory=lambda: {c: [] for c in CHECKS})

    @property
    def passed(self) -> bool:
        return not any(self.errors.values())

    def flat(self) -> list[str]:
        return [f"{check}: {e}" for check, errs in self.errors.items() for e in errs]

    def to_json(self) -> dict:
        return {
            "passed": self.passed,
            "word_count": self.word_count,
            "checks": {c: not errs for c, errs in self.errors.items()},
            "errors": self.flat(),
        }


def split_sections(text: str) -> tuple[list[str], dict[str, list[str]], list[str]]:
    """The lines before the first `## ` heading, each section's non-blank lines, heading order."""
    head: list[str] = []
    sections: dict[str, list[str]] = {}
    order: list[str] = []
    current = head
    for line in text.splitlines():
        if line.startswith("## "):
            name = line[3:].strip()
            order.append(name)
            current = sections.setdefault(name, [])
        elif line.strip():
            current.append(line.rstrip())
    return head, sections, order


def numbered(lines: list[str], section: str, errors: list[str]) -> list[str]:
    """The bodies of `1. ...`, `2. ...` items; reports any other line or a numbering gap."""
    bodies = []
    for i, line in enumerate(lines, 1):
        m = ITEM.fullmatch(line)
        if not m:
            errors.append(f"{section}: line {i} is not a numbered item")
            continue
        if int(m.group(1)) != len(bodies) + 1:
            errors.append(f"{section}: item {i} is numbered {m.group(1)}")
        bodies.append(m.group(2).strip())
    return bodies


def strip_ellipsis(body: str) -> str:
    """The verbatim span inside a rendered quote; the cut marks are added outside it."""
    body = body.removeprefix("…")
    return body.removesuffix(" …").removesuffix("…")


def check_structure(head: list[str], sections: dict, order: list[str], errors: list[str]) -> None:
    if not head or not head[0].startswith("# ") or "Weekly Review Pulse" not in head[0]:
        errors.append("the note must open with the `# ... Weekly Review Pulse` title")
    if len(head) < 2:
        errors.append("the stats line under the title is missing")
    if order != list(SECTIONS):
        errors.append(f"sections must be {list(SECTIONS)} in that order, got {order}")
    for name in SECTIONS:
        if name in sections and not sections[name]:
            errors.append(f"section {name!r} is empty")


def check_themes(lines: list[str], taxonomy: set[str], want: int, errors: list[str]) -> list[str]:
    """The listed theme names, in order."""
    names = []
    for i, body in enumerate(numbered(lines, SECTIONS[0], errors), 1):
        m = THEME_LINE.fullmatch(body)
        if not m:
            errors.append(f"theme {i}: expected `<theme> (<share>%) — <summary>`")
            continue
        name = m.group("name")
        names.append(name)
        if name == OTHER or name not in taxonomy:
            errors.append(f"theme {i}: {name!r} is not one of this run's themes")
        if not m.group("summary").strip():
            errors.append(f"theme {i}: the summary is empty")
    if len(lines) != want:
        errors.append(f"expected exactly {want} themes, got {len(lines)}")
    if len(set(names)) != len(names):
        errors.append("a theme is listed more than once")
    return names


def check_quotes(lines: list[str], reviews: list[CleanReview], want: int, errors: list[str]):
    for i, line in enumerate(lines, 1):
        m = QUOTE_LINE.fullmatch(line)
        if not m:
            errors.append(f"quote {i}: expected `- “<quote>” — <rating>★, <store>`")
            continue
        span = strip_ellipsis(m.group("body"))
        if len(span.strip()) < 2:
            errors.append(f"quote {i}: empty")
            continue
        sources = [r for r in reviews if span in r.text]
        if not sources:
            errors.append(f"quote {i}: not an exact substring of any cleaned review")
            continue
        rating, store = int(m.group("rating")), STORE_KEY.get(m.group("store"), m.group("store"))
        if not any(r.rating == rating and r.store == store for r in sources):
            errors.append(f"quote {i}: the rating or store does not match its source review")
    if len(lines) != want:
        errors.append(f"expected exactly {want} quotes, got {len(lines)}")


def check_actions(lines: list[str], listed: list[str], want: int, errors: list[str]) -> None:
    for i, body in enumerate(numbered(lines, SECTIONS[2], errors), 1):
        named = [n for n in listed if n.casefold() in body.casefold()]
        if not named:
            errors.append(f"action {i}: does not name one of the listed themes")
            continue
        rest = re.sub(re.escape(named[0]), "", body, count=1, flags=re.I)
        if not word_count(rest):
            errors.append(f"action {i}: names a theme but gives no next step")
    if len(lines) != want:
        errors.append(f"expected exactly {want} actions, got {len(lines)}")


def validate(text: str, taxonomy: list[str], reviews: list[CleanReview], cfg: Config) -> Report:
    """Run every rule on the rendered pulse. `taxonomy` is the run's theme names."""
    report = Report(word_count=word_count(text))
    errors = report.errors
    if report.word_count > cfg.note.max_words:
        errors["length"].append(
            f"the note is {report.word_count} words; the limit is {cfg.note.max_words}"
        )

    head, sections, order = split_sections(text)
    check_structure(head, sections, order, errors["structure"])
    listed = check_themes(
        sections.get(SECTIONS[0], []), set(taxonomy), cfg.themes.top_k, errors["themes"]
    )
    check_quotes(sections.get(SECTIONS[1], []), reviews, cfg.note.quotes, errors["quotes"])
    check_actions(sections.get(SECTIONS[2], []), listed, cfg.note.actions, errors["actions"])

    if hits := detect(text):
        errors["pii"].append(f"the PII detector matched: {', '.join(sorted(set(hits)))}")
    if REVIEWER_FIELD.search(text):
        errors["pii"].append("the note contains a review id or another reviewer field")
    return report
