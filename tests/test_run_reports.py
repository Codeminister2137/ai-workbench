"""Tests for deterministic run reports."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ai_agent.run_reports import (
    REPORT_FLAVORS,
    render_report,
    render_run_report,
    render_shareable_report,
)
from ai_agent.supervisor_drain import RunDrain


def _make_drain(tmp_path: Path) -> RunDrain:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    return RunDrain(
        runs_dir=runs_dir,
        get_inbox=lambda _inbox_id: None,
        executor=lambda _run: {"status": "completed"},
        now=lambda: 0.0,
    )


def test_completed_run_exact_markdown() -> None:
    run = {
        "id": "r-1",
        "title": "Demo run",
        "status": "completed",
        "started_at_utc": "2026-01-01T00:00:00+00:00",
        "finished_at_utc": "2026-01-01T00:05:00+00:00",
        "staged": ["a.txt", "b/c.txt"],
        "receipts": [
            {
                "status": "completed",
                "iterations": 3,
                "tool_calls": [{"tool": "read"}, {"tool": "write"}],
                "owner_tasks": [{"id": "t-1"}, {"id": "t-2"}],
                "summary": "Did things.",
            }
        ],
    }
    expected = (
        "# Demo run (r-1)\n"
        "Status: completed\n"
        "Started (UTC): 2026-01-01T00:00:00+00:00\n"
        "Finished (UTC): 2026-01-01T00:05:00+00:00\n"
        "Iterations: 3\n"
        "\n"
        "## Tools used\n"
        "- read\n"
        "- write\n"
        "\n"
        "## Staged files\n"
        "- a.txt\n"
        "- b/c.txt\n"
        "\n"
        "## Owner tasks filed\n"
        "- t-1\n"
        "- t-2\n"
        "\n"
        "## Summary\n"
        "Did things."
    )
    assert render_run_report(run) == expected


def test_failed_run_error_section_exact() -> None:
    run = {
        "id": "r-2",
        "title": "Fail run",
        "status": "failed",
        "finished_at_utc": "2026-01-02T00:00:00+00:00",
        "error": "boom",
        "receipts": [{"status": "failed", "summary": "tried"}],
    }
    expected = (
        "# Fail run (r-2)\n"
        "Status: failed\n"
        "Finished (UTC): 2026-01-02T00:00:00+00:00\n"
        "Iterations: (none)\n"
        "\n"
        "## Tools used\n"
        "(none)\n"
        "\n"
        "## Staged files\n"
        "(none)\n"
        "\n"
        "## Owner tasks filed\n"
        "(none)\n"
        "\n"
        "## Error\n"
        "boom\n"
        "\n"
        "## Summary\n"
        "tried"
    )
    assert render_run_report(run) == expected


def test_minimal_run_no_crash() -> None:
    expected = (
        "# untitled (unknown)\n"
        "Status: (none)\n"
        "Iterations: (none)\n"
        "\n"
        "## Tools used\n"
        "(none)\n"
        "\n"
        "## Staged files\n"
        "(none)\n"
        "\n"
        "## Owner tasks filed\n"
        "(none)"
    )
    assert render_run_report({}) == expected
    weird = {
        "title": 123,
        "id": None,
        "status": 5,
        "staged": "nope",
        "receipts": "nope",
        "error": 123,
    }
    assert render_run_report(weird) == expected


def test_finish_attaches_report(tmp_path: Path) -> None:
    drain = _make_drain(tmp_path)
    runs_dir = tmp_path / "runs"
    path = runs_dir / "r-9.json"
    claim = runs_dir / "r-9.json.claim"
    run: dict = {"id": "r-9", "title": "Finish me", "status": "running"}
    receipt = {
        "status": "completed",
        "iterations": 2,
        "tool_calls": ["read"],
        "summary": "ok",
    }
    outcome = drain._finish(path, claim, run, "completed", error=None, receipt=receipt)
    assert outcome == {"run_id": "r-9", "status": "completed"}
    assert run["report"] == render_run_report(run)
    assert run["report"] == (
        "# Finish me (r-9)\n"
        "Status: completed\n"
        "Finished (UTC): 1970-01-01T00:00:00+00:00\n"
        "Iterations: 2\n"
        "\n"
        "## Tools used\n"
        "- read\n"
        "\n"
        "## Staged files\n"
        "(none)\n"
        "\n"
        "## Owner tasks filed\n"
        "(none)\n"
        "\n"
        "## Summary\n"
        "ok"
    )
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["report"] == run["report"]
    path2 = runs_dir / "r-10.json"
    claim2 = runs_dir / "r-10.json.claim"
    run2: dict = {"id": "r-10", "title": "Synthetic", "status": "running"}
    drain._finish(path2, claim2, run2, "failed", error="boom", receipt=None)
    assert run2["report"] == render_run_report(run2)
    assert "## Error\nboom" in run2["report"]
    path3 = runs_dir / "r-11.json"
    claim3 = runs_dir / "r-11.json.claim"
    run3: dict = {
        "id": "r-11",
        "title": "Keep",
        "status": "running",
        "report": "custom narrative",
    }
    drain._finish(path3, claim3, run3, "completed", error=None, receipt={"status": "completed"})
    assert run3["report"] == "custom narrative"


def test_shareable_drops_internals_exact() -> None:
    run = {
        "id": "r-1",
        "title": "Demo run",
        "status": "completed",
        "started_at_utc": "2026-01-01T00:00:00+00:00",
        "finished_at_utc": "2026-01-01T00:05:00+00:00",
        "staged": ["a.txt", "b/c.txt"],
        "receipts": [
            {
                "status": "completed",
                "iterations": 3,
                "tool_calls": [{"tool": "read"}, {"tool": "write"}],
                "owner_tasks": [{"id": "t-1"}, {"id": "t-2"}],
                "summary": "Did things.",
            }
        ],
    }
    expected = (
        "# Demo run (r-1)\n"
        "Status: completed\n"
        "Started (UTC): 2026-01-01T00:00:00+00:00\n"
        "Finished (UTC): 2026-01-01T00:05:00+00:00\n"
        "\n"
        "## Staged files\n"
        "- a.txt\n"
        "- b/c.txt\n"
        "\n"
        "## Summary\n"
        "Did things."
    )
    assert render_shareable_report(run) == expected


def test_shareable_drops_error_section() -> None:
    run = {
        "id": "r-2",
        "title": "Fail run",
        "status": "failed",
        "finished_at_utc": "2026-01-02T00:00:00+00:00",
        "error": "boom",
        "receipts": [{"status": "failed", "summary": "tried"}],
    }
    out = render_shareable_report(run)
    assert "## Error" not in out
    assert "boom" not in out
    assert "## Summary\ntried" in out


def test_shareable_minimal_no_crash() -> None:
    expected = "# untitled (unknown)\nStatus: (none)\n\n## Staged files\n(none)"
    assert render_shareable_report({}) == expected
    weird = {
        "title": 123,
        "id": None,
        "status": 5,
        "staged": "nope",
        "receipts": "nope",
        "error": 123,
    }
    assert render_shareable_report(weird) == expected


def test_render_report_dispatcher() -> None:
    run = {"id": "r-1", "title": "Demo run", "status": "completed"}
    assert render_report(run) == render_run_report(run)
    assert render_report(run, "full") == render_run_report(run)
    assert render_report(run, "shareable") == render_shareable_report(run)
    assert REPORT_FLAVORS == ("full", "shareable")
    with pytest.raises(ValueError, match="unknown report flavor"):
        render_report(run, "owner-plus")


def test_finish_attaches_both_flavors(tmp_path: Path) -> None:
    drain = _make_drain(tmp_path)
    runs_dir = tmp_path / "runs"
    path = runs_dir / "r-20.json"
    claim = runs_dir / "r-20.json.claim"
    run: dict = {"id": "r-20", "title": "Both", "status": "running"}
    receipt = {"status": "completed", "iterations": 2, "summary": "ok"}
    drain._finish(path, claim, run, "completed", error=None, receipt=receipt)
    assert run["shareable_report"] == render_shareable_report(run)
    assert "Iterations" not in run["shareable_report"]
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["shareable_report"] == run["shareable_report"]
    path2 = runs_dir / "r-21.json"
    claim2 = runs_dir / "r-21.json.claim"
    run2: dict = {
        "id": "r-21",
        "title": "Keep",
        "status": "running",
        "shareable_report": "hand-written client note",
    }
    drain._finish(path2, claim2, run2, "completed", error=None, receipt={"status": "completed"})
    assert run2["shareable_report"] == "hand-written client note"
