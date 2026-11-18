import hashlib
import json

import pytest
from pydantic import BaseModel

from pulse import cli, pipeline
from pulse.compose import ThemeCopy, render
from pulse.config import load_config
from pulse.llm import LlmError
from pulse.textfilter import word_count
from pulse.validate import CHECKS, ValidateError, strip_ellipsis, validate
from tests.test_compose import FakeLlm, selection
from tests.test_compose import seed_run as seed_select_run
from tests.test_select import review

CFG = load_config()
RUN = "2026-W44"
TAXONOMY = ["Trading And F&O", "App Performance", "Customer Support", "Charges And Fees"]
GOOD = [
    ThemeCopy(
        summary="Reviewers report stop-loss orders not triggering.", action="Audit triggers."
    ),
    ThemeCopy(
        summary="Reviewers report freezes at market open.", action="Profile the home screen."
    ),
    ThemeCopy(summary="Reviewers praise quick chat replies.", action="Track first reply time."),
]


def corpus():
    """Clean reviews holding the selection's quotes, each inside longer text where it was cut."""
    return [
        review(1, "Stop loss did not trigger and I lost money. Fix it now please.", rating=1),
        review(2, "App hangs every morning at market open.", rating=2),
        review(3, "Long wait at first. Support resolved my issue quickly, thanks.", rating=5),
        review(4, "Charges are too high for small orders.", rating=2),
    ]


def pulse(copy=GOOD, sel=None) -> str:
    return render(sel or selection(), copy, CFG)


def failed(text: str, reviews=None) -> dict[str, list[str]]:
    report = validate(text, TAXONOMY, reviews or corpus(), CFG)
    return {check: errs for check, errs in report.errors.items() if errs}


def test_rendered_pulse_passes_every_check():
    report = validate(pulse(), TAXONOMY, corpus(), CFG)
    assert report.passed, report.flat()
    assert report.to_json()["checks"] == dict.fromkeys(CHECKS, True)


# --- one failing case per rule -----------------------------------------------------------


def test_length_over_the_cap_fails():
    long = ThemeCopy(summary="Reviewers report " + "slow " * 200 + "orders.", action="Fix it.")
    errors = failed(pulse([long, *GOOD[1:]]))
    assert list(errors) == ["length"]
    assert "the limit is 250" in errors["length"][0]


def test_length_counts_with_the_shared_counter():
    text = pulse()
    report = validate(text, TAXONOMY, corpus(), CFG)
    assert report.word_count == word_count(text)


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda t: t.replace("## Top themes\n", ""), "sections must be"),
        (
            lambda t: (
                t.replace("## What users said", "## TMP")
                .replace("## Action ideas", "## What users said")
                .replace("## TMP", "## Action ideas")
            ),
            "sections must be",
        ),
        (lambda t: t.split("\n", 1)[1], "Weekly Review Pulse"),
        (lambda t: t.replace("1. Trading And F&O:", "4. Trading And F&O:"), "numbered 4"),
    ],
    ids=["missing-section", "out-of-order", "no-title", "numbering"],
)
def test_structure_breaks_fail(mutate, message):
    errors = failed(mutate(pulse()))
    assert any(message in e for e in errors.get("structure", []) + errors.get("actions", []))


def test_empty_section_fails():
    text = pulse()
    errors = failed(text.split("## Action ideas\n")[0] + "## Action ideas\n")
    assert any("'Action ideas' is empty" in e for e in errors["structure"])


def test_wrong_number_of_themes_fails():
    text = pulse().replace("3. Customer Support (15%) — Reviewers praise quick chat replies.\n", "")
    errors = failed(text)
    assert any("exactly 3 themes, got 2" in e for e in errors["themes"])


@pytest.mark.parametrize("name", ["Made Up Theme", "other"])
def test_theme_outside_the_clustered_set_fails(name):
    sel = selection()
    sel.top[1].name = name
    errors = failed(pulse(sel=sel))
    assert any("not one of this run's themes" in e for e in errors["themes"])


def test_duplicate_theme_fails():
    sel = selection()
    sel.top[2].name = sel.top[0].name
    assert any("more than once" in e for e in failed(pulse(sel=sel))["themes"])


