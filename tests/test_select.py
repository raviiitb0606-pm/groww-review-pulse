import json
import re

import pytest
from pydantic import BaseModel

from pulse.config import Weights, load_config
from pulse.llm import LlmError
from pulse.models import CleanReview
from pulse.select import (
    Candidate,
    SelectError,
    choose,
    rank_themes,
    select,
    spans,
    theme_candidates,
)
from pulse.themes import OTHER, Assignment, Theme, ThemeResult

CFG = load_config()

THEMES = [
    Theme(name="Brokerage And Charges", definition="Fees and charges.", includes="brokerage, DP"),
    Theme(name="App Performance", definition="Crashes and lag.", includes="crash, slow, login"),
    Theme(name="Customer Support", definition="Help from support.", includes="chat, tickets"),
    Theme(name="Mutual Funds", definition="SIP and funds.", includes="sip, nav"),
]


def review(i: int, text: str, rating: int = 1, eligible: bool = True) -> CleanReview:
    return CleanReview(
        id=f"{i:064x}",
        store="play",
        rating=rating,
        title=None,
        text=text,
        date="2026-10-01",
        app_version=None,
        lang="en",
        quote_eligible=eligible,
    )


def result_for(assign: dict[str, str], themes=THEMES, low=()) -> ThemeResult:
    return ThemeResult(
        taxonomy=themes,
        assignments={
            rid: Assignment(theme=t, confidence="low" if rid in low else "high")
            for rid, t in assign.items()
        },
    )


# --- ranking -----------------------------------------------------------------------------


def test_rank_scales_volume_and_severity_to_the_largest_theme():
    # A: 4 reviews, 1 low-rated. B: 2 reviews, both low. C: 2 reviews, none low.
    plan = [("A", 1), ("A", 5), ("A", 5), ("A", 4), ("B", 1), ("B", 2), ("C", 5), ("C", 4)]
    reviews = [review(i, "x" * 30, rating) for i, (_, rating) in enumerate(plan)]
    reviews.append(review(99, "y" * 30, 1))
    themes = [Theme(name=n, definition="d", includes="i") for n in "ABC"]
    assign = {r.id: t for r, (t, _) in zip(reviews, plan, strict=False)} | {reviews[-1].id: OTHER}
    ranked = rank_themes(result_for(assign, themes), reviews, Weights(volume=0.6, severity=0.4))

    by = {t.name: t for t in ranked}
    assert by["A"].score == pytest.approx(0.6 * 1 + 0.4 * 0.25)  # 0.7
    assert by["B"].score == pytest.approx(0.6 * 0.5 + 0.4 * 1)  # 0.7
    assert by["C"].score == pytest.approx(0.6 * 0.5)
    assert by["A"].share == round(4 / 9, 4) and by["B"].severity == 1.0
    # A and B tie on score; SEL-1 breaks the tie on severity, so B ranks first
    assert [t.name for t in ranked] == ["B", "A", "C"]
    assert OTHER not in by


def test_rank_tie_on_everything_breaks_on_name():
    reviews = [review(i, "x" * 30, 1) for i in range(4)]
    themes = [Theme(name=n, definition="d", includes="i") for n in ("Zeta", "Alpha")]
    assign = {reviews[0].id: "Zeta", reviews[1].id: "Zeta", reviews[2].id: "Alpha"}
    assign[reviews[3].id] = "Alpha"
    ranked = rank_themes(result_for(assign, themes), reviews, Weights(volume=0.6, severity=0.4))
    assert [t.name for t in ranked] == ["Alpha", "Zeta"]


# --- spans -------------------------------------------------------------------------------


TEXTS = [
    "Brokerage charges are too high. The app is fine otherwise, but the DP charge hurts!",
    "Love the app, it is smooth; charts load fast. Withdrawals take two days though.",
    "worst app ever no response from support for a week and my money is stuck in the account",
    "Great for beginners.\nCharges are hidden and support never replies to tickets.",
]


@pytest.mark.parametrize("text", TEXTS)
def test_every_span_is_a_verbatim_substring_cut_at_a_boundary(text):
    for s, e in spans(text, 10, 200):
        span = text[s:e]
        assert span in text and span == span.strip()
        assert s == 0 or re.search(r"[.!?…]\s+$|\n\s*$", text[:s])  # starts a sentence
        assert e == len(text) or re.match(r"[,;:]\s|\s+|\n", text[e:]) or text[e - 1] in ".!?…"


