"""Selection: rank themes to the top 3 and pick one verbatim quote per top theme.

See architecture.md §3.5 and edge-cases.md §5. A quote is a contiguous substring of a cleaned
review, cut only at sentence or clause boundaries. The ellipsis that marks a cut is added at
render time, outside the stored span, so the span always matches the corpus exactly (SEL-4).
"""

import json
import logging
import random
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from pulse.config import Config, Weights
from pulse.llm import Llm
from pulse.models import CleanReview
from pulse.pii import detect
from pulse.textfilter import ENGLISH_WORDS, HINGLISH_WORDS, is_english, words
from pulse.themes import OTHER, Theme, ThemeResult, load_prompts

log = logging.getLogger(__name__)

PROMPTS = Path(__file__).resolve().parents[2] / "prompts" / "select.md"

# A sentence boundary keeps its punctuation in the span; a clause boundary drops the comma.
BOUNDARY = re.compile(r"([.!?…]+)\s+|([,;:])\s+|(\s*\n\s*)")
# Dropping text that starts with one of these could flip the quote's meaning (SEL-4).
CONTRAST = re.compile(
    r"(?i)(?:but|not|no|never|nothing|except|however|although|though|yet|unless|until|only"
    r"|otherwise|still)\b"
)
# A span that ends on a connector, or that opens on one after a cut, reads as torn from its
# context ("...failure screen. However", "...But not for intraday").
DANGLING = re.compile(
    r"(?i)\b(?:however|but|and|or|so|because|also|although|though|then|which|that|if|as|with)$"
)
OPENER = re.compile(r"(?i)(?:however|but|and|or|so|because|also|although|though|yet)\b")
# Quotes are rendered verbatim, so Markdown marks, quote marks and the scrubber's [placeholders]
# are never allowed inside one (CMP-9).
FORBIDDEN = re.compile(r"[*_#`\[\]<>|\\\"“”~]")
SHOUTING = 0.5  # share of upper-case letters above which a span reads as shouting
MIX_DEPTH = 3  # SEL-3: how far down a theme's ranked quotes to look for a different rating
NEAR_DUPLICATE = 0.6  # SEL-5: word-set Jaccard at or above this is the same quote
# Words in theme definitions that say nothing about the topic.
GENERIC = frozenset(
    """groww users user reviews review reviewers issues issue problems problem experience
    including include includes such like related regarding around general overall complaints
    praise feedback things""".split()
)


class SelectError(Exception):
    """Too few usable themes or quotes to build a pulse, or a missing input file."""


class ThemeScore(BaseModel):
    name: str
    count: int
    share: float  # of all reviews in the run, `other` included
    severity: float  # share of this theme's reviews rated 1-2
    avg_rating: float
    score: float


class TopTheme(ThemeScore):
    definition: str
    includes: str
    grounding_ids: list[str]  # reviews compose may read to ground the summary and action


class Quote(BaseModel):
    theme: str
    review_id: str
    rating: int
    store: str
    text: str  # verbatim substring of the review's cleaned text
    cut_start: bool = False  # text before the span was dropped; rendered with an ellipsis
    cut_end: bool = False
    flags: list[str] = []  # SEL-7: competitor or legal-claim words, for human review


class Selection(BaseModel):
    """What `selection.json` holds."""

    run_id: str
    total_reviews: int
    avg_rating: float
    ranking: list[ThemeScore]  # every theme, best first
    top: list[TopTheme]
    quotes: list[Quote]  # one per top theme, in the same order


# --- theme ranking -----------------------------------------------------------------------


