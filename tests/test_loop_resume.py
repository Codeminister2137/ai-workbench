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
