"""Offline checks for loop resume seeding and run summaries."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/unattended-development-loop.py"
spec = importlib.util.spec_from_file_location("unattended_development_loop", SCRIPT)
assert spec is not None
assert spec.loader is not None
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


def test_completed_means_objective_end_only():
    ledger = "\n".join(
        [
            '{"at": "t", "kind": "start"}',
            '{"at": "t", "kind": "objective-start", "objective": "a"}',
            '{"at": "t", "kind": "objective-end", "objective": "a"}',
            '{"at": "t", "kind": "objective-error", "objective": "b"}',
            '{"at": "t", "kind": "skipped", "objective": "c"}',
            '{"at": "t", "kind": "skipped-missing", "objective": "d"}',
            '{"at": "t", "kind": "notify", "event": "x"}',
            "not json",
            "",
        ]
    )
    assert driver.load_completed_objectives(ledger) == {"a"}
    assert driver.load_completed_objectives("") == set()


def test_stale_dirs_cover_all_kinds(tmp_path):
    assert driver.stale_objective_dirs(tmp_path, {"kind": "implement", "id": "x"}) == [
        tmp_path / "phases" / "x"
    ]
    assert driver.stale_objective_dirs(tmp_path, {"kind": "workbench-implement", "id": "y"}) == [
        tmp_path / "workbench" / "y"
    ]
    assert driver.stale_objective_dirs(tmp_path, {"kind": "propose", "id": "z"}) == [
        tmp_path / "proposals" / "z"
    ]
    assert driver.stale_objective_dirs(tmp_path, {"kind": "other", "id": "w"}) == []


def test_summarize_results_counts_and_totals():
    summary = driver.summarize_results(
        [
            {"id": "a", "status": "accepted"},
            {"id": "b", "status": "error"},
            {"id": "c", "status": "accepted"},
            {"id": "d"},
        ],
        {"requests": 9, "input_tokens": 100, "output_tokens": 50},
        "start",
        "finish",
        "deadline",
        "sup",
        "imp",
    )
    assert summary["by_status"] == {"accepted": 2, "error": 1, "unknown": 1}
    assert summary["requests"] == 9
    assert summary["input_tokens"] == 100
    assert summary["output_tokens"] == 50
    assert summary["started"] == "start"
    assert summary["finished"] == "finish"
    assert summary["supervisor_model"] == "sup"
    assert len(summary["objectives"]) == 4


def test_closeout_immediate_sleep_only_near_deadline():
    assert driver.closeout_immediate_sleep(True, 6000.0) is False
    assert driver.closeout_immediate_sleep(True, 900.0) is True
    assert driver.closeout_immediate_sleep(True, 60.0) is True
    assert driver.closeout_immediate_sleep(False, 60.0) is False


def test_commit_outcome_maps_empty_tree_to_noop():
    assert driver.commit_outcome(0, "[branch x] msg", "") == "committed"
    assert (
        driver.commit_outcome(1, "On branch x\nnothing to commit, working tree clean", "")
        == "accepted-noop"
    )
    assert driver.commit_outcome(1, "", "lock failed") == "commit-failed"


def test_cancel_own_sleep_guards_touches_only_run_files(tmp_path):
    driver.cancel_own_sleep_guards(tmp_path)
    assert (tmp_path / "sleep-continue.cancel").exists()
    assert (tmp_path / "sleep-closeout.cancel").exists()
    assert len(list(tmp_path.iterdir())) == 2


def test_closeout_sleep_note_labels_rolling_and_final(tmp_path):
    import json

    assert driver.closeout_sleep_note(tmp_path, final=False).startswith(
        "rolling guard (internal, no action needed)"
    )
    assert driver.closeout_sleep_note(tmp_path, final=True).startswith("FINAL sleep scheduled")
    (tmp_path / "sleep-continue.json").write_text(
        json.dumps({"status": "sleep_scheduled", "planned_sleep_warsaw": "2026-10-31 20:38:09"}),
        encoding="utf-8",
    )
    rolling = driver.closeout_sleep_note(tmp_path, final=False)
    assert "rolling guard (internal" in rolling
    assert "sleep_scheduled" in rolling and "20:38" in rolling
    (tmp_path / "sleep-continue.json").write_text("not json", encoding="utf-8")
    assert "unknown" in driver.closeout_sleep_note(tmp_path, final=True)


def test_should_mail_error_only_first_mid_run_error():
    assert driver.should_mail_error(0, 0) is False
    assert driver.should_mail_error(5, 0) is True
    assert driver.should_mail_error(5, 1) is False
    assert driver.should_mail_error(0, 1) is False
