"""Stage orchestration and run directory handling.

Each stage reads and writes files in `data/<run_id>/`, with `run_id` the ISO week `YYYY-Www`.
"""

import asyncio
import hashlib
import json
import logging
import re
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from pulse import mcp_gateway
from pulse.compose import ComposeError, compose
from pulse.config import Config
from pulse.ingest.base import IngestError, ReviewSource
from pulse.ingest.play_store import PlayStoreSource
from pulse.llm import Llm, LlmError, new_llm
from pulse.mcp_gateway import PublishError
from pulse.models import IST, CleanReview, RawReview, Review, run_id_for, window_for
from pulse.normalize import normalize
from pulse.pii import detect
from pulse.scrub import scrub_reviews
from pulse.select import SelectError, Selection, select
from pulse.themes import Theme, build_themes, from_json, theme_stats, to_json
from pulse.validate import ValidateError, validate

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"

RAW_FILE = "raw_reviews.jsonl"
REVIEWS_FILE = "reviews.jsonl"
NORMALIZE_STATS_FILE = "normalize_stats.json"
CLEAN_FILE = "reviews_clean.jsonl"
SCRUB_STATS_FILE = "scrub_stats.json"
THEMES_FILE = "themes.json"
THEMES_STATS_FILE = "themes_stats.json"
SELECTION_FILE = "selection.json"
PULSE_FILE = "pulse.md"
VALIDATION_FILE = "validation.json"
PUBLISH_FILE = "publish_result.json"

DONE, UNKNOWN, SKIPPED = "done", "unknown", "skipped"  # publish step statuses


def current_run_id() -> str:
    return run_id_for(datetime.now(IST).date())


def run_dir(run_id: str, data_dir: Path = DATA_DIR) -> Path:
    path = data_dir / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_jsonl(path: Path, rows: Iterable[BaseModel]) -> int:
    n = 0
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(row.model_dump_json() + "\n")
                n += 1
    except BaseException:
        tmp.unlink(missing_ok=True)  # a partial fetch never lands on disk
        raise
    tmp.replace(path)
    return n


def read_jsonl[T: BaseModel](path: Path, model: type[T]) -> list[T]:
    with path.open(encoding="utf-8") as f:
        return [model.model_validate_json(line) for line in f if line.strip()]


def default_source(cfg: Config) -> ReviewSource:
    return PlayStoreSource(cfg.app.play_package, cfg.app.play_locale, cfg.ingest)


def stage_ingest(
    cfg: Config, run_id: str, data_dir: Path = DATA_DIR, source: ReviewSource | None = None
) -> Path:
    """Fetch raw reviews. The raw file holds reviewer names; Phase 2 deletes it after scrub."""
    source = source or default_source(cfg)
    window = window_for(run_id, cfg.window_weeks)
    out = run_dir(run_id, data_dir) / RAW_FILE
    try:
        n = write_jsonl(out, source.fetch(window))
    except IngestError:
        out.unlink(missing_ok=True)
        raise
    if n == 0:
        out.unlink(missing_ok=True)
        raise IngestError(
            f"{source.store}: no reviews in window {window.start:%F}..{window.end:%F}"
        )
    log.info("ingest: %d raw reviews for %s", n, run_id)
    return out


def stage_normalize(cfg: Config, run_id: str, data_dir: Path = DATA_DIR) -> Path:
    rdir = run_dir(run_id, data_dir)
    raw_path = rdir / RAW_FILE
    if not raw_path.exists():
        raise IngestError(f"{raw_path} missing; run the ingest stage first")
    window = window_for(run_id, cfg.window_weeks)
    reviews, stats = normalize(read_jsonl(raw_path, RawReview), window, cfg.min_review_chars)
    out = rdir / REVIEWS_FILE
    write_jsonl(out, reviews)
    summary = {
        "run_id": run_id,
        "window": {"start": window.start.isoformat(), "end": window.end.isoformat()},
        "counts": dict(sorted(stats.items())),
        "rating_counts": _rating_counts(reviews),
    }
    (rdir / NORMALIZE_STATS_FILE).write_text(json.dumps(summary, indent=2) + "\n")
    log.info("normalize: %s", dict(stats))
    return out


