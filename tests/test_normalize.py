from datetime import timedelta

from pulse.ingest.play_store import parse_record
from pulse.models import RawReview, Review, window_for
from pulse.normalize import clean_text, detect_lang, normalize, review_id
from tests.conftest import ist

WINDOW = window_for("2026-W44", 12)
IDENTITY_FIELDS = {"user_name", "userName", "userImage", "source_id", "reviewId"}


def raw(sid, at=None, text="The app keeps logging me out daily.", rating=3, **kw) -> RawReview:
    return RawReview(
        store="play",
        source_id=sid,
        user_name="Someone",
        rating=rating,
        text=text,
        at=at or ist(2026, 10, 1),
        **kw,
    )


def run(rows, min_chars=15):
    return normalize(rows, WINDOW, min_chars)


def test_maps_fixture_to_common_schema_without_identity(play_page):
    reviews, stats = run(parse_record(r) for r in play_page)
    assert len(reviews) == 2 and stats["dropped_short"] == 1  # "good"
    for r in reviews:
        dumped = r.model_dump()
        assert set(dumped) == set(Review.model_fields)
        assert not IDENTITY_FIELDS & set(dumped)
        assert "Test User" not in r.model_dump_json()
    assert reviews[0].id == review_id("play", "gp-001")
    assert reviews[0].date.isoformat() == "2026-10-31"


def test_id_is_a_store_prefixed_hash():
    rid = review_id("play", "gp-001")
    assert len(rid) == 64 and "gp-001" not in rid
    assert rid != review_id("app_store", "gp-001")


def test_window_boundary_inclusive_start_exclusive_end():
    rows = [
        raw("start", WINDOW.start, text="Review exactly at the window start."),
        raw("before", WINDOW.start - timedelta(seconds=1), text="One second before the window."),
        raw("last", WINDOW.end - timedelta(seconds=1), text="Last second inside the window."),
        raw("end", WINDOW.end, text="Exactly at the exclusive window end."),
    ]
    reviews, stats = run(rows)
    assert {r.id for r in reviews} == {review_id("play", "start"), review_id("play", "last")}
    assert stats["dropped_out_of_window"] == 2


def test_date_is_the_ist_calendar_day():
    from datetime import UTC

    # 20:00 UTC on Oct 20 is 01:30 IST on Oct 21.
    reviews, _ = run([raw("a", ist(2026, 10, 21, 1, 30).astimezone(UTC))])
    assert reviews[0].date.isoformat() == "2026-10-21"


def test_dedupe_same_id_keeps_latest_edit():
    rows = [
        raw("x", ist(2026, 10, 1), text="Original text of the review here."),
        raw("x", ist(2026, 10, 5), text="Edited text of the review, newer."),
        raw("x", ist(2026, 10, 3), text="A middle version that should lose."),
    ]
    reviews, stats = run(rows)
    assert [r.text for r in reviews] == ["Edited text of the review, newer."]
    assert stats["dup_id"] == 2


def test_dedupe_exact_text_across_reviewers():
    rows = [
        raw("a", ist(2026, 10, 2), text="Best app for investing in India!"),
        raw("b", ist(2026, 10, 1), text="best app for  investing in india!"),
        raw("c", ist(2026, 10, 3), text="A different review about charges."),
    ]
    reviews, stats = run(rows)
    assert len(reviews) == 2 and stats["dup_text"] == 1
    assert reviews[0].id == review_id("play", "c")  # newest first


def test_drops_short_empty_emoji_and_bad_ratings():
    rows = [
        raw("short", text="ok good"),
        raw("empty", text="   "),
        raw("none", text=None),
        raw("emoji", text="👍👍👍🔥🔥🔥💯💯💯💯"),
        raw("zero", rating=0),
        raw("six", rating=6),
        raw("none_rating", rating=None),
        raw("keep"),
    ]
    reviews, stats = run(rows)
    assert [r.id for r in reviews] == [review_id("play", "keep")]
    assert stats["dropped_short"] == 1
    assert stats["dropped_empty"] == 3
    assert stats["dropped_bad_rating"] == 3


def test_clean_text_nfc_and_zero_width():
    assert clean_text("café ​great‍  app\n") == "café great app"


def test_detect_lang():
    assert detect_lang("Withdrawal is slow") == "en"
    assert detect_lang("बहुत अच्छा ऐप है") == "und"