def rank_themes(
    result: ThemeResult, reviews: list[CleanReview], weights: Weights
) -> list[ThemeScore]:
    """Score = weighted volume plus weighted severity, each scaled to the largest theme's value.

    Scaling puts both terms on 0..1, so the configured weights mean what they say. Ties break
    on severity, then volume, then name (SEL-1). `other` is never ranked.
    """
    rating = {r.id: r.rating for r in reviews}
    members: dict[str, list[int]] = {t.name: [] for t in result.taxonomy}
    for rid, a in result.assignments.items():
        if a.theme != OTHER:
            members[a.theme].append(rating[rid])
    counts = {n: len(rs) for n, rs in members.items()}
    severity = {n: sum(r <= 2 for r in rs) / len(rs) if rs else 0.0 for n, rs in members.items()}
    top_count = max(counts.values(), default=0) or 1
    top_severity = max(severity.values(), default=0) or 1
    scores = [
        ThemeScore(
            name=n,
            count=counts[n],
            share=round(counts[n] / len(reviews), 4),
            severity=round(severity[n], 4),
            avg_rating=round(sum(rs) / len(rs), 2) if rs else 0.0,
            score=round(
                weights.volume * counts[n] / top_count
                + weights.severity * severity[n] / top_severity,
                6,
            ),
        )
        for n, rs in members.items()
    ]
    return sorted(scores, key=lambda t: (-t.score, -t.severity, -t.count, t.name))


# --- quote spans -------------------------------------------------------------------------


def spans(text: str, lo: int, hi: int) -> list[tuple[int, int]]:
    """Every (start, end) that starts a sentence, ends a sentence or clause, and is lo..hi chars.

    A span is never cut just before text that opens with a negation or contrast word, so
    "Good app, but withdrawals fail" cannot become "Good app".
    """
    starts, ends = [0], []
    for m in BOUNDARY.finditer(text):
        if m.group(2):
            ends.append(m.start())
        elif m.group(1):
            ends.append(m.end(1))
            starts.append(m.end())
        else:
            ends.append(m.start())
            starts.append(m.end())
    full_end = len(text.rstrip())
    ends.append(full_end)
    out = []
    for s in starts:
        for e in ends:
            if e <= s or not lo <= e - s <= hi or text[e - 1].isspace():
                continue
            rest = text[e:].lstrip(" \n,;:.!?…")
            if (e < full_end and CONTRAST.match(rest)) or DANGLING.search(text[s:e]):
                continue
            if s > 0 and OPENER.match(text[s:e]):
                continue
            out.append((s, e))
    return sorted(set(out))


@dataclass(frozen=True)
class Candidate:
    review: CleanReview
    start: int
    end: int
    score: float
    flags: tuple[str, ...]

    @property
    def text(self) -> str:
        return self.review.text[self.start : self.end]

    @property
    def cut_start(self) -> bool:
        return self.start > 0

    @property
    def cut_end(self) -> bool:
        return self.end < len(self.review.text.rstrip())

    def quote(self, theme: str) -> Quote:
        return Quote(
            theme=theme,
            review_id=self.review.id,
            rating=self.review.rating,
            store=self.review.store,
            text=self.text,
            cut_start=self.cut_start,
            cut_end=self.cut_end,
            flags=list(self.flags),
        )


def theme_keywords(theme: Theme) -> set[str]:
    """Five-letter stems of the theme's topic words, so "charge" and "charges" match."""
    text = f"{theme.name} {theme.definition} {theme.includes}".casefold()
    return {
        w[:5] for w in words(text) if len(w) >= 3 and w not in ENGLISH_WORDS and w not in GENERIC
    }


def _usable(span: str, blocked: set[str]) -> bool:
    tokens = [w.casefold() for w in words(span)]
    letters = sum(c.isalpha() for c in span)
    return (
        len(tokens) >= 4
        and not FORBIDDEN.search(span)
        and not blocked.intersection(tokens)
        and letters >= 0.6 * len(span)
        and is_english(span)  # NRM-5: Hinglish can be themed but is never quoted
        and not HINGLISH_WORDS.intersection(tokens)
        and not detect(span)
    )