def _rating_counts(reviews: list[Review]) -> dict[str, int]:
    counts = {str(i): 0 for i in range(1, 6)}
    for r in reviews:
        counts[str(r.rating)] += 1
    return counts


def stage_scrub(cfg: Config, run_id: str, data_dir: Path = DATA_DIR) -> Path:
    """Filter and redact reviews, verify the result is PII-free, then delete the raw file."""
    rdir = run_dir(run_id, data_dir)
    in_path = rdir / REVIEWS_FILE
    if not in_path.exists():
        raise IngestError(f"{in_path} missing; run the normalize stage first")
    clean, stats = scrub_reviews(read_jsonl(in_path, Review), cfg.scrub)
    out = rdir / CLEAN_FILE
    write_jsonl(out, clean)
    (rdir / SCRUB_STATS_FILE).write_text(
        json.dumps({"run_id": run_id, "counts": dict(sorted(stats.items()))}, indent=2) + "\n"
    )
    (rdir / RAW_FILE).unlink(missing_ok=True)
    log.info("scrub: %s", dict(stats))
    return out


def previous_taxonomy(run_id: str, data_dir: Path = DATA_DIR) -> list[Theme] | None:
    """The latest earlier run's themes, whose names are reused so they stay stable."""
    earlier = sorted(p for p in data_dir.glob(f"*/{THEMES_FILE}") if p.parent.name < run_id)
    if not earlier:
        return None
    return from_json(json.loads(earlier[-1].read_text())).taxonomy


def stage_theme(cfg: Config, run_id: str, data_dir: Path = DATA_DIR) -> Path:
    """Cluster the clean reviews into at most `themes.max` themes with TF-IDF and NMF. No LLM."""
    rdir = run_dir(run_id, data_dir)
    in_path = rdir / CLEAN_FILE
    if not in_path.exists():
        raise IngestError(f"{in_path} missing; run the scrub stage first")
    reviews = read_jsonl(in_path, CleanReview)
    if len(reviews) < cfg.min_reviews:
        raise IngestError(f"only {len(reviews)} clean reviews; need {cfg.min_reviews}")
    previous = previous_taxonomy(run_id, data_dir)
    result, diagnostics = build_themes(reviews, cfg, previous)

    out = rdir / THEMES_FILE
    out.write_text(json.dumps(to_json(result, run_id), indent=2) + "\n")
    stats = theme_stats(result, reviews, cfg) | {
        "names_seeded_from_previous_run": previous is not None,
        "clustering": diagnostics,
    }
    (rdir / THEMES_STATS_FILE).write_text(json.dumps(stats, indent=2) + "\n")
    log.info("theme: %s", stats["counts"])
    for name, ok in stats["checks"].items():
        if not ok:
            log.warning("theme: exit check %s failed", name)
    return out


def stage_select(
    cfg: Config, run_id: str, data_dir: Path = DATA_DIR, llm: Llm | None = None
) -> Path:
    rdir = run_dir(run_id, data_dir)
    themes_path = rdir / THEMES_FILE
    if not themes_path.exists():
        raise SelectError(f"{themes_path} missing; run the theme stage first")
    result = from_json(json.loads(themes_path.read_text()))
    reviews = read_jsonl(rdir / CLEAN_FILE, CleanReview)
    selection = select(llm or new_llm(cfg.llm), result, reviews, cfg, run_id)
    out = rdir / SELECTION_FILE
    out.write_text(selection.model_dump_json(indent=2) + "\n")
    log.info(
        "select: top %s, quotes from %s",
        [t.name for t in selection.top],
        [q.review_id[:12] for q in selection.quotes],
    )
    return out


