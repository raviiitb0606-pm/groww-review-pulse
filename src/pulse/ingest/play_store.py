"""Play Store fetcher over the public listing, via google-play-scraper.

Reads only what the public store page serves (no login). Pages newest-first,
throttles between pages, retries with backoff, and stops at the window boundary.
"""

import logging
import time
from collections.abc import Callable, Iterator
from typing import Any

from pulse.config import Ingest
from pulse.ingest.base import IngestError
from pulse.models import IST, RawReview, Window

log = logging.getLogger(__name__)

REQUIRED_FIELDS = ("reviewId", "score", "content", "at")

# (continuation_token | None) -> (records, next_token)
FetchPage = Callable[[Any], tuple[list[dict], Any]]


def library_fetch_page(package: str, locale: str, page_size: int) -> FetchPage:
    from google_play_scraper import Sort, reviews

    lang, _, country = locale.partition("_")

    def fetch_page(token: Any) -> tuple[list[dict], Any]:
        if token is None:
            return reviews(
                package,
                lang=lang,
                country=country.lower() or "in",
                sort=Sort.NEWEST,
                count=page_size,
            )
        return reviews(package, continuation_token=token)

    return fetch_page


class PlayStoreSource:
    store = "play"

    def __init__(
        self,
        package: str,
        locale: str,
        settings: Ingest,
        fetch_page: FetchPage | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.settings = settings
        self.fetch_page = fetch_page or library_fetch_page(package, locale, settings.page_size)
        self.sleep = sleep

    def fetch(self, window: Window) -> Iterator[RawReview]:
        token = None
        old_streak = 0
        kept = skipped_new = 0
        for page in range(self.settings.max_pages):
            if page:
                self.sleep(self.settings.throttle_seconds)
            records, token = self._fetch_with_retry(token)
            for record in records:
                review = parse_record(record)
                at = review.at
                if at < window.start:
                    old_streak += 1
                    if old_streak >= self.settings.stop_after_old:
                        log.info(
                            "play: reached window start after %d pages, kept %d", page + 1, kept
                        )
                        return
                    continue
                old_streak = 0
                if at >= window.end:
                    skipped_new += 1
                    continue
                kept += 1
                yield review
            if not records or token is None or getattr(token, "token", "") is None:
                log.info("play: pages exhausted after %d pages, kept %d", page + 1, kept)
                return
        log.warning(
            "play: page cap %d hit before window start, kept %d", self.settings.max_pages, kept
        )

    def _fetch_with_retry(self, token: Any) -> tuple[list[dict], Any]:
        attempts = self.settings.max_retries + 1
        for attempt in range(attempts):
            try:
                return self.fetch_page(token)
            except Exception as exc:  # the library surfaces HTTP and parse errors untyped
                if attempt == attempts - 1:
                    raise IngestError(f"Play Store fetch failed after {attempts} attempts") from exc
                delay = 2.0 * 2**attempt
                log.warning("play: fetch error (%s), retrying in %.0fs", type(exc).__name__, delay)
                self.sleep(delay)
        raise AssertionError("unreachable")


def parse_record(record: dict) -> RawReview:
    missing = [f for f in REQUIRED_FIELDS if f not in record]
    if missing:
        raise IngestError(f"Play Store record missing fields: {', '.join(missing)}")
    # The library returns naive datetimes in host-local time; pin them to IST.
    at = record["at"].astimezone(IST)
    return RawReview(
        store="play",
        source_id=str(record["reviewId"]),
        user_name=record.get("userName"),
        rating=record["score"],
        text=record["content"],
        at=at,
        app_version=record.get("appVersion") or record.get("reviewCreatedVersion"),
    )
