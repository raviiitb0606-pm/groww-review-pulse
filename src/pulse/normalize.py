"""Map raw records to the common schema. Reviewer identity is dropped here."""

import hashlib
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable

from pulse.models import IST, RawReview, Review, Window

ZERO_WIDTH = re.compile("[​‌‍⁠﻿]")
WHITESPACE = re.compile(r"\s+")


def review_id(store: str, source_id: str) -> str:
    return hashlib.sha256(f"{store}:{source_id}".encode()).hexdigest()


def clean_text(text: str | None) -> str:
    """NFC, zero-width characters removed, whitespace collapsed (NRM-8)."""
    if not text:
        return ""
    text = ZERO_WIDTH.sub("", unicodedata.normalize("NFC", text))
    return WHITESPACE.sub(" ", text).strip()


def has_words(text: str) -> bool:
    """False for emoji-only or punctuation-only text (NRM-6)."""
    return any(ch.isalnum() for ch in text)


def detect_lang(text: str) -> str:
    """Coarse script check: `en` when letters are mostly Latin, else `und`.

    Hinglish written in Latin script is tagged `en`; a known limitation.
    """
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return "und"
    latin = sum(1 for ch in letters if ch.isascii())
    return "en" if latin / len(letters) >= 0.9 else "und"


def dedupe_key(text: str) -> str:
    return text.casefold()


def normalize(
    raw: Iterable[RawReview], window: Window, min_chars: int
) -> tuple[list[Review], Counter]:
    """Return reviews newest-first plus drop counts. Counts never include review text."""
    stats: Counter = Counter()
    latest: dict[str, RawReview] = {}
    for r in raw:
        stats["fetched"] += 1
        if not window.contains(r.at):
            stats["dropped_out_of_window"] += 1
            continue
        if not isinstance(r.rating, int) or not 1 <= r.rating <= 5:
            stats["dropped_bad_rating"] += 1
            continue
        rid = review_id(r.store, r.source_id)
        if rid in latest:
            stats["dup_id"] += 1
            if r.at <= latest[rid].at:
                continue
        latest[rid] = r  # an edited review keeps its latest version (ING-9)

    out: list[Review] = []
    seen_text: set[str] = set()
    for rid, r in sorted(latest.items(), key=lambda kv: (kv[1].at, kv[0]), reverse=True):
        text = clean_text(r.text)
        if not has_words(text):
            stats["dropped_empty"] += 1
            continue
        if len(text) < min_chars:
            stats["dropped_short"] += 1
            continue
        key = dedupe_key(text)
        if key in seen_text:
            stats["dup_text"] += 1
            continue
        seen_text.add(key)
        out.append(
            Review(
                id=rid,
                store=r.store,
                rating=r.rating,
                title=clean_text(r.title) or None,
                text=text,
                date=r.at.astimezone(IST).date(),
                app_version=r.app_version,
                lang=detect_lang(text),
            )
        )
    stats["kept"] = len(out)
    return out, stats
