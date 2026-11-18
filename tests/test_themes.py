import json
import random

import numpy as np
import pytest

from pulse import pipeline
from pulse.config import load_config
from pulse.ingest.base import IngestError
from pulse.models import CleanReview
from pulse.themes import (
    OTHER,
    Theme,
    ThemeError,
    build_themes,
    describe,
    from_json,
    reuse_names,
    to_json,
)

CFG = load_config()

# Planted topics: each review draws from one topic's words, so the clusters are known.
TOPICS = {
    "charges": "brokerage charges fees hidden dp deducted expensive intraday",
    "support": "customer support ticket response chat executive callback resolved",
    "withdrawal": "withdrawal bank payout pending credited transfer upi refund",
    "charts": "chart candles indicator scalper option chain screen zoom",
    "kyc": "kyc verification aadhaar documents onboarding signature rejected nominee",
}
GENERIC = ["good app nice", "worst app ever", "very nice app thanks", "best app"]


def review(i: int, text: str, rating: int = 1) -> CleanReview:
    return CleanReview(
        id=f"{i:064x}",
        store="play",
        rating=rating,
        title=None,
        text=text,
        date="2026-10-01",
        app_version=None,
        lang="en",
    )


def corpus(per_topic: int = 30, topics=TOPICS, generic: int = 8, seed: int = 0):
    """Reviews with their planted topic (None for generic praise)."""
    rng = random.Random(seed)
    rows: list[tuple[CleanReview, str | None]] = []
    for topic, vocab in topics.items():
        words = vocab.split()
        for _ in range(per_topic):
            text = "the " + " ".join(rng.sample(words, 4)) + " is a problem"
            rows.append((review(len(rows), text, rating=1 + len(rows) % 5), topic))
    for j in range(generic):
        rows.append((review(len(rows), GENERIC[j % len(GENERIC)], rating=5), None))
    return rows


def cfg(**themes):
    return CFG.model_copy(update={"themes": CFG.themes.model_copy(update={"min_df": 2, **themes})})


def build(rows, config=None, previous=None):
    return build_themes([r for r, _ in rows], config or cfg(), previous)


def test_every_review_assigned_and_generic_praise_goes_to_other():
    rows = corpus()
    result, diag = build(rows)
    assert set(result.assignments) == {r.id for r, _ in rows}
    for r, topic in rows:
        if topic is None:
            assert result.assignments[r.id].theme == OTHER
    assert diag["no_topic_words"] == 8 and diag["method"] == "tfidf-nmf-bisect"


def test_planted_topics_are_recovered_one_theme_each():
    rows = corpus()
    result, _ = build(rows)
    assert len(result.taxonomy) == 5
    for topic in TOPICS:
        themes = {result.assignments[r.id].theme for r, t in rows if t == topic}
        assert len(themes) == 1 and OTHER not in themes, (topic, themes)
    assert len({result.assignments[r.id].theme for r, t in rows if t}) == 5


def test_themes_are_topics_not_sentiment():
    rows = corpus()  # ratings cycle 1..5 inside every topic
    result, _ = build(rows)
    for theme in result.taxonomy:
        ratings = {r.rating for r, _ in rows if result.assignments[r.id].theme == theme.name}
        assert ratings == {1, 2, 3, 4, 5}


def test_cap_folds_the_smallest_theme_into_other():
    topics = dict(list(TOPICS.items())[:4])
    rows = corpus(topics=topics)
    result, _ = build(rows, cfg(max=3))
    assert len(result.taxonomy) <= 3
    names = {result.assignments[r.id].theme for r, t in rows if t}
    assert names - {OTHER} == {t.name for t in result.taxonomy}


def test_oversized_topic_is_bisected():
    # One NMF topic must hold two planted topics when only 3 fit; the split separates them.
    topics = dict(list(TOPICS.items())[:4])
    rows = corpus(topics=topics)
    _, no_split = build(rows, cfg(max=3, max_splits=0))
    result, diag = build(rows, cfg(max=3, split_share=0.3))
    assert no_split["splits"] == 0 and diag["splits"] >= 1
    assert result.capped  # the split went over the cap, so the smallest theme was folded


