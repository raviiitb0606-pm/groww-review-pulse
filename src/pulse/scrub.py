"""Scrub stage logic: filter by language and length, strip emoji, redact PII, verify clean."""

from collections import Counter

from pulse.config import Scrub
from pulse.models import CleanReview, Review
from pulse.pii import detect, scrub_with_stats
from pulse.textfilter import is_english, strip_emoji, word_count


class ScrubError(Exception):
    """Raised when PII survives scrubbing; nothing is written and the raw file is kept."""


def scrub_reviews(reviews: list[Review], cfg: Scrub) -> tuple[list[CleanReview], Counter]:
    """Return clean reviews plus drop counts. Counts never include review text."""
    stats: Counter = Counter()
    out: list[CleanReview] = []
    seen: set[str] = set()
    for r in reviews:
        stats["input"] += 1
        text = strip_emoji(r.text)
        if word_count(text) <= cfg.min_words:
            stats["dropped_short"] += 1
            continue
        if cfg.english_only and not is_english(text):
            stats["dropped_non_english"] += 1
            continue
        key = text.casefold()
        if key in seen:  # emoji removal can make previously distinct texts identical
            stats["dup_text"] += 1
            continue
        seen.add(key)

        body = scrub_with_stats(text)
        title = scrub_with_stats(strip_emoji(r.title)).text if r.title else None
        share = body.redacted_chars / len(text)
        eligible = share <= cfg.max_redaction_share
        stats["quote_ineligible"] += not eligible
        stats["redacted_reviews"] += body.redacted_chars > 0
        out.append(
            CleanReview(
                **r.model_dump(exclude={"text", "title", "lang"}),
                text=body.text,
                title=title or None,
                lang="en",
                quote_eligible=eligible,
            )
        )

    leaks = [c.id for c in out if detect(c.text) or (c.title and detect(c.title))]
    if leaks:
        raise ScrubError(f"PII detected after scrub in {len(leaks)} reviews (ids: {leaks[:5]})")
    stats["kept"] = len(out)
    return out, stats
