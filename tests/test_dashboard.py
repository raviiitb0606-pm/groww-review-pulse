import json

import pytest

from pulse import cli, pipeline
from pulse.config import DashboardTheme
from pulse.dashboard import OTHER_KEY, PALETTE, DashboardError, build
from tests.test_publish import LIVE, FakeWorkspace
from tests.test_select import review
from tests.test_validate import CFG, GOOD, RUN, TAXONOMY, pulse, seed_run


def published_run(tmp_path):
    rdir = seed_run(tmp_path, pulse())
    pipeline.stage_validate(CFG, RUN, tmp_path)
    pipeline.stage_publish(LIVE, RUN, tmp_path, FakeWorkspace().connect)
    return rdir


def test_export_holds_reviews_themes_pulse_and_publish_status(tmp_path):
    rdir = published_run(tmp_path)
    cfg = CFG.model_copy(
        update={
            "dashboard": CFG.dashboard.model_copy(
                update={"themes": {TAXONOMY[0]: DashboardTheme(label="Trading", color="#0EA5E9")}}
            )
        }
    )
    data = build(cfg, RUN, rdir)

    assert [t["key"] for t in data["themes"]] == ["t1", "t2", "t3", "t4", OTHER_KEY]
    assert data["themes"][0] | {"terms": []} == {
        "key": "t1",
        "name": TAXONOMY[0],
        "label": "Trading",
        "color": "#0EA5E9",
        "terms": [],
    }
    assert data["themes"][1]["label"] == TAXONOMY[1] and data["themes"][1]["color"] == PALETTE[1]

    clean = pipeline.read_jsonl(rdir / pipeline.CLEAN_FILE, pipeline.CleanReview)
    assert len(data["reviews"]) == len(clean)
    assert all(len(r["id"]) == 12 for r in data["reviews"])
    assert data["reviews"] == sorted(data["reviews"], key=lambda r: r["date"], reverse=True)

    p = data["pulse"]
    assert [a["text"] for a in p["actions"]] == [c.action for c in GOOD]
    assert [t["summary"] for t in p["themes"]] == [c.summary for c in GOOD]
    assert all(a["theme"] in {"t1", "t2", "t3", "t4"} for a in p["actions"])
    assert len(p["quotes"]) == 3 and all(q["text"] in pulse() for q in p["quotes"])
    assert p["title"].startswith("Groww Weekly Review Pulse")

    assert data["publish"]["email_status"] == "done" and data["publish"]["doc_url"]
    assert CFG.email.to not in json.dumps(data)  # the recipient never reaches the dashboard


def test_unvalidated_pulse_is_left_out(tmp_path):
    rdir = seed_run(tmp_path, pulse())
    data = build(CFG, RUN, rdir)
    assert data["pulse"] is None and data["publish"] is None
    (rdir / "validation.json").write_text(json.dumps({"passed": True, "pulse_sha256": "0" * 64}))
    assert build(CFG, RUN, rdir)["pulse"] is None  # pulse.md changed after the gate


def test_pii_in_the_corpus_aborts(tmp_path):
    rdir = seed_run(tmp_path, pulse())
    leaky = review(9, "Call me on 9876543210 about the refund please.")
    pipeline.write_jsonl(rdir / pipeline.CLEAN_FILE, [leaky])
    with pytest.raises(DashboardError, match="PII"):
        build(CFG, RUN, rdir)


def test_missing_theme_stage_fails(tmp_path):
    (tmp_path / RUN).mkdir()
    with pytest.raises(DashboardError, match="theme"):
        build(CFG, RUN, tmp_path / RUN)


def test_cli_writes_the_file(tmp_path, monkeypatch):
    published_run(tmp_path)
    monkeypatch.setattr(pipeline, "DATA_DIR", tmp_path)
    out = tmp_path / "web" / "dashboard.json"
    assert cli.main(["dashboard", "--week", RUN, "--out", str(out)]) == 0
    assert json.loads(out.read_text())["run_id"] == RUN
    assert cli.main(["dashboard", "--week", "2020-W01", "--out", str(out)]) == cli.EXIT_DASHBOARD