def stage_compose(
    cfg: Config, run_id: str, data_dir: Path = DATA_DIR, llm: Llm | None = None
) -> Path:
    rdir = run_dir(run_id, data_dir)
    sel_path = rdir / SELECTION_FILE
    if not sel_path.exists():
        raise SelectError(f"{sel_path} missing; run the select stage first")
    selection = Selection.model_validate_json(sel_path.read_text())
    reviews = read_jsonl(rdir / CLEAN_FILE, CleanReview)
    out = rdir / PULSE_FILE
    out.write_text(compose(llm or new_llm(cfg.llm), selection, reviews, cfg))
    (rdir / VALIDATION_FILE).unlink(missing_ok=True)  # a new draft has not passed the gate yet
    return out


def stage_validate(
    cfg: Config, run_id: str, data_dir: Path = DATA_DIR, llm: Llm | None = None
) -> Path:
    """Gate `pulse.md`. On failure, re-compose with the error list up to the retry limit.

    Always writes `validation.json`. It records the hash of the text that was checked, so the
    publish stage can confirm it sends exactly that text (VAL-4). Raises after the last attempt
    fails (VAL-1); the error list holds no review text.
    """
    rdir = run_dir(run_id, data_dir)
    for name, stage in ((PULSE_FILE, "compose"), (THEMES_FILE, "theme"), (CLEAN_FILE, "scrub")):
        if not (rdir / name).exists():
            raise ValidateError(f"{rdir / name} missing; run the {stage} stage first")
    taxonomy = [t.name for t in from_json(json.loads((rdir / THEMES_FILE).read_text())).taxonomy]
    reviews = read_jsonl(rdir / CLEAN_FILE, CleanReview)
    pulse_path = rdir / PULSE_FILE

    attempts: list[dict] = []
    for attempt in range(1, cfg.note.compose_retries + 2):
        if attempt > 1:
            selection = Selection.model_validate_json((rdir / SELECTION_FILE).read_text())
            llm = llm or new_llm(cfg.llm)
            try:
                text = compose(llm, selection, reviews, cfg, feedback=attempts[-1]["errors"])
            except (ComposeError, LlmError) as exc:
                attempts.append(
                    {"attempt": attempt, "passed": False, "errors": [f"compose: {exc}"]}
                )
                break
            pulse_path.write_text(text)
        text = pulse_path.read_text()
        report = validate(text, taxonomy, reviews, cfg)
        attempts.append({"attempt": attempt, **report.to_json()})
        log.info(
            "validate: attempt %d %s, %d words, %d errors",
            attempt,
            "passed" if report.passed else "failed",
            report.word_count,
            len(report.flat()),
        )
        if report.passed:
            break

    last = attempts[-1]
    out = rdir / VALIDATION_FILE
    result = {
        "run_id": run_id,
        "passed": last["passed"],
        "pulse_sha256": hashlib.sha256(pulse_path.read_bytes()).hexdigest(),
        "attempts": attempts,
    }
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    if not last["passed"]:
        raise ValidateError(
            f"pulse failed the gate after {len(attempts)} attempts: {last['errors'][:5]}"
        )
    return out


def plain_text(pulse: str) -> str:
    """The pulse as the plain text the MCP tools take: Markdown heading marks removed."""
    return re.sub(r"(?m)^#{1,6} ", "", pulse)


def gated_pulse(rdir: Path) -> tuple[str, str]:
    """`pulse.md` and its hash, only when it is exactly the text that passed the gate (VAL-4)."""
    val_path = rdir / VALIDATION_FILE
    pulse_path = rdir / PULSE_FILE
    if not (val_path.exists() and pulse_path.exists()):
        raise PublishError(f"{val_path} missing; run the validate stage first", "NOT_VALIDATED")
    validation = json.loads(val_path.read_text())
    raw = pulse_path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if not validation.get("passed") or validation.get("pulse_sha256") != sha:
        raise PublishError(
            "pulse.md has not passed the validation gate as it is now; re-run validate",
            "NOT_VALIDATED",
        )
    return raw.decode("utf-8"), sha


def _now() -> str:
    return datetime.now(IST).isoformat(timespec="seconds")


