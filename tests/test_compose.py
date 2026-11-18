import json
import re
from datetime import date

import pytest
from pydantic import BaseModel

from pulse import cli, pipeline
from pulse.compose import (
    SECTIONS,
    ComposeError,
    ThemeCopy,
    compose,
    date_range,
    render,
    word_budget,
)
from pulse.config import load_config
from pulse.llm import LlmError
from pulse.select import Quote, Selection, ThemeScore, TopTheme
from pulse.textfilter import word_count
from pulse.themes import to_json
from tests.test_select import CORPUS, FakeRanker, corpus, review

CFG = load_config()
RUN = "2026-W44"


def top(i: int, name: str, share: float) -> TopTheme:
    return TopTheme(
        name=name,
        count=10 * i,
        share=share,
        severity=0.5,
        avg_rating=2.5,
        score=1.0 - i / 10,
        definition=f"{name} definition.",
        includes="things",
        grounding_ids=[f"{i:064x}"],
    )


def quote(i: int, text: str, rating: int, **kw) -> Quote:
    return Quote(theme=f"T{i}", review_id=f"{i:064x}", rating=rating, store="play", text=text, **kw)


def selection() -> Selection:
    tops = [top(1, "Trading And F&O", 0.312), top(2, "App Performance", 0.205)]
    tops.append(top(3, "Customer Support", 0.149))
    return Selection(
        run_id=RUN,
        total_reviews=1596,
        avg_rating=2.94,
        ranking=[ThemeScore(**t.model_dump(include=set(ThemeScore.model_fields))) for t in tops],
        top=tops,
        quotes=[
            quote(1, "Stop loss did not trigger and I lost money.", 1, cut_end=True),
            quote(2, "App hangs every morning at market open.", 2),
            quote(3, "Support resolved my issue quickly, thanks.", 5, cut_start=True),
        ],
    )


class FakeWriter:
    """Returns scripted copy per attempt; the last script repeats."""

    def __init__(self, *scripts):
        self.scripts = scripts or (
            [("Reviewers report orders failing at open.", "Audit order routing at open.")] * 3,
        )
        self.prompts: list[str] = []
        self.feedback: list[list[str]] = []

    def structured(self, *, system, prompt, schema: type[BaseModel], effort, validate=None):
        self.prompts.append(prompt)
        for attempt in range(3):
            script = self.scripts[min(attempt, len(self.scripts) - 1)]
            out = schema.model_validate(
                {"themes": [{"summary": s, "action": a} for s, a in script]}
            )
            errors = validate(out) if validate else []
            if not errors:
                return out
            self.feedback.append(errors)
        raise LlmError(f"invalid after retries: {errors}", out)


def reviews_for(sel: Selection):
    return [review(i, f"grounding review {i} text") for i in range(1, len(sel.top) + 1)]


def test_template_assembly_puts_code_facts_and_verbatim_quotes_in_order():
    sel = selection()
    pulse = compose(FakeWriter(), sel, reviews_for(sel), CFG)
    lines = pulse.splitlines()
    assert lines[0] == "# Groww Weekly Review Pulse — 26 Oct – 1 Nov 2026"
    assert lines[2] == "1,596 reviews · 10 Aug – 1 Nov 2026 · avg rating 2.9 · Play Store"
    headings = [line[3:] for line in lines if line.startswith("## ")]
    assert headings == list(SECTIONS)
    assert "1. Trading And F&O (31%) — Reviewers report orders failing at open." in lines
    assert "3. Customer Support: Audit order routing at open." in lines
    # quotes inserted unchanged, ellipsis outside the verbatim span
    assert "- “Stop loss did not trigger and I lost money. …” — 1★, Play Store" in lines
    assert "- “…Support resolved my issue quickly, thanks.” — 5★, Play Store" in lines
    for q in sel.quotes:
        assert f"{q.text}" in pulse
    assert word_count(pulse) <= CFG.note.max_words


def test_prompt_carries_budget_quotes_and_grounding_but_not_ids():
    sel = selection()
    writer = FakeWriter()
    compose(writer, sel, reviews_for(sel), CFG)
    prompt = writer.prompts[0]
    summary, action = word_budget(sel, CFG)
    assert f"at most {summary} words" in prompt and f"at most {action} words" in prompt
    assert "grounding review 1 text" in prompt and sel.quotes[0].text in prompt
    assert sel.quotes[0].review_id not in prompt