def test_paraphrased_quote_fails():
    sel = selection()
    sel.quotes[1].text = "App hangs every single morning at market open."
    errors = failed(pulse(sel=sel))
    assert errors["quotes"] == ["quote 2: not an exact substring of any cleaned review"]


def test_quote_with_the_wrong_rating_fails():
    sel = selection()
    sel.quotes[1].rating = 5
    assert any("rating or store" in e for e in failed(pulse(sel=sel))["quotes"])


def test_wrong_number_of_quotes_fails():
    text = pulse().replace("- “App hangs every morning at market open.” — 2★, Play Store\n", "")
    assert any("exactly 3 quotes, got 2" in e for e in failed(text)["quotes"])


def test_quote_error_messages_hold_no_review_text():
    sel = selection()
    sel.quotes[0].text = "Totally invented quote that nobody wrote."
    flat = validate(pulse(sel=sel), TAXONOMY, corpus(), CFG).flat()
    assert flat and not any("invented" in e for e in flat)


def test_strip_ellipsis_removes_only_the_cut_marks():
    assert strip_ellipsis("…middle part …") == "middle part"
    assert strip_ellipsis("ends cut…") == "ends cut"
    assert strip_ellipsis("whole quote.") == "whole quote."


def test_action_not_naming_a_listed_theme_fails():
    text = pulse().replace("2. App Performance: Profile", "2. Profile")
    assert failed(text)["actions"] == ["action 2: does not name one of the listed themes"]


def test_action_naming_an_unlisted_theme_fails():
    text = pulse().replace("2. App Performance: Profile", "2. Charges And Fees: Profile")
    assert any("action 2" in e for e in failed(text)["actions"])


def test_action_with_no_next_step_fails():
    text = pulse().replace("3. Customer Support: Track first reply time.", "3. Customer Support:")
    assert any("no next step" in e for e in failed(text)["actions"])


def test_wrong_number_of_actions_fails():
    text = pulse().replace("3. Customer Support: Track first reply time.\n", "")
    assert any("exactly 3 actions, got 2" in e for e in failed(text)["actions"])


@pytest.mark.parametrize(
    "leak, pattern",
    [
        ("Write to help.desk@example.com for refunds.", "email"),
        ("Reviewers list +91 98765 43210 as a support line.", "phone"),
        ("Reviewers mention PAN ABCDE1234F in complaints.", "pan"),
    ],
)
def test_pii_in_the_final_text_fails(leak, pattern):
    copy = [ThemeCopy(summary=leak, action="Audit triggers."), *GOOD[1:]]
    errors = failed(pulse(copy))
    assert any(pattern in e for e in errors["pii"])


def test_review_id_in_the_final_text_fails():
    copy = [ThemeCopy(summary=f"See {'ab' * 32}.", action="Audit triggers."), *GOOD[1:]]
    assert any("reviewer field" in e for e in failed(pulse(copy))["pii"])


# --- the stage: retry with feedback, then abort -----------------------------------------


class CallWriter:
    """Returns one script per compose call (the last repeats) and records the prompts."""

    def __init__(self, *scripts):
        self.scripts = scripts
        self.prompts: list[str] = []

    def structured(self, *, system, prompt, schema: type[BaseModel], effort, validate=None):
        script = self.scripts[min(len(self.prompts), len(self.scripts) - 1)]
        self.prompts.append(prompt)
        out = schema.model_validate({"themes": [c.model_dump() for c in script]})
        assert not (validate and validate(out)), validate(out)
        return out


def seed_run(tmp_path, text: str):
    sel = selection()
    rdir = tmp_path / RUN
    rdir.mkdir(parents=True)
    pipeline.write_jsonl(rdir / pipeline.CLEAN_FILE, corpus())
    themes = [{"name": n, "definition": "d", "includes": "i", "review_ids": []} for n in TAXONOMY]
    (rdir / pipeline.THEMES_FILE).write_text(
        json.dumps({"themes": themes, "other": {"review_ids": []}})
    )
    (rdir / pipeline.SELECTION_FILE).write_text(sel.model_dump_json())
    (rdir / pipeline.PULSE_FILE).write_text(text)
    return rdir