def test_too_few_themes_or_no_vocabulary_aborts():
    with pytest.raises(ThemeError):
        build([(review(i, GENERIC[i % 4], 5), None) for i in range(60)])
    with pytest.raises(ThemeError, match="need at least 3"):
        two_topics = dict(list(TOPICS.items())[:2])
        build(corpus(per_topic=1, topics=two_topics, generic=60), cfg(min_df=1))


def test_result_does_not_depend_on_input_order():
    rows = corpus()
    shuffled = rows[:]
    random.Random(3).shuffle(shuffled)
    assert build(rows)[0] == build(shuffled)[0]


def test_confidence_marks_mixed_reviews_low():
    rows = corpus()
    mixed = review(999, "kyc verification bank payout chart", rating=1)  # three topics
    result, _ = build_themes([r for r, _ in rows] + [mixed], cfg())
    assert result.assignments[mixed.id].confidence == "low"
    pure = rows[0][0]
    assert result.assignments[pure.id].confidence == "high"


def test_describe_names_from_distinct_top_terms():
    vocab = np.array(["charges", "charge", "brokerage", "brokerage charges", "high", "dp", "fees"])
    weights = np.array([0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3])
    theme = describe(weights, vocab)
    assert theme.name == "Charges / Brokerage / DP"  # repeats and "high" are skipped
    assert theme.includes.startswith("charges, charge, brokerage")


def test_previous_names_reused_when_terms_overlap():
    new = [
        Theme(name="Charges / Brokerage / DP", definition="d", includes="charges, brokerage, dp"),
        Theme(name="Chart / Scalper", definition="d", includes="chart, scalper, indicator"),
    ]
    previous = [
        Theme(name="Charges And Fees", definition="old", includes="charges, brokerage, fees")
    ]
    out = reuse_names(new, previous)
    assert [t.name for t in out] == ["Charges And Fees", "Chart / Scalper"]
    assert out[0].includes == new[0].includes  # this run's terms are kept


def test_json_round_trip():
    result, _ = build(corpus())
    data = json.loads(json.dumps(to_json(result, "2026-W44")))
    assert data["method"] == "tfidf-nmf-bisect"
    assert from_json(data) == result


def write_clean(tmp_path, run_id, reviews):
    rdir = tmp_path / run_id
    rdir.mkdir(parents=True, exist_ok=True)
    pipeline.write_jsonl(rdir / "reviews_clean.jsonl", reviews)


def test_theme_stage_writes_files_and_reuses_previous_names(tmp_path):
    reviews = [r for r, _ in corpus()]
    write_clean(tmp_path, "2026-W43", reviews)
    pipeline.stage_theme(cfg(), "2026-W43", tmp_path)
    stats = json.loads((tmp_path / "2026-W43" / "themes_stats.json").read_text())
    assert stats["names_seeded_from_previous_run"] is False
    assert all(stats["checks"].values())
    assert stats["clustering"]["vocabulary"] > 0

    # rename last week's themes; this week's matching themes inherit the names
    themes_path = tmp_path / "2026-W43" / "themes.json"
    data = json.loads(themes_path.read_text())
    for i, t in enumerate(data["themes"]):
        t["name"] = f"Stable Theme {i}"
    themes_path.write_text(json.dumps(data))
    write_clean(tmp_path, "2026-W44", reviews)
    out = pipeline.stage_theme(cfg(), "2026-W44", tmp_path)
    data = json.loads(out.read_text())
    assert {t["name"] for t in data["themes"]} == {f"Stable Theme {i}" for i in range(5)}
    assert sum(t["count"] for t in data["themes"]) + data["other"]["count"] == len(reviews)
    text = out.read_text() + (tmp_path / "2026-W44" / "themes_stats.json").read_text()
    assert "is a problem" not in text  # no review text in theme artifacts


def test_theme_stage_needs_minimum_reviews(tmp_path):
    write_clean(tmp_path, "2026-W44", [r for r, _ in corpus(per_topic=2, generic=0)])
    with pytest.raises(IngestError, match="need 50"):
        pipeline.stage_theme(CFG, "2026-W44", tmp_path)
