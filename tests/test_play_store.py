from datetime import timedelta

import pytest

from pulse.config import Ingest
from pulse.ingest.base import IngestError
from pulse.ingest.play_store import PlayStoreSource, parse_record
from pulse.models import window_for
from tests.conftest import ist, record

WINDOW = window_for("2026-W44", 12)  # 2026-08-10 .. 2026-11-02 IST


class Token:
    def __init__(self, token):
        self.token = token


def pages_source(pages, settings=None, **kw):
    """Serve `pages` in order; the last page returns a token with no continuation."""
    calls = []

    def fetch_page(token):
        i = len(calls)
        calls.append(token)
        if i >= len(pages):
            return [], Token(None)
        return pages[i], Token(None if i == len(pages) - 1 else f"t{i}")

    settings = settings or Ingest(stop_after_old=3, throttle_seconds=0)
    source = PlayStoreSource("pkg", "en_IN", settings, fetch_page=fetch_page, sleep=lambda s: None)
    return source, calls


def test_parse_recorded_page(play_page):
    reviews = [parse_record(r) for r in play_page]
    assert [r.source_id for r in reviews] == ["gp-001", "gp-002", "gp-003"]
    first = reviews[0]
    assert first.rating == 1 and first.store == "play"
    assert first.app_version == "18.22.1"
    assert first.at == ist(2026, 10, 31, 11, 39, 24)
    assert reviews[1].app_version is None


def test_parse_fails_fast_on_shape_change(play_page):
    del play_page[0]["content"]
    with pytest.raises(IngestError, match="content"):
        parse_record(play_page[0])


def test_fetch_yields_only_in_window_and_stops_after_consecutive_old():
    inside = [record(f"in{i}", ist(2026, 10, 1) - timedelta(days=i)) for i in range(3)]
    old = [record(f"old{i}", ist(2026, 8, 1) - timedelta(days=i)) for i in range(5)]
    future = [record("future", ist(2026, 11, 5))]
    source, calls = pages_source(
        [future + inside[:2], inside[2:] + old, [record("never", ist(2026, 9, 1))]]
    )
    got = [r.source_id for r in source.fetch(WINDOW)]
    assert got == ["in0", "in1", "in2"]
    assert len(calls) == 2  # third page never requested


def test_fetch_tolerates_out_of_order_reviews():
    # Two stray old reviews, then in-window reviews again (ING-6).
    page = [
        record("a", ist(2026, 10, 1)),
        record("old1", ist(2026, 7, 1)),
        record("old2", ist(2026, 7, 2)),
        record("b", ist(2026, 9, 30)),
    ]
    source, _ = pages_source([page])
    assert [r.source_id for r in source.fetch(WINDOW)] == ["a", "b"]


def test_fetch_stops_when_pages_run_out():
    source, calls = pages_source([[record("a", ist(2026, 10, 1))]])
    assert [r.source_id for r in source.fetch(WINDOW)] == ["a"]
    assert len(calls) == 1


def test_fetch_respects_page_cap():
    pages = [[record(f"p{i}", ist(2026, 10, 1))] for i in range(10)]
    source, calls = pages_source(pages, Ingest(max_pages=4, throttle_seconds=0))
    assert len(list(source.fetch(WINDOW))) == 4
    assert len(calls) == 4


def test_fetch_retries_with_backoff_then_succeeds():
    sleeps = []
    attempts = {"n": 0}

    def flaky(token):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ConnectionError("429")
        return [record("a", ist(2026, 10, 1))], Token(None)

    source = PlayStoreSource(
        "pkg", "en_IN", Ingest(max_retries=4), fetch_page=flaky, sleep=sleeps.append
    )
    assert [r.source_id for r in source.fetch(WINDOW)] == ["a"]
    assert sleeps == [2.0, 4.0]


def test_fetch_gives_up_after_max_retries():
    def broken(token):
        raise TimeoutError

    source = PlayStoreSource(
        "pkg", "en_IN", Ingest(max_retries=2), fetch_page=broken, sleep=lambda s: None
    )
    with pytest.raises(IngestError, match="3 attempts"):
        list(source.fetch(WINDOW))
