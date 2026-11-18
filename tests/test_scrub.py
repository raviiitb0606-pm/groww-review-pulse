import json

import pytest

from pulse import pipeline
from pulse.config import Scrub, load_config
from pulse.models import CleanReview, Review
from pulse.scrub import ScrubError, scrub_reviews
from pulse.textfilter import is_english, strip_emoji, word_count

CFG = Scrub()


def review(text: str, rid: str = "a", title: str | None = None) -> Review:
    return Review(
        id=rid,
        store="play",
        rating=3,
        title=title,
        text=text,
        date="2026-10-01",
        app_version=None,
        lang="en",
    )


NINE = "this app is really good for my investing needs"  # 9 words


def test_strip_emoji():
    assert strip_emoji("great app 💯🔥 love it ❤️ ✅ done") == "great app love it done"
    assert strip_emoji("lost ₹500 today") == "lost ₹500 today"


def test_word_count():
    assert word_count("can't log in") == 3


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (NINE, True),
        ("मेरा पैसा नहीं आया बहुत खराब ऐप है यह", False),
        ("app bahut accha hai lekin paisa nahi aata kabhi", False),
        ("esta aplicación es muy buena para invertir dinero", False),
        ("12345 67890", False),
    ],
)
def test_is_english(text, expected):
    assert is_english(text) is expected


def test_more_than_eight_words_kept_exactly_eight_dropped():
    eight = "this app is really good for my needs"
    assert word_count(eight) == 8
    out, stats = scrub_reviews([review(eight, "a"), review(NINE, "b")], CFG)
    assert [r.id for r in out] == ["b"]
    assert stats["dropped_short"] == 1


def test_emoji_removed_and_not_counted_as_words():
    out, _ = scrub_reviews([review(NINE + " 😀😀😀😀", "a")], CFG)
    assert out[0].text == NINE
    out, stats = scrub_reviews([review("good app 😀 " * 3, "a")], CFG)
    assert out == [] and stats["dropped_short"] == 1


def test_non_english_dropped_and_counted():
    out, stats = scrub_reviews([review("मेरा पैसा नहीं आया बहुत खराब ऐप है यह", "a")], CFG)
    assert out == [] and stats["dropped_non_english"] == 1


def test_english_filter_can_be_disabled():
    hindi = "मेरा पैसा नहीं आया बहुत खराब ऐप है यह"
    out, _ = scrub_reviews([review(hindi)], Scrub(english_only=False))
    assert len(out) == 1


def test_pii_redacted_and_heavy_redaction_not_quote_eligible():
    text = (
        "my number is 9876543210 and email is a@b.com, "
        "please call me back as soon as you can today or tomorrow"
    )
    out, _ = scrub_reviews([review(text)], CFG)
    assert "9876543210" not in out[0].text and "a@b.com" not in out[0].text
    assert out[0].quote_eligible is True

    heavy = "call 9876543210 9876543211 9876543212 9876543213 or mail a@b.com about this"
    out, stats = scrub_reviews([review(heavy)], CFG)
    assert out[0].quote_eligible is False and stats["quote_ineligible"] == 1


def test_title_is_scrubbed():
    out, _ = scrub_reviews([review(NINE, title="call 9876543210 now 😀")], CFG)
    assert out[0].title == "call [redacted] now"


def test_emoji_only_difference_deduped():
    out, stats = scrub_reviews([review(NINE, "a"), review(NINE + " 😀", "b")], CFG)
    assert len(out) == 1 and stats["dup_text"] == 1


def test_leak_after_scrub_raises(monkeypatch):
    monkeypatch.setattr("pulse.scrub.detect", lambda text: ["email"])
    with pytest.raises(ScrubError):
        scrub_reviews([review(NINE)], CFG)


def test_scrub_stage_writes_clean_file_and_deletes_raw(tmp_path):
    rdir = tmp_path / "2026-W44"
    rdir.mkdir()
    (rdir / "raw_reviews.jsonl").write_text('{"user_name": "Test User"}\n')
    pipeline.write_jsonl(
        rdir / "reviews.jsonl", [review(NINE + " 9876543210", "a"), review("short", "b")]
    )

    out = pipeline.stage_scrub(load_config(), "2026-W44", tmp_path)
    clean = pipeline.read_jsonl(out, CleanReview)
    assert [r.id for r in clean] == ["a"]
    assert "9876543210" not in out.read_text()
    assert not (rdir / "raw_reviews.jsonl").exists()
    stats = json.loads((rdir / "scrub_stats.json").read_text())
    assert stats["counts"]["kept"] == 1 and stats["counts"]["dropped_short"] == 1


def test_scrub_stage_keeps_raw_on_leak(tmp_path, monkeypatch):
    rdir = tmp_path / "2026-W44"
    rdir.mkdir()
    (rdir / "raw_reviews.jsonl").write_text("x\n")
    pipeline.write_jsonl(rdir / "reviews.jsonl", [review(NINE)])
    monkeypatch.setattr("pulse.scrub.detect", lambda text: ["email"])
    with pytest.raises(ScrubError):
        pipeline.stage_scrub(load_config(), "2026-W44", tmp_path)
    assert (rdir / "raw_reviews.jsonl").exists()
    assert not (rdir / "reviews_clean.jsonl").exists()