def score_span(span: str, keywords: set[str], high_confidence: bool, whole: bool) -> float:
    """Relevance (theme words hit) and clarity (length, reads cleanly, no shouting), both 0..1."""
    stems = {w.casefold()[:5] for w in words(span)}
    relevance = min(len(keywords & stems), 3) / 3
    letters = [c for c in span if c.isalpha()]
    # Short spans keep the note under the word cap (CMP-6); a long review gets trimmed.
    clarity = 0.8 if 30 <= len(span) <= 120 else 0.6 if len(span) <= 160 else 0.4
    clarity += 0.1 * span[0].isupper() + 0.1 * (span[-1] in ".!…")
    if sum(c.isupper() for c in letters) > SHOUTING * len(letters):
        clarity -= 0.4
    if re.search(r"(.)\1{3,}|[!?]{2,}", span):
        clarity -= 0.3
    return round(0.6 * relevance + 0.3 * clarity + 0.07 * high_confidence + 0.03 * whole, 6)


def best_span(
    review: CleanReview,
    keywords: set[str],
    high_confidence: bool,
    bounds: tuple[int, int],
    blocked: set[str],
    flag_words: set[str],
) -> Candidate | None:
    """The review's best-scoring usable span, or None. Each review yields at most one quote."""
    best: Candidate | None = None
    text = review.text
    full_end = len(text.rstrip())
    for s, e in spans(text, *bounds):
        span = text[s:e]
        if not _usable(span, blocked):
            continue
        score = score_span(span, keywords, high_confidence, s == 0 and e == full_end)
        if best is None or score > best.score:
            flags = tuple(sorted(flag_words.intersection(w.casefold() for w in words(span))))
            best = Candidate(review, s, e, score, flags)
    return best


def theme_candidates(
    theme: Theme,
    reviews: list[CleanReview],
    result: ThemeResult,
    cfg: Config,
) -> list[Candidate]:
    """Quote candidates for a theme, best first: unflagged before flagged, then by score.

    Falls back to the relaxed length bounds only when the normal ones yield nothing (SEL-2).
    """
    keywords = theme_keywords(theme)
    blocked = {w.casefold() for w in cfg.select.blocked_words}
    flag_words = {w.casefold() for w in cfg.select.flag_words}
    members = [
        r for r in reviews if r.quote_eligible and result.assignments[r.id].theme == theme.name
    ]
    for bounds in (cfg.select.quote_chars, cfg.select.relaxed_quote_chars):
        found = [
            c
            for r in members
            if (
                c := best_span(
                    r,
                    keywords,
                    result.assignments[r.id].confidence == "high",
                    bounds,
                    blocked,
                    flag_words,
                )
            )
        ]
        if found:
            return sorted(found, key=lambda c: (bool(c.flags), -c.score, c.review.id))
        log.info("select: no quote in %s chars for a theme; relaxing", bounds)
    return []


# --- LLM re-rank -------------------------------------------------------------------------


class ThemePick(BaseModel):
    theme: int
    keys: list[int]


class Ranked(BaseModel):
    picks: list[ThemePick]


def llm_rank(
    llm: Llm, themes: list[Theme], pools: list[list[Candidate]], app: str
) -> list[list[Candidate]]:
    """Ask the model which candidates best show each theme; it returns keys only, never text.

    Each theme's list comes back as the model's picks first, then the rest in heuristic order.
    """
    prompts = load_prompts(PROMPTS)
    key_of: dict[int, tuple[int, Candidate]] = {}
    blocks = []
    for i, (theme, pool) in enumerate(zip(themes, pools, strict=True), 1):
        lines = []
        for c in pool:
            key = len(key_of) + 1
            key_of[key] = (i, c)
            line = {"key": key, "rating": c.review.rating, "text": c.text}
            lines.append(json.dumps(line, ensure_ascii=False))
        blocks.append(
            f"Theme {i}: {theme.name}: {theme.definition}\n<reviews>\n"
            + "\n".join(lines)
            + "\n</reviews>"
        )

    def check(out: Ranked) -> list[str]:
        errors = []
        numbers = [p.theme for p in out.picks]
        if sorted(numbers) != list(range(1, len(themes) + 1)):
            errors.append(f"return exactly one entry per theme 1..{len(themes)}, got {numbers}")
        all_keys = [k for p in out.picks for k in p.keys]
        if dupes := sorted(k for k, n in Counter(all_keys).items() if n > 1):
            errors.append(f"keys used more than once: {dupes}")
        for p in out.picks:
            if not 1 <= len(p.keys) <= 3:
                errors.append(f"theme {p.theme}: return 1 to 3 keys, got {len(p.keys)}")
            if wrong := [k for k in p.keys if key_of.get(k, (None,))[0] != p.theme]:
                errors.append(f"theme {p.theme}: keys not listed under this theme: {wrong}")
        return errors

    out = llm.structured(
        system=prompts["system"].substitute(app=app),
        prompt=prompts["rank"].substitute(themes="\n\n".join(blocks)),
        schema=Ranked,
        effort="low",
        validate=check,
    )
    picked = {p.theme: [key_of[k][1] for k in p.keys] for p in out.picks}
    return [picked[i] + [c for c in pool if c not in picked[i]] for i, pool in enumerate(pools, 1)]


