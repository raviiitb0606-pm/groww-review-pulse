"""PII scrubber and detector. Both share one pattern set so the validate gate agrees with scrub."""

import re
from dataclasses import dataclass

from pulse.textfilter import ENGLISH_WORDS

REDACTED = "[redacted]"
NAME = "[name]"

# Words that can follow a greeting or sign-off without being a person's name (PII-14).
NOT_NAMES = (
    frozenset(
        """groww grow team sir sirs madam mam maam support customer care everyone all there guys
    folks
    friends sirji bhai the this that for you your it its and but so i we my our to of in on
    app please also just very much sorry good platform service broker trading great nice super
    awesome excellent amazing thank experience""".split()
    )
    | ENGLISH_WORDS
)

_NAME_WORD = r"[A-Z][a-z]{2,}"
_NAME_CONTEXT = (
    r"(?:\b(?i:hi|hello|hey|dear|regards|thanks|thank you|cheers|sincerely)\b[,\s]+)"
    rf"({_NAME_WORD}(?:\s{_NAME_WORD})?)(?=\s*(?:[,.!:;\u2013\u2014-]|$))"
)

# Order matters: more specific shapes first so a PAN or ref id is not eaten by a digit-run rule.
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    (
        "url",
        re.compile(r"(?i)\b(?:https?://|www\.)\S+|\b[\w-]+\.(?:com|in|co|me|io|app|net|org)/\S*"),
    ),
    (
        "upi",
        re.compile(
            r"(?i)\b[\w.-]{2,}@(?:ok\w+|ybl|ibl|axl|paytm|upi|apl|sbi|hdfc\w*|icici|axis\w*|oksbi)\b"
        ),
    ),
    ("pan", re.compile(r"\b[A-Za-z]{5}\d{4}[A-Za-z]\b")),
    (
        "reference",
        re.compile(
            r"(?i)\b(?:ref(?:erence)?|order|txn|transaction|utr|ticket|request|complaint|case)"
            r"(?:\s*(?:no|number|num|id|#))?\s*[:#-]?\s*[A-Za-z]*\d{5,}[A-Za-z\d]*"
        ),
    ),
    ("aadhaar", re.compile(r"(?<![\d-])\d{4}[ -]?\d{4}[ -]?\d{4}(?![\d-])")),
    (
        "phone",
        re.compile(r"(?<![\d.,])(?:(?:\+|00)?91[\s-]?|0)?[6-9]\d{4}[\s-]?\d{5}(?![\d,]\d|\d)"),
    ),
    ("digits", re.compile(r"(?<![\d,.])\d{9,18}(?![\d,]\d|\d)")),
]
NAME_PATTERN = re.compile(_NAME_CONTEXT)


@dataclass(frozen=True)
class Scrubbed:
    text: str
    redacted_chars: int  # characters of the original replaced; drives the quote_eligible rule


def _is_name(name: str) -> bool:
    return not any(part.casefold() in NOT_NAMES for part in name.split())


def scrub_with_stats(text: str) -> Scrubbed:
    redacted = 0

    def redact(match: re.Match[str]) -> str:
        nonlocal redacted
        redacted += len(match.group(0))
        return REDACTED

    def rename(match: re.Match[str]) -> str:
        nonlocal redacted
        name = match.group(1)
        if not _is_name(name):
            return match.group(0)
        redacted += len(name)
        return match.group(0)[: match.start(1) - match.start()] + NAME

    for _, pattern in PATTERNS:
        text = pattern.sub(redact, text)
    text = NAME_PATTERN.sub(rename, text)
    return Scrubbed(text, redacted)


def scrub(text: str) -> str:
    return scrub_with_stats(text).text


def detect(text: str) -> list[str]:
    """Names of the PII patterns that match `text`. Empty means clean."""
    hits = [name for name, pattern in PATTERNS if pattern.search(text)]
    if any(_is_name(m.group(1)) for m in NAME_PATTERN.finditer(text)):
        hits.append("name")
    return hits