def test_span_never_drops_a_following_contrast_or_negation():
    text = "Good app overall, but withdrawals fail every single time I try."
    assert "Good app overall" not in [text[s:e] for s, e in spans(text, 5, 200)]
    text = "The charts are great. Not the order screen, which freezes."
    assert "The charts are great." not in [text[s:e] for s, e in spans(text, 5, 200)]


def test_span_never_ends_on_a_dangling_connector():
    text = "It always shows a technical error screen. However, support says it is fine."
    assert all(not text[s:e].endswith("However") for s, e in spans(text, 5, 200))


def test_span_cut_at_the_start_never_opens_on_a_connector():
    text = "The app is great for delivery trades. But not for intraday orders at all."
    assert "But not for intraday orders at all." not in [text[s:e] for s, e in spans(text, 5, 200)]


def test_span_respects_length_bounds():
    text = "Short one. " + "A much longer sentence about brokerage charges that goes on. " * 2
    for s, e in spans(text, 20, 70):
        assert 20 <= e - s <= 70


def test_unpunctuated_review_has_only_the_whole_text():
    text = "worst app ever no response from support for a week"
    assert spans(text, 20, 200) == [(0, len(text))]
    assert spans(text, 20, 30) == []


# --- candidates --------------------------------------------------------------------------


def candidates_for(texts, theme=THEMES[0], **kw):
    reviews = [review(i, t, **kw) for i, t in enumerate(texts)]
    assign = {r.id: theme.name for r in reviews}
    return theme_candidates(theme, reviews, result_for(assign), CFG)


def test_candidates_skip_placeholders_markdown_quotes_profanity_and_ineligible():
    bad = [
        "Charges deducted from my [redacted] account without any notice.",
        "Brokerage is *way* too high for small trades on this app.",
        'They call it "zero brokerage" but charges are everywhere.',
        "Shit app with hidden charges on every single order.",
    ]
    assert candidates_for(bad) == []
    assert (
        candidates_for(["Brokerage charges are far too high for small orders."], eligible=False)
        == []
    )


def test_hinglish_is_never_quoted():
    assert candidates_for(["yaar brokerage charges kyu itne jyada hai, bilkul bekar app"]) == []


def test_candidate_prefers_the_on_theme_span_and_flags_competitors():
    text = (
        "I have used this app for two years now and it was fine for most of that time. "
        "Brokerage charges are much higher than Zerodha for intraday orders."
    )
    [c] = candidates_for([text])
    assert c.text == "Brokerage charges are much higher than Zerodha for intraday orders."
    assert c.cut_start and not c.cut_end and c.flags == ("zerodha",)
    assert c.text in text


def test_flagged_candidates_rank_after_unflagged():
    pool = candidates_for(
        [
            "Brokerage charges are a scam on every order I place.",
            "Brokerage charges are high on every order I place here.",
        ]
    )
    assert [bool(c.flags) for c in pool] == [False, True]


def test_relaxed_bounds_used_only_when_nothing_fits(caplog):
    long_text = "Brokerage charges " + "are really high and " * 12 + "unfair."  # > 200 chars
    assert len(long_text) > 200
    assert candidates_for([long_text]) == []  # 240 relaxed cap is still too short
    short = "Fees far too high."  # 18 chars: below 20, above the relaxed 12
    [c] = candidates_for([short])
    assert c.text == short


# --- choice ------------------------------------------------------------------------------


def cand(i: int, rating: int, text: str) -> Candidate:
    r = review(i, text, rating)
    return Candidate(r, 0, len(text), 1.0, ())


def test_choose_mixes_ratings_where_the_data_allows():
    t1 = [cand(1, 1, "charges are high on options")]
    t2 = [cand(2, 1, "app crashes at market open"), cand(3, 5, "app is fast and smooth now")]
    t3 = [cand(4, 1, "support never replies to me")]
    picks = choose([t1, t2, t3])
    assert [c.review.rating for c in picks] == [1, 5, 1]


def test_choose_keeps_best_when_every_option_shares_a_rating():
    texts = [
        "brokerage is far too high",
        "hidden dp fees on sell",
        "account charges every month",
        "app crashes at nine fifteen",
        "login otp never arrives",
        "charts freeze during trading",
        "support chat takes days",
        "ticket closed without fix",
        "nobody answers the helpline",
    ]
    pools = [[cand(i * 3 + j, 1, texts[i * 3 + j]) for j in range(3)] for i in range(3)]
    assert [c.review.id for c in choose(pools)] == [pools[i][0].review.id for i in range(3)]


