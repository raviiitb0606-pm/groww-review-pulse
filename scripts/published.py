"""Exit 0 when a week's pulse is fully published (doc done, email done or skipped), else 1.

Used by scripts/weekly.sh: re-running a published week would compose a new pulse and fail the
REPUBLISH check, so the weekly job skips the pipeline and only refreshes the dashboard.
"""

import json
import sys

from pulse.pipeline import DATA_DIR, DONE, PUBLISH_FILE, SKIPPED


def published(run_id: str) -> bool:
    path = DATA_DIR / run_id / PUBLISH_FILE
    if not path.exists():
        return False
    result = json.loads(path.read_text())
    doc = result.get("doc", {}).get("status")
    email = result.get("email", {}).get("status")
    return doc == DONE and email in (DONE, SKIPPED)


if __name__ == "__main__":
    sys.exit(0 if published(sys.argv[1]) else 1)
