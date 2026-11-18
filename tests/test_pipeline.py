import json

import pytest

from pulse import pipeline
from pulse.config import load_config
from pulse.ingest.base import IngestError
from pulse.ingest.play_store import parse_record
from pulse.models import Review, window_for
from tests.conftest import ist

RUN = "2026-W44"


class FakeSource:
    store = "play"

    def __init__(self, records):
        self.records = records

    def fetch(self, window):
        return (parse_record(r) for r in self.records)


def test_ingest_then_normalize_writes_run_dir(tmp_path, play_page):
    cfg = load_config()
    raw_path = pipeline.stage_ingest(cfg, RUN, tmp_path, FakeSource(play_page))
    assert raw_path == tmp_path / RUN / "raw_reviews.jsonl"

    out = pipeline.stage_normalize(cfg, RUN, tmp_path)
    reviews = pipeline.read_jsonl(out, Review)
    window = window_for(RUN, cfg.window_weeks)
    assert len(reviews) == 2
    assert all(window.start.date() <= r.date < window.end.date() for r in reviews)
    text = out.read_text()
    assert "Test User" not in text and "userName" not in text and "gp-00" not in text

    stats = json.loads((tmp_path / RUN / "normalize_stats.json").read_text())
    assert stats["counts"]["kept"] == 2 and stats["counts"]["dropped_short"] == 1


def test_ingest_with_zero_reviews_aborts(tmp_path):
    with pytest.raises(IngestError, match="no reviews"):
        pipeline.stage_ingest(load_config(), RUN, tmp_path, FakeSource([]))
    assert not (tmp_path / RUN / "raw_reviews.jsonl").exists()


def test_normalize_without_ingest_fails(tmp_path):
    with pytest.raises(IngestError, match="ingest stage first"):
        pipeline.stage_normalize(load_config(), RUN, tmp_path)


def test_failed_fetch_leaves_no_partial_raw_file(tmp_path):
    class Broken:
        store = "play"

        def fetch(self, window):
            yield parse_record(
                {"reviewId": "a", "content": "x" * 20, "score": 3, "at": ist(2026, 10, 1)}
            )
            raise IngestError("boom")

    with pytest.raises(IngestError):
        pipeline.stage_ingest(load_config(), RUN, tmp_path, Broken())
    assert list((tmp_path / RUN).iterdir()) == []