def _write_result(out: Path, result: dict) -> None:
    out.write_text(json.dumps(result, indent=2) + "\n")


async def _step(result: dict, out: Path, step: str, call, key: str, **fields) -> str:
    """Await one MCP write and record its outcome at once, before anything else can fail."""
    try:
        value = await call
    except PublishError as exc:
        if exc.status_unknown:
            result[step] = {"status": UNKNOWN, "error": exc.code, "at": _now(), **fields}
            _write_result(out, result)
        raise
    result[step] = {"status": DONE, key: value, "at": _now(), **fields}
    _write_result(out, result)
    return value


async def _publish(cfg: Config, text: str, result: dict, out: Path, connect) -> None:
    need_doc = result.get("doc", {}).get("status") != DONE
    need_email = cfg.email.send and result.get("email", {}).get("status") != DONE
    if not (need_doc or need_email):
        return
    tools = cfg.mcp.tools
    async with connect(cfg.mcp) as gw:
        await gw.check_tools(*[tools.docs_append] * need_doc, *[tools.gmail_send] * need_email)
        if need_doc:
            await _step(
                result,
                out,
                "doc",
                gw.publish_doc(cfg.doc.document_id, text),
                "doc_url",
                document_id=cfg.doc.document_id,
            )
        if need_email:
            body = f"{text.rstrip()}\n\nFull pulse in Google Docs: {result['doc']['doc_url']}\n"
            subject = text.split("\n", 1)[0]
            await _step(
                result,
                out,
                "email",
                gw.send_email(cfg.email.to, subject, body),
                "message_id",
                to=cfg.email.to,
            )


def stage_publish(
    cfg: Config, run_id: str, data_dir: Path = DATA_DIR, connect: Callable | None = None
) -> Path:
    """Append the validated pulse to the standing Doc, then email it with the Doc link.

    The Doc comes first, so an email never points at a missing Doc (architecture.md §8).
    `publish_result.json` is written after each step: a re-run skips steps already done, and a
    step whose outcome is unknown (it may have gone through) is never repeated automatically.
    The MCP server has no draft tool, so the email is sent, and only when `email.send` is true.
    """
    rdir = run_dir(run_id, data_dir)
    pulse, sha = gated_pulse(rdir)
    if not cfg.doc.document_id:
        raise PublishError("doc.document_id is empty in config/pulse.yaml", "NO_DOCUMENT")
    text = plain_text(pulse)
    if found := detect(text):  # the exact text sent, not only the Markdown the gate checked
        raise PublishError(f"the PII detector matched {found} in the publish text", "PII")

    out = rdir / PUBLISH_FILE
    result = json.loads(out.read_text()) if out.exists() else {}
    if result.get("pulse_sha256", sha) != sha:
        raise PublishError(f"{run_id} was already published from a different pulse", "REPUBLISH")
    for step in ("doc", "email"):
        if result.get(step, {}).get("status") == UNKNOWN:
            raise PublishError(
                f"the last {step} step may have gone through; check it, then remove "
                f"`{step}` from {out} to retry",
                "STATUS_UNKNOWN",
            )
    result |= {"run_id": run_id, "pulse_sha256": sha}
    if not cfg.email.send and result.get("email", {}).get("status") != DONE:
        result["email"] = {"status": SKIPPED, "reason": "email.send is false"}
    _write_result(out, result)

    try:
        asyncio.run(_publish(cfg, text, result, out, connect or mcp_gateway.connect))
    except PublishError:
        raise
    except Exception as exc:
        raise mcp_gateway.as_publish_error(exc) from exc
    log.info("publish: doc %s, email %s", result["doc"]["status"], result["email"]["status"])
    return out


STAGES = {
    "ingest": stage_ingest,
    "normalize": stage_normalize,
    "scrub": stage_scrub,
    "theme": stage_theme,
    "select": stage_select,
    "compose": stage_compose,
    "validate": stage_validate,
    "publish": stage_publish,
}
