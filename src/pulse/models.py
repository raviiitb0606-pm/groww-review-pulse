"""Typed schemas shared across stages."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

IST = ZoneInfo("Asia/Kolkata")


class Window(BaseModel):
    """Review date window in IST: start inclusive, end exclusive (ING-8)."""

    start: datetime
    end: datetime

    def contains(self, at: datetime) -> bool:
        return self.start <= at.astimezone(IST) < self.end


def run_id_for(day: date) -> str:
    """ISO week label `YYYY-Www` for the week containing `day`."""
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def window_for(run_id: str, weeks: int) -> Window:
    """`weeks` full ISO weeks ending with (and including) the run's week."""
    monday = date.fromisoformat(f"{run_id}-1")
    end = datetime.combine(monday + timedelta(weeks=1), datetime.min.time(), IST)
    return Window(start=end - timedelta(weeks=weeks), end=end)


class RawReview(BaseModel):
    """A store record as fetched. Holds reviewer identity: transient, never leaves the run dir."""

    model_config = ConfigDict(frozen=True)

    store: str
    source_id: str
    user_name: str | None = None
    rating: int | None
    title: str | None = None
    text: str | None
    at: datetime
    app_version: str | None = None


class Review(BaseModel):
    """Common schema (architecture.md §3.2). No reviewer identity fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    store: str
    rating: int = Field(ge=1, le=5)
    title: str | None
    text: str
    date: date
    app_version: str | None
    lang: str


class CleanReview(Review):
    """A scrubbed review. `quote_eligible` is false when redaction mangled too much of the text."""

    quote_eligible: bool = True
