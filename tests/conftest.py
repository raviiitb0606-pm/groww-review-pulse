import json
from datetime import datetime
from pathlib import Path

import pytest

from pulse.models import IST

FIXTURES = Path(__file__).parent / "fixtures"


def ist(*args: int) -> datetime:
    return datetime(*args, tzinfo=IST)


def record(rid: str, at: datetime, text: str = "A perfectly ordinary review text.", score=4):
    return {"reviewId": rid, "userName": f"user {rid}", "content": text, "score": score, "at": at}


@pytest.fixture
def play_page() -> list[dict]:
    """A recorded-shape Play Store page (synthetic content), with IST-aware datetimes."""
    rows = json.loads((FIXTURES / "play_page.json").read_text())
    for row in rows:
        row["at"] = datetime.fromisoformat(row["at"]).replace(tzinfo=IST)
    return rows
