"""Dashboard export: one JSON file the frontend reads (frontend/README.md).

It holds facts only: every clean review with its theme, the themes with display labels and
colours, the validated pulse, and the publish status. The frontend computes every KPI and chart
from these, so its week picker and filters need no server. Review text is the scrubbed text and
is checked again here; review ids are shortened; the email recipient is left out.
"""

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

from pulse.compose import SECTIONS, STORE_LABEL, quote_body
from pulse.config import Config
from pulse.models import IST, CleanReview, window_for
from pulse.pii import detect
from pulse.select import Selection
from pulse.themes import OTHER
from pulse.validate import ITEM, THEME_LINE, split_sections

PALETTE = ("#7C3AED", "#F97362", "#14B8A6", "#0EA5E9", "#F59E0B")  # for unmapped theme names
OTHER_KEY, OTHER_COLOR = "other", "#64748B"
ID_CHARS = 12


class DashboardError(Exception):
    pass


def theme_meta(themes_json: dict, cfg: Config) -> tuple[list[dict], dict[str, str]]:
    """Display entries for each theme plus `other`, and a map from theme name to key."""
    entries, keys = [], {}
    for i, t in enumerate(themes_json["themes"]):
        style = cfg.dashboard.themes.get(t["name"])
        key = f"t{i + 1}"
        keys[t["name"]] = key
        entries.append(
            {
                "key": key,
                "name": t["name"],
                "label": style.label if style else t["name"],
                "color": style.color if style else PALETTE[i % len(PALETTE)],
                "terms": [w.strip() for w in t["includes"].split(",") if w.strip()],
            }
        )
    keys[OTHER] = OTHER_KEY
    entries.append(
        {"key": OTHER_KEY, "name": OTHER, "label": "Other", "color": OTHER_COLOR, "terms": []}
    )
    return entries, keys


def pulse_entry(rdir: Path, keys: dict[str, str]) -> dict | None:
    """The pulse that passed the gate, split into themes, quotes and actions; else None."""
    paths = {n: rdir / n for n in ("pulse.md", "validation.json", "selection.json")}
    if not all(p.exists() for p in paths.values()):
        return None
    raw = paths["pulse.md"].read_bytes()
    validation = json.loads(paths["validation.json"].read_text())
    if not validation.get("passed") or validation.get("pulse_sha256") != (
        hashlib.sha256(raw).hexdigest()
    ):
        return None
    selection = Selection.model_validate_json(paths["selection.json"].read_text())
    head, sections, _ = split_sections(raw.decode("utf-8"))
    top = [t.name for t in selection.top]

    themes = []
    for line in sections.get(SECTIONS[0], []):
        if (item := ITEM.fullmatch(line)) and (m := THEME_LINE.fullmatch(item.group(2))):
            themes.append({"theme": keys.get(m["name"]), "summary": m["summary"]})
    actions = []
    for line in sections.get(SECTIONS[2], []):
        if item := ITEM.fullmatch(line):
            body = item.group(2)
            name = next((n for n in top if body.startswith(f"{n}: ")), None)
            text = body.removeprefix(f"{name}: ") if name else body
            actions.append({"theme": keys.get(name) if name else None, "text": text})
    quotes = [
        {"theme": keys.get(q.theme), "rating": q.rating, "text": quote_body(q)}
        for q in selection.quotes
    ]
    return {
        "title": head[0].removeprefix("# ") if head else "",
        "themes": themes,
        "quotes": quotes,
        "actions": actions,
    }


def publish_entry(rdir: Path) -> dict | None:
    path = rdir / "publish_result.json"
    if not path.exists():
        return None
    result = json.loads(path.read_text())
    doc, email = result.get("doc", {}), result.get("email", {})
    return {  # no recipient address: the dashboard does not need it
        "doc_url": doc.get("doc_url"),
        "doc_at": doc.get("at"),
        "email_status": email.get("status"),
        "email_at": email.get("at"),
    }


def build(cfg: Config, run_id: str, rdir: Path) -> dict:
    for name in ("reviews_clean.jsonl", "themes.json"):
        if not (rdir / name).exists():
            raise DashboardError(f"{rdir / name} missing; run the pipeline through `theme`")
    themes_json = json.loads((rdir / "themes.json").read_text())
    themes, keys = theme_meta(themes_json, cfg)
    assigned = {
        rid: keys[entry["name"]]
        for entry in themes_json["themes"] + [{"name": OTHER, **themes_json["other"]}]
        for rid in entry["review_ids"]
    }
    low = set(themes_json.get("low_confidence_ids", []))

    with (rdir / "reviews_clean.jsonl").open(encoding="utf-8") as f:
        reviews = [CleanReview.model_validate_json(line) for line in f if line.strip()]
    if leaks := [r.id[:ID_CHARS] for r in reviews if detect(r.text)]:
        raise DashboardError(f"PII detector matched {len(leaks)} reviews, e.g. {leaks[:3]}")
    rows = [
        {
            "id": r.id[:ID_CHARS],
            "date": r.date.isoformat(),
            "rating": r.rating,
            "version": r.app_version,
            "theme": assigned.get(r.id, OTHER_KEY),
            "confidence": "low" if r.id in low else "high",
            "quote_eligible": r.quote_eligible,
            "text": r.text,
        }
        for r in sorted(reviews, key=lambda r: (r.date, r.id), reverse=True)
    ]
    window = window_for(run_id, cfg.window_weeks)
    return {
        "app": cfg.app.name,
        "run_id": run_id,
        "store": STORE_LABEL["play"],
        "generated_at": datetime.now(IST).isoformat(timespec="seconds"),
        "window": {
            "start": window.start.date().isoformat(),
            "end": (window.end - timedelta(days=1)).date().isoformat(),
        },
        "themes": themes,
        "reviews": rows,
        "pulse": pulse_entry(rdir, keys),
        "publish": publish_entry(rdir),
    }