def test_over_length_copy_is_retried_with_the_word_count():
    long = ("word " * 60).strip() + "."
    writer = FakeWriter([(long, long)] * 3, [("Short summary.", "Short action.")] * 3)
    pulse = compose(writer, selection(), reviews_for(selection()), CFG)
    assert any(re.search(r"the note is \d+ words; the limit is 250", e) for e in writer.feedback[0])
    assert word_count(pulse) <= 250


@pytest.mark.parametrize(
    "bad, error",
    [
        ("Reviewers say 40% of orders fail.", "number or percentage"),
        ("Over 200 users report failures.", "number or percentage"),
        ("Reviewers say “it never works”.", "quotation marks"),
        ("", "is empty"),
    ],
)
def test_invented_stats_quotes_and_empty_copy_are_rejected(bad, error):
    good = ("Reviewers report slow orders.", "Profile the order screen.")
    writer = FakeWriter([(bad, good[1]), good, good], [good] * 3)
    compose(writer, selection(), reviews_for(selection()), CFG)
    assert any(error in e for e in writer.feedback[0])


def test_wrong_number_of_entries_is_rejected_then_aborts():
    writer = FakeWriter([("Summary.", "Action.")] * 2)
    with pytest.raises(LlmError):
        compose(writer, selection(), reviews_for(selection()), CFG)
    assert "exactly 3 entries" in writer.feedback[0][0]


def test_quotes_too_long_for_the_budget_abort():
    sel = selection()
    sel.quotes[0].text = "very long quote " * 60
    with pytest.raises(ComposeError, match="quotes are too long"):
        word_budget(sel, CFG)


def test_date_range_labels():
    assert date_range(date(2026, 11, 2), date(2026, 11, 8)) == "2–8 Nov 2026"
    assert date_range(date(2026, 10, 26), date(2026, 11, 1)) == "26 Oct – 1 Nov 2026"
    assert date_range(date(2025, 12, 29), date(2026, 1, 4)) == "29 Dec 2025 – 4 Jan 2026"


def test_render_is_deterministic():
    sel = selection()
    copy = [ThemeCopy(summary="S.", action="A.")] * 3
    assert render(sel, copy, CFG) == render(sel, copy, CFG)


# --- stages and the dry run --------------------------------------------------------------


class FakeLlm:
    """Routes by schema: the select ranker and the compose writer."""

    def __init__(self):
        self.ranker, self.writer = FakeRanker(), FakeWriter()

    def structured(self, *, schema, **kw):
        target = self.ranker if schema.__name__ == "Ranked" else self.writer
        return target.structured(schema=schema, **kw)


def seed_run(tmp_path):
    reviews, result = corpus()
    rdir = tmp_path / RUN
    rdir.mkdir(parents=True)
    pipeline.write_jsonl(rdir / pipeline.CLEAN_FILE, reviews)
    (rdir / pipeline.THEMES_FILE).write_text(json.dumps(to_json(result, RUN, "m")))
    return reviews


def test_select_and_compose_stages_write_their_files(tmp_path):
    seed_run(tmp_path)
    llm = FakeLlm()
    sel_path = pipeline.stage_select(CFG, RUN, tmp_path, llm)
    sel = Selection.model_validate_json(sel_path.read_text())
    assert len(sel.top) == 3 and len(sel.quotes) == 3
    out = pipeline.stage_compose(CFG, RUN, tmp_path, llm)
    assert out.name == "pulse.md" and all(q.text in out.read_text() for q in sel.quotes)


def test_stage_without_input_fails_with_select_error(tmp_path):
    with pytest.raises(pipeline.SelectError, match="theme stage first"):
        pipeline.stage_select(CFG, RUN, tmp_path, FakeLlm())
    with pytest.raises(pipeline.SelectError, match="select stage first"):
        pipeline.stage_compose(CFG, RUN, tmp_path, FakeLlm())


def test_dry_run_prints_the_pulse_and_publishes_nothing(tmp_path, monkeypatch, capsys):
    seed_run(tmp_path)
    monkeypatch.setattr(pipeline, "DATA_DIR", tmp_path)
    monkeypatch.setattr(pipeline, "new_llm", lambda cfg: FakeLlm())
    code = cli.main(["run", "--dry-run", "--week", RUN, "--from", "select"])
    out, err = capsys.readouterr()
    assert code == 0
    assert out.startswith("# Groww Weekly Review Pulse")
    assert "nothing published" in err
    assert any(text in out for texts in CORPUS.values() for text in texts)


def test_dry_run_missing_inputs_exits_with_select_code(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "DATA_DIR", tmp_path)
    assert cli.main(["run", "--dry-run", "--week", RUN, "--from", "select"]) == cli.EXIT_SELECT
