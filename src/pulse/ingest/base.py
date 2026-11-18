"""Common interface for review sources."""

from collections.abc import Iterable
from typing import Protocol

from pulse.models import RawReview, Window


class IngestError(RuntimeError):
    """The fetch failed or returned nothing usable."""


class ReviewSource(Protocol):
    store: str

    def fetch(self, window: Window) -> Iterable[RawReview]:
        """Yield reviews in (or near) `window`. Later stages filter strictly."""
        ...
