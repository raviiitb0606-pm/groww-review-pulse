from datetime import date, timedelta

from pulse.models import run_id_for, window_for
from tests.conftest import ist


def test_run_id_is_iso_week():
    assert run_id_for(date(2026, 11, 1)) == "2026-W44"  # Sunday
    assert run_id_for(date(2026, 10, 26)) == "2026-W44"  # Monday
    assert run_id_for(date(2027, 1, 1)) == "2026-W53"  # year boundary (CMP-8)


def test_window_covers_full_weeks_ending_with_run_week():
    w = window_for("2026-W44", 12)
    assert w.end == ist(2026, 11, 2)
    assert w.start == ist(2026, 8, 10)
    assert w.end - w.start == timedelta(weeks=12)


def test_window_start_inclusive_end_exclusive():
    w = window_for("2026-W44", 8)
    assert w.contains(w.start)
    assert not w.contains(w.start - timedelta(microseconds=1))
    assert w.contains(w.end - timedelta(microseconds=1))
    assert not w.contains(w.end)


def test_window_compares_in_ist_regardless_of_input_timezone():
    from datetime import UTC

    w = window_for("2026-W44", 8)
    # 2026-11-01 19:00 UTC is 2026-11-02 00:30 IST: outside.
    assert not w.contains(ist(2026, 11, 2, 0, 30).astimezone(UTC))
    # 2026-11-01 18:00 UTC is 23:30 IST on Sunday: inside.
    assert w.contains(ist(2026, 11, 1, 23, 30).astimezone(UTC))