LEAKY = [ThemeCopy(summary="Mail help.desk@example.com now.", action="Audit triggers."), *GOOD[1:]]


def test_passing_pulse_writes_validation_with_its_hash(tmp_path):
    rdir = seed_run(tmp_path, pulse())
    out = pipeline.stage_validate(CFG, RUN, tmp_path, llm=None)  # no LLM needed on a pass
    result = json.loads(out.read_text())
    assert result["passed"] and len(result["attempts"]) == 1
    assert result["pulse_sha256"] == hashlib.sha256((rdir / "pulse.md").read_bytes()).hexdigest()


def test_failure_recomposes_with_the_error_list_then_passes(tmp_path):
    rdir = seed_run(tmp_path, pulse(LEAKY))
    writer = CallWriter(GOOD)
    pipeline.stage_validate(CFG, RUN, tmp_path, writer)
    result = json.loads((rdir / "validation.json").read_text())
    assert result["passed"] and [a["passed"] for a in result["attempts"]] == [False, True]
    assert "rejected by the publish checks" in writer.prompts[0]
    assert "pii: the PII detector matched: email" in writer.prompts[0]
    assert "help.desk" not in (rdir / "pulse.md").read_text()


def test_retry_limit_then_abort_writes_validation(tmp_path):
    rdir = seed_run(tmp_path, pulse(LEAKY))
    writer = CallWriter(LEAKY)
    with pytest.raises(ValidateError, match="after 3 attempts"):
        pipeline.stage_validate(CFG, RUN, tmp_path, writer)
    assert len(writer.prompts) == CFG.note.compose_retries
    result = json.loads((rdir / "validation.json").read_text())
    assert not result["passed"] and len(result["attempts"]) == 3
    assert result["attempts"][-1]["checks"]["pii"] is False


def test_compose_failure_during_retry_aborts(tmp_path):
    class Broken:
        def structured(self, **kw):
            raise LlmError("Composed: invalid after retries")

    rdir = seed_run(tmp_path, pulse(LEAKY))
    with pytest.raises(ValidateError):
        pipeline.stage_validate(CFG, RUN, tmp_path, Broken())
    attempts = json.loads((rdir / "validation.json").read_text())["attempts"]
    assert len(attempts) == 2 and attempts[1]["errors"][0].startswith("compose:")


def test_missing_pulse_fails_with_validate_error(tmp_path):
    with pytest.raises(ValidateError, match="compose stage first"):
        pipeline.stage_validate(CFG, RUN, tmp_path)


def test_recompose_clears_a_stale_validation_file(tmp_path):
    seed_select_run(tmp_path)
    llm = FakeLlm()
    pipeline.stage_select(CFG, RUN, tmp_path, llm)
    (tmp_path / RUN / "validation.json").write_text("{}")
    pipeline.stage_compose(CFG, RUN, tmp_path, llm)
    assert not (tmp_path / RUN / "validation.json").exists()


# --- CLI ---------------------------------------------------------------------------------


def test_exit_codes_are_distinct():
    codes = [getattr(cli, n) for n in dir(cli) if n.startswith("EXIT_")]
    assert len(codes) == len(set(codes)) and 0 not in codes and 1 not in codes
    assert {cli.EXIT_INGEST, cli.EXIT_VALIDATION, cli.EXIT_PUBLISH} <= set(codes)


def test_dry_run_failing_the_gate_exits_with_validation_code(tmp_path, monkeypatch, capsys):
    seed_run(tmp_path, pulse(LEAKY))
    monkeypatch.setattr(pipeline, "DATA_DIR", tmp_path)
    monkeypatch.setattr(pipeline, "new_llm", lambda cfg: CallWriter(LEAKY))
    code = cli.main(["run", "--dry-run", "--week", RUN, "--from", "validate"])
    out, err = capsys.readouterr()
    assert code == cli.EXIT_VALIDATION
    assert out == "" and "validation failed" in err
    assert (tmp_path / RUN / "validation.json").exists()