# --- final choice ------------------------------------------------------------------------


def _band(rating: int) -> str:
    return "low" if rating <= 2 else "mid" if rating == 3 else "high"


def _similar(a: Candidate, b: Candidate) -> bool:
    if a.review.id == b.review.id:
        return True
    wa, wb = ({w.casefold() for w in words(c.text)} for c in (a, b))
    return len(wa & wb) / len(wa | wb) >= NEAR_DUPLICATE


def choose(ranked: list[list[Candidate]]) -> list[Candidate]:
    """One quote per theme: the best one, unless every pick so far shares a rating (SEL-3).

    In that case look a little further down for another rating band, then another rating.
    Near-duplicates of earlier picks are skipped (SEL-5).
    """
    chosen: list[Candidate] = []
    for pool in ranked:
        fresh = [c for c in pool if not any(_similar(c, p) for p in chosen)] or pool
        front = fresh[:MIX_DEPTH]
        pick = front[0]
        if chosen and len({c.review.rating for c in chosen}) == 1:
            bands = {_band(c.review.rating) for c in chosen}
            ratings = {c.review.rating for c in chosen}
            pick = next(
                (c for c in front if _band(c.review.rating) not in bands),
                next((c for c in front if c.review.rating not in ratings), pick),
            )
        chosen.append(pick)
    return chosen


def grounding_ids(theme: str, result: ThemeResult, size: int, seed: int) -> list[str]:
    """A seeded sample of the theme's reviews, high-confidence first, for compose to read."""
    ids = sorted(rid for rid, a in result.assignments.items() if a.theme == theme)
    high = [rid for rid in ids if result.assignments[rid].confidence == "high"]
    pool = high if len(high) >= size else ids
    return sorted(random.Random(f"{seed}:{theme}").sample(pool, min(size, len(pool))))


def select(
    llm: Llm, result: ThemeResult, reviews: list[CleanReview], cfg: Config, run_id: str
) -> Selection:
    ranking = rank_themes(result, reviews, cfg.themes.weights)
    by_name = {t.name: t for t in result.taxonomy}
    top: list[ThemeScore] = []
    pools: list[list[Candidate]] = []
    for score in ranking:
        if len(top) == cfg.themes.top_k:
            break
        pool = theme_candidates(by_name[score.name], reviews, result, cfg)
        if not pool:
            log.warning("select: theme ranked %d has no quotable review; skipping", len(top) + 1)
            continue
        top.append(score)
        pools.append(pool[: cfg.select.rank_candidates])
    if len(top) < cfg.themes.top_k:
        raise SelectError(f"only {len(top)} themes have a quotable review; need {cfg.themes.top_k}")

    themes = [by_name[t.name] for t in top]
    picks = choose(llm_rank(llm, themes, pools, cfg.app.name))
    return Selection(
        run_id=run_id,
        total_reviews=len(reviews),
        avg_rating=round(sum(r.rating for r in reviews) / len(reviews), 2),
        ranking=ranking,
        top=[
            TopTheme(
                **t.model_dump(),
                definition=th.definition,
                includes=th.includes,
                grounding_ids=grounding_ids(
                    t.name, result, cfg.select.grounding_sample, cfg.themes.seed
                ),
            )
            for t, th in zip(top, themes, strict=True)
        ],
        quotes=[c.quote(t.name) for c, t in zip(picks, top, strict=True)],
    )