def test_choose_skips_near_duplicates():
    same = "withdrawal stuck for three days no update"
    pools = [[cand(1, 1, same)], [cand(2, 2, same + " at all"), cand(3, 2, "the login otp fails")]]
    assert [c.review.id for c in choose(pools)][1] == pools[1][1].review.id


# --- select with a stubbed ranker --------------------------------------------------------


class FakeRanker:
    """Picks the first listed key of each theme; `hook` can corrupt the first answer."""

    def __init__(self, hook=None):
        self.hook = hook
        self.calls: list[str] = []
        self.feedback: list[list[str]] = []

    def structured(self, *, system, prompt, schema: type[BaseModel], effort, validate=None):
        self.calls.append(prompt)
        blocks = re.findall(r"Theme (\d+):.*?<reviews>\n(.*?)\n</reviews>", prompt, re.S)
        for attempt in range(3):
            picks = [
                {"theme": int(n), "keys": [json.loads(body.splitlines()[0])["key"]]}
                for n, body in blocks
            ]
            if self.hook and attempt == 0:
                picks = self.hook(picks)
            out = schema.model_validate({"picks": picks})
            errors = validate(out) if validate else []
            if not errors:
                return out
            self.feedback.append(errors)
        raise LlmError(f"invalid after retries: {errors}", out)


CORPUS = {
    "Brokerage And Charges": [
        "Brokerage charges are too high for small intraday orders.",
        "Hidden DP charges were deducted when I sold my shares.",
    ],
    "App Performance": [
        "The app crashes every morning right at market open.",
        "Login with OTP is slow and the app freezes often.",
    ],
    "Customer Support": [
        "Support chat never replies and tickets stay open for weeks.",
        "Customer care closed my ticket without solving anything.",
    ],
    "Mutual Funds": ["My SIP failed twice this month with no reason given."],
}


def corpus():
    reviews, assign = [], {}
    for theme, texts in CORPUS.items():
        for text in texts:
            r = review(len(reviews), text, rating=1 + len(reviews) % 3)
            reviews.append(r)
            assign[r.id] = theme
    return reviews, result_for(assign)


def test_select_returns_top_three_with_verbatim_quotes_and_no_ids_in_prompt():
    reviews, result = corpus()
    llm = FakeRanker()
    sel = select(llm, result, reviews, CFG, "2026-W44")
    assert [t.name for t in sel.top] == [t.name for t in sel.ranking[:3]]
    assert len(sel.quotes) == 3 and [q.theme for q in sel.quotes] == [t.name for t in sel.top]
    text = {r.id: r.text for r in reviews}
    assert all(q.text in text[q.review_id] for q in sel.quotes)
    assert reviews[0].id not in llm.calls[0]
    assert sel.total_reviews == len(reviews)


def test_select_skips_a_theme_with_nothing_quotable():
    reviews, result = corpus()
    # make every Brokerage review unquotable (SEL-2): the next-ranked theme takes its place
    reviews = [
        r.model_copy(update={"quote_eligible": False})
        if result.assignments[r.id].theme == "Brokerage And Charges"
        else r
        for r in reviews
    ]
    sel = select(FakeRanker(), result, reviews, CFG, "2026-W44")
    assert "Brokerage And Charges" not in [t.name for t in sel.top]
    assert len(sel.top) == 3


def test_select_aborts_with_fewer_than_three_quotable_themes():
    reviews, result = corpus()
    keep = {"App Performance", "Customer Support"}
    reviews = [
        r
        if result.assignments[r.id].theme in keep
        else r.model_copy(update={"quote_eligible": False})
        for r in reviews
    ]
    with pytest.raises(SelectError, match="only 2 themes"):
        select(FakeRanker(), result, reviews, CFG, "2026-W44")


@pytest.mark.parametrize(
    "hook",
    [
        lambda picks: picks[:2],  # a theme missing
        lambda picks: [p | {"keys": [999]} for p in picks],  # unknown key
        lambda picks: [picks[0] | {"keys": picks[1]["keys"]}] + picks[1:],  # wrong theme's key
        lambda picks: [p | {"keys": []} for p in picks],  # no keys
    ],
)
def test_bad_ranker_output_is_retried(hook):
    reviews, result = corpus()
    llm = FakeRanker(hook)
    sel = select(llm, result, reviews, CFG, "2026-W44")
    assert llm.feedback and len(sel.quotes) == 3
