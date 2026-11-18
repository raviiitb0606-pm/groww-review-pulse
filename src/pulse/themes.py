"""Theming with machine learning: TF-IDF features, NMF topics, at most 5 themes, every review
assigned. No LLM is involved (implementation-plan.md Phase 3).

1. Vectorize each review as TF-IDF over unigrams and bigrams of topic words. Sentiment and filler
   words ("good", "worst", "app") are left out of the vocabulary: the rating already carries
   sentiment, so themes form around topics, not star ratings. A review with no topic words
   ("nice app") has an empty row and goes to `other`.
2. Fit NMF with as many topics as the theme cap. Each review takes its highest-weighted topic.
3. Bisect any topic holding more than `split_share` of the reviews with a 2-topic NMF over its
   members, so one catch-all topic cannot swallow the corpus. When a split goes over the cap, the
   smallest topic is folded into `other` (THM-1).
4. Name each theme from its top terms, reusing last run's name when the terms overlap enough, so
   names stay stable for week-to-week comparison.

On the W44 corpus this beat LSA + k-means and LDA on agreement with the keyword buckets and on
stability across seeds; see the Phase 3 notes in implementation-plan.md.
"""

import logging
import re
from collections import Counter
from pathlib import Path
from string import Template
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field
from scipy.sparse import csr_matrix
from sklearn.decomposition import NMF
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer

from pulse.config import Config
from pulse.models import CleanReview

log = logging.getLogger(__name__)

OTHER = "other"
METHOD = "tfidf-nmf-bisect"
MAX_REVIEW_CHARS = 1200  # NRM-7: very long reviews are cut for the prompt, with a marker
TOKEN = r"(?u)\b[a-zA-Z&][a-zA-Z&]+\b"  # letters and "&", so "f&o" survives; no digits
# Sentiment, praise and filler: they say how a reviewer feels, not what about.
GENERIC_WORDS = frozenset(
    """good bad best worst nice great excellent awesome amazing super poor useless worse better
    love like hate happy sad very really app apps groww grow application please platform
    experience using use used user users thank thanks ok okay osm wow fantastic wonderful fine
    perfect helpful recommend highly loved liked totally just bekar waste rubbish pathetic
    horrible terrible fraud also even much many one get got make made dont don im it's its time
    new add want need give giving know""".split()
)
# Top terms that make a poor theme name on their own.
NAME_SKIP = frozenset("high low open start working properly available able".split())
ACRONYMS = frozenset("f&o ipo sip kyc upi mtf nav dp ui otp etf nfo gtt amc pan".split())
NAME_TERMS = 3
NAME_REUSE = 0.3  # Jaccard overlap of top terms above which last run's name is kept


class ThemeError(Exception):
    """The corpus has no topic vocabulary, or too few themes survive to fill the pulse."""


class Theme(BaseModel):
    name: str
    definition: str
    includes: str


class Assignment(BaseModel):
    theme: str
    confidence: Literal["high", "low"]


class ThemeResult(BaseModel):
    """What `themes.json` holds."""

    taxonomy: list[Theme]
    assignments: dict[str, Assignment]  # review id -> assignment
    capped: list[str] = Field(default_factory=list)  # theme names folded into `other` by the cap


def load_prompts(path: Path) -> dict[str, Template]:
    """A prompt file split on its `## <name>` headings (used by select and compose)."""
    text = re.sub(r"<!--.*?-->", "", path.read_text(), flags=re.S)
    parts = re.split(r"^## (\w+)\s*$", text, flags=re.M)
    return {
        name: Template(body.strip()) for name, body in zip(parts[1::2], parts[2::2], strict=True)
    }


# --- features and topics -----------------------------------------------------------------


def vectorize(texts: list[str], cfg: Config) -> tuple[csr_matrix, np.ndarray]:
    vectorizer = TfidfVectorizer(
        stop_words=sorted(ENGLISH_STOP_WORDS | GENERIC_WORDS),
        token_pattern=TOKEN,
        ngram_range=(1, 2),
        min_df=cfg.themes.min_df,
        max_df=cfg.themes.max_df,
        sublinear_tf=True,
    )
    try:
        X = vectorizer.fit_transform(texts)
    except ValueError as exc:  # every term was pruned: too few or too generic reviews
        raise ThemeError(f"no topic vocabulary: {exc}") from exc
    return X.tocsr(), vectorizer.get_feature_names_out()


