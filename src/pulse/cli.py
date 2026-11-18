"""Entry point: run-stage, run (through MCP publish), and run --dry-run (no MCP calls)."""

import argparse
import json
import logging
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

from pulse import pipeline
from pulse.compose import ComposeError
from pulse.config import load_config
from pulse.dashboard import DashboardError, build
from pulse.ingest.base import IngestError
from pulse.llm import LlmError
from pulse.mcp_gateway import PublishError
from pulse.scrub import ScrubError
from pulse.select import SelectError, Selection
from pulse.textfilter import word_count
from pulse.themes import ThemeError
from pulse.validate import ValidateError

# One exit code per failure class, so a scheduler can alert on each (architecture.md §8).
EXIT_INGEST = 2
EXIT_SCRUB = 3
EXIT_THEME = 4
EXIT_SELECT = 5
EXIT_COMPOSE = 6
EXIT_VALIDATION = 7  # the pulse failed the gate; validation.json says why, nothing published
EXIT_PUBLISH = 8  # MCP publishing failed; publish_result.json records the steps done
EXIT_DASHBOARD = 9  # the dashboard export failed; nothing written
LLM_EXIT = {"select": EXIT_SELECT, "compose": EXIT_COMPOSE}
DRY_RUN_LAST = "validate"


def week_arg(value: str) -> str:
    if not re.fullmatch(r"\d{4}-W\d{2}", value):
        raise argparse.ArgumentTypeError("expected an ISO week like 2026-W44")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pulse")
    parser.add_argument("--config", help="path to pulse.yaml")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check-config", help="validate config/pulse.yaml")
    stage = sub.add_parser("run-stage", help="run one or more stages for a week")
    stage.add_argument("stages", nargs="+", choices=list(pipeline.STAGES))
    stage.add_argument("--week", type=week_arg, help="ISO week run id (default: current week)")
    dash = sub.add_parser("dashboard", help="export dashboard.json for the frontend")
    dash.add_argument("--week", type=week_arg, help="ISO week run id (default: current week)")
    dash.add_argument("--out", help="output path (default: dashboard.out in the config)")
    run = sub.add_parser("run", help="run the pipeline for a week")
    run.add_argument("--week", type=week_arg, help="ISO week run id (default: current week)")
    run.add_argument(
        "--dry-run", action="store_true", help="stop before publishing and print the pulse"
    )
    run.add_argument(
        "--from",
        dest="start",
        choices=list(pipeline.STAGES),
        default="ingest",
        help="first stage to run; earlier stages' files must exist (default: ingest)",
    )
    args = parser.parse_args(argv)
    load_dotenv()  # the LLM key and MCP_AUTH_TOKEN from .env, if present

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = load_config(*([Path(args.config)] if args.config else []))

    if args.command == "check-config":
        print(f"config ok: {cfg.app.name}, {cfg.window_weeks} week window")
        return 0

    run_id = args.week or pipeline.current_run_id()
    if args.command == "dashboard":
        return export_dashboard(cfg, run_id, args.out)
    if args.command == "run":
        names = list(pipeline.STAGES)
        last = names.index(DRY_RUN_LAST) if args.dry_run else len(names) - 1
        stages = names[names.index(args.start) : last + 1]
    else:
        stages = args.stages
    if code := run_stages(cfg, run_id, stages):
        return code
    if args.command == "run" and args.dry_run:
        print_pulse(run_id)
    elif "publish" in stages:
        print_published(run_id)
    return 0


def run_stages(cfg, run_id: str, stages: list[str]) -> int:
    name = stages[0] if stages else ""
    try:
        for name in stages:
            out = pipeline.STAGES[name](cfg, run_id, pipeline.DATA_DIR)
            print(f"{name}: wrote {out}", file=sys.stderr)
    except IngestError as exc:
        print(f"ingest failed: {exc}", file=sys.stderr)
        return EXIT_INGEST
    except ScrubError as exc:
        print(f"scrub failed: {exc}", file=sys.stderr)
        return EXIT_SCRUB
    except ThemeError as exc:
        print(f"theme failed: {exc}", file=sys.stderr)
        return EXIT_THEME
    except (SelectError, ComposeError) as exc:
        print(f"{name} failed: {exc}", file=sys.stderr)
        return EXIT_SELECT if isinstance(exc, SelectError) else EXIT_COMPOSE
    except ValidateError as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        return EXIT_VALIDATION
    except LlmError as exc:
        print(f"{name} failed: {exc}", file=sys.stderr)
        return LLM_EXIT.get(name, EXIT_COMPOSE)
    except PublishError as exc:
        print(f"publish failed: {exc}", file=sys.stderr)
        return EXIT_PUBLISH
    return 0


def print_pulse(run_id: str) -> None:
    """The dry run's output: the pulse on stdout, review notes on stderr. No MCP calls."""
    rdir = pipeline.DATA_DIR / run_id
    pulse = (rdir / pipeline.PULSE_FILE).read_text()
    print(pulse, end="")
    print(
        f"\n[dry run] {word_count(pulse)} words, passed validation; nothing published",
        file=sys.stderr,
    )
    selection = Selection.model_validate_json((rdir / pipeline.SELECTION_FILE).read_text())
    for i, q in enumerate(selection.quotes, 1):
        if q.flags:
            print(f"[review] quote {i} mentions: {', '.join(q.flags)}", file=sys.stderr)


def export_dashboard(cfg, run_id: str, out: str | None) -> int:
    try:
        data = build(cfg, run_id, pipeline.DATA_DIR / run_id)
    except DashboardError as exc:
        print(f"dashboard failed: {exc}", file=sys.stderr)
        return EXIT_DASHBOARD
    path = Path(out) if out else pipeline.ROOT / cfg.dashboard.out
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    print(f"dashboard: wrote {len(data['reviews'])} reviews to {path}", file=sys.stderr)
    return 0


def print_published(run_id: str) -> None:
    result = json.loads((pipeline.DATA_DIR / run_id / pipeline.PUBLISH_FILE).read_text())
    print(f"doc: {result['doc']['doc_url']}")
    email = result["email"]
    if email["status"] == pipeline.DONE:
        print(f"email: sent to {email['to']} (message {email['message_id']})")
    else:
        print(f"email: {email['status']} ({email.get('reason', '')})")


if __name__ == "__main__":
    raise SystemExit(main())