def _nmf(X: csr_matrix, k: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Deterministic NMF: `nndsvda` initialisation has no random draw."""
    model = NMF(n_components=k, init="nndsvda", random_state=seed, max_iter=1000)
    return model.fit_transform(X), model.components_


def _top_share(W: np.ndarray) -> np.ndarray:
    """How much of each review's topic weight its best topic holds, 0..1."""
    total = W.sum(axis=1)
    return np.divide(W.max(axis=1), total, out=np.zeros(len(W)), where=total > 0)


def cluster(X: csr_matrix, cfg: Config) -> tuple[np.ndarray, np.ndarray, list, dict]:
    """Topic label per review (-1 for `other`), its weight share, topic term vectors, stats."""
    t = cfg.themes
    n = X.shape[0]
    labels = np.full(n, -1)
    share = np.zeros(n)
    rows = np.flatnonzero(X.getnnz(axis=1))
    k = min(t.max, len(rows), X.shape[1])
    if k < t.top_k:
        raise ThemeError(f"{len(rows)} reviews with topic words; need at least {t.top_k}")
    W, H = _nmf(X[rows], k, t.seed)
    labels[rows], share[rows] = W.argmax(axis=1), _top_share(W)
    topics: list[np.ndarray | None] = list(H)

    splits, folded = 0, []
    while splits < t.max_splits:
        sizes = np.bincount(labels[labels >= 0], minlength=len(topics))
        big = int(sizes.argmax())
        if sizes[big] <= t.split_share * n:
            break
        members = np.flatnonzero(labels == big)
        w2, h2 = _nmf(X[members], 2, t.seed)
        sub = w2.argmax(axis=1)
        if np.bincount(sub, minlength=2).min() < t.min_theme_share * n:
            break  # the split would leave a sliver, not a theme
        topics[big] = h2[0]
        topics.append(h2[1])
        labels[members[sub == 1]] = len(topics) - 1
        share[members] = _top_share(w2)
        splits += 1
        sizes = np.bincount(labels[labels >= 0], minlength=len(topics))
        alive = np.flatnonzero(sizes)
        for c in alive[np.argsort(sizes[alive], kind="stable")][: max(0, len(alive) - t.max)]:
            labels[labels == c] = -1
            folded.append(topics[c])
            topics[c] = None
    return labels, share, topics, {"splits": splits, "folded": folded}


# --- names -------------------------------------------------------------------------------


def _label(term: str) -> str:
    return " ".join(w.upper() if w in ACRONYMS else w.capitalize() for w in term.split())


def describe(weights: np.ndarray, vocab: np.ndarray) -> Theme:
    """Name a topic from its top terms, skipping terms that repeat a word already used.

    Words compare by five-letter stem, so "charge" repeats "charges".
    """
    ranked = [str(vocab[i]) for i in np.argsort(-weights, kind="stable")[:12]]
    picked: list[str] = []
    used: set[str] = set()
    for term in ranked:
        stems = {w[:5] for w in term.split()}
        if term in NAME_SKIP or stems & used:
            continue
        picked.append(term)
        used |= stems
        if len(picked) == NAME_TERMS:
            break
    return Theme(
        name=" / ".join(_label(term) for term in picked or ranked[:1]),
        definition=f"Reviews mentioning {', '.join(ranked[:5])}.",
        includes=", ".join(ranked[:10]),
    )


def _terms(theme: Theme) -> set[str]:
    return {term.strip() for term in theme.includes.split(",") if term.strip()}


def _overlap(a: Theme, b: Theme) -> float:
    ta, tb = _terms(a), _terms(b)
    return len(ta & tb) / len(ta | tb) if ta | tb else 0.0


def reuse_names(themes: list[Theme], previous: list[Theme] | None) -> list[Theme]:
    """Give a theme last run's name when their top terms overlap enough (stable trend names)."""
    if not previous:
        return themes
    out, used = [], set()
    for theme in themes:
        best = max(previous, key=lambda p: (_overlap(theme, p), p.name))
        names = {t.name for t in themes if t is not theme} | used
        if _overlap(theme, best) >= NAME_REUSE and best.name not in names:
            theme = theme.model_copy(update={"name": best.name})
        used.add(theme.name)
        out.append(theme)
    return out


# --- the stage -------------------------------------------------------------------------


def build_themes(
    reviews: list[CleanReview], cfg: Config, previous: list[Theme] | None = None
) -> tuple[ThemeResult, dict]:
    """Every review gets one theme or `other`. Returns the result and clustering diagnostics."""
    ordered = sorted(reviews, key=lambda r: r.id)  # THM-7: input order cannot change the result
    X, vocab = vectorize([r.text for r in ordered], cfg)
    labels, share, topics, info = cluster(X, cfg)

    alive = sorted(
        (c for c, h in enumerate(topics) if h is not None and np.any(labels == c)),
        key=lambda c: (-int(np.sum(labels == c)), c),
    )
    if len(alive) < cfg.themes.top_k:
        raise ThemeError(f"only {len(alive)} themes found; the pulse needs {cfg.themes.top_k}")
    themes = reuse_names([describe(topics[c], vocab) for c in alive], previous)
    name = {c: t.name for c, t in zip(alive, themes, strict=True)}
    high = cfg.themes.high_confidence
    assignments = {
        r.id: Assignment(
            theme=name.get(int(c), OTHER),
            confidence="high" if c >= 0 and s >= high else "low",
        )
        for r, c, s in zip(ordered, labels, share, strict=True)
    }
    capped = [describe(h, vocab).name for h in info["folded"]]
    diagnostics = {
        "method": METHOD,
        "vocabulary": len(vocab),
        "no_topic_words": int(X.shape[0] - len(np.flatnonzero(X.getnnz(axis=1)))),
        "splits": info["splits"],
    }
    log.info("theme: %d themes, %d splits, vocabulary %d", len(themes), info["splits"], len(vocab))
    return ThemeResult(taxonomy=themes, assignments=assignments, capped=capped), diagnostics


def to_json(result: ThemeResult, run_id: str, method: str = METHOD) -> dict:
    """`themes.json`: each theme with its review ids, plus `other` and low-confidence ids."""
    by_theme: dict[str, list[str]] = {t.name: [] for t in result.taxonomy} | {OTHER: []}
    for rid, a in sorted(result.assignments.items()):
        by_theme[a.theme].append(rid)
    return {
        "run_id": run_id,
        "method": method,
        "themes": [
            t.model_dump() | {"count": len(by_theme[t.name]), "review_ids": by_theme[t.name]}
            for t in result.taxonomy
        ],
        "other": {"count": len(by_theme[OTHER]), "review_ids": by_theme[OTHER]},
        "low_confidence_ids": sorted(
            rid for rid, a in result.assignments.items() if a.confidence == "low"
        ),
        "capped_into_other": result.capped,
    }


def from_json(data: dict) -> ThemeResult:
    low = set(data.get("low_confidence_ids", []))
    assignments = {}
    for entry in data["themes"] + [{"name": OTHER, **data["other"]}]:
        for rid in entry["review_ids"]:
            conf = "low" if rid in low else "high"
            assignments[rid] = Assignment(theme=entry["name"], confidence=conf)
    taxonomy = [
        Theme(name=t["name"], definition=t["definition"], includes=t["includes"])
        for t in data["themes"]
    ]
    return ThemeResult(
        taxonomy=taxonomy, assignments=assignments, capped=data.get("capped_into_other", [])
    )


# --- diagnostics -------------------------------------------------------------------------

# Coarse keyword buckets: an independent cross-check of the clustering, not a gate (plan task 6).
KEYWORD_BUCKETS = {
    "charges": r"brokerage|brokrage|charges?|fees?|dp charge|hidden|costly|expensive|\bamc\b",
    "support": r"customer (care|support|service)|support|no response|nobody|ticket|complain"
    r"|helpdesk|\bchat\b",
    "kyc": r"\bkyc\b|account opening|verification|aadhaar|\bpan\b|sign ?up|onboard|nominee",
    "money": r"withdraw|payment|\bupi\b|add money|deposit|refund|settle|payout|margin|balance",
    "performance": r"crash|\blag|slow|hang|glitch|bug|error|not working|server|loading|freez"
    r"|login|otp",
    "trading": r"f&o|option|chart|order|scalper|stop ?loss|target|intraday|trad(e|ing)|\bmtf\b",
    "ease": r"easy|simple|user.friendly|interface|\bui\b|smooth|beginner",
    "funds": r"\bsip\b|mutual fund|\bmf\b|\bnfo\b|\bipo\b|returns?|gold|\betf\b",
}


def keyword_agreement(result: ThemeResult, reviews: list[CleanReview]) -> dict[str, dict]:
    """Per theme: its most common keyword bucket and the share of its reviews that hit it."""
    text = {r.id: r.text for r in reviews}
    report: dict[str, dict] = {}
    for theme in [t.name for t in result.taxonomy] + [OTHER]:
        ids = [rid for rid, a in result.assignments.items() if a.theme == theme]
        hits = Counter()
        for rid in ids:
            for bucket, pattern in KEYWORD_BUCKETS.items():
                if re.search(pattern, text[rid], re.I):
                    hits[bucket] += 1
        if ids and hits:
            bucket, n = hits.most_common(1)[0]
            report[theme] = {"top_bucket": bucket, "agreement": round(n / len(ids), 3)}
        else:
            report[theme] = {"top_bucket": None, "agreement": 0.0}
    return report


def theme_stats(result: ThemeResult, reviews: list[CleanReview], cfg: Config) -> dict:
    total = len(reviews)
    counts = Counter(a.theme for a in result.assignments.values())
    low = sum(a.confidence == "low" for a in result.assignments.values())
    shares = {t.name: round(counts[t.name] / total, 3) for t in result.taxonomy}
    other_share = round(counts[OTHER] / total, 3)
    return {
        "reviews": total,
        "themes": len(result.taxonomy),
        "counts": {t.name: counts[t.name] for t in result.taxonomy} | {OTHER: counts[OTHER]},
        "shares": shares | {OTHER: other_share},
        "low_confidence_share": round(low / total, 3),
        "capped_into_other": result.capped,
        "checks": {
            "max_themes": len(result.taxonomy) <= cfg.themes.max,
            "all_assigned": len(result.assignments) == total,
            "other_share_ok": other_share <= cfg.themes.max_other_share,
            "min_theme_share_ok": all(s >= cfg.themes.min_theme_share for s in shares.values()),
        },
        "keyword_agreement": keyword_agreement(result, reviews),
    }
