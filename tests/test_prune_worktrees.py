"""Retention pruner (inbox 8d79ac88 answer A): selection, safety, dry-run."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "prune_worktrees", Path(__file__).resolve().parents[1] / "scripts" / "prune-worktrees.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE  # slotted dataclasses need this during exec
SPEC.loader.exec_module(MODULE)

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)


def _write_run(data: Path, run_id: str, status: str, finished_days_ago: int | None) -> None:
    record: dict[str, object] = {"id": run_id, "status": status}
    if finished_days_ago is not None:
        record["finished_at_utc"] = (NOW - timedelta(days=finished_days_ago)).isoformat()
    (data / "runs").mkdir(parents=True, exist_ok=True)
    (data / "runs" / f"{run_id}.json").write_text(json.dumps(record), encoding="utf-8")
    (data / "run-progress").mkdir(parents=True, exist_ok=True)
    (data / "run-progress" / f"{run_id}.jsonl").write_text("{}\n", encoding="utf-8")


def _checkout(repo: Path, short: str) -> Path:
    target = repo / ".tmp" / "run-worktrees" / short
    target.mkdir(parents=True, exist_ok=True)
    (target / "file.txt").write_text("state", encoding="utf-8")
    return target


def _runner_for(repo: Path, registered: list[Path], locked: list[Path] | None = None):
    locked_set = {p.resolve() for p in (locked or [])}

    def run(_repo: Path, *args: str) -> str:
        assert args[:2] == ("worktree", "list"), args
        lines = [f"worktree {repo.resolve()}", "HEAD x", ""]
        for path in registered:
            lines += [f"worktree {path.resolve()}", "HEAD y", ""]
            if path.resolve() in locked_set:
                lines.insert(-1, "locked")
        return "\n".join(lines) + "\n"

    return run


def test_selects_old_terminal_registered_checkouts(tmp_path: Path) -> None:
    repo, data = tmp_path / "repo", tmp_path / "data"
    old = "0" * 12 + "a" * 20
    recent = "1" * 12 + "b" * 20
    live = "2" * 12 + "c" * 20
    _write_run(data, old, "completed", 45)
    _write_run(data, recent, "failed", 5)
    _write_run(data, live, "queued", None)
    old_dir = _checkout(repo, old[:12])
    _checkout(repo, recent[:12])
    _checkout(repo, live[:12])
    result = MODULE.collect_candidates(repo, data, 30, NOW, _runner_for(repo, [old_dir]))
    assert [c.run_id for c in result.candidates] == [old]
    reasons = {item["run"]: item["reason"] for item in result.skipped}
    assert "recently" in reasons[recent]
    assert "live" in reasons[live]


def test_boundary_day_counts_as_eligible(tmp_path: Path) -> None:
    repo, data = tmp_path / "repo", tmp_path / "data"
    run_id = "3" * 12 + "d" * 20
    _write_run(data, run_id, "cancelled", 30)
    target = _checkout(repo, run_id[:12])
    result = MODULE.collect_candidates(repo, data, 30, NOW, _runner_for(repo, [target]))
    assert [c.run_id for c in result.candidates] == [run_id]


def test_missing_dates_strays_orphans_and_locks_skipped(tmp_path: Path) -> None:
    repo, data = tmp_path / "repo", tmp_path / "data"
    nodate = "4" * 12 + "e" * 20
    stray = "5" * 12 + "f" * 20
    locked = "6" * 12 + "0" * 20
    _write_run(data, nodate, "merged", None)
    _write_run(data, stray, "closed", 60)
    _write_run(data, locked, "completed", 60)
    _checkout(repo, nodate[:12])
    _checkout(repo, stray[:12])
    locked_dir = _checkout(repo, locked[:12])
    _checkout(repo, "orphanorphan")
    result = MODULE.collect_candidates(
        repo, data, 30, NOW, _runner_for(repo, [locked_dir], [locked_dir])
    )
    assert result.candidates == []
    reasons = {item["run"]: item["reason"] for item in result.skipped}
    assert "no terminal date" in reasons[nodate]
    assert "stray" in reasons[stray]
    assert "locked" in reasons[locked]
    assert "orphan" in reasons["orphanorphan"]


def test_dry_run_deletes_nothing_and_apply_uses_git_remove(tmp_path: Path) -> None:
    repo, data = tmp_path / "repo", tmp_path / "data"
    run_id = "7" * 12 + "1" * 20
    _write_run(data, run_id, "completed", 90)
    target = _checkout(repo, run_id[:12])
    result = MODULE.collect_candidates(repo, data, 30, NOW, _runner_for(repo, [target]))
    assert len(result.candidates) == 1
    calls: list[tuple[str, ...]] = []

    def fail_if_called(_repo: Path, *args: str) -> str:
        calls.append(args)
        raise AssertionError("dry-run must not call git remove")

    report = MODULE.prune_candidates(repo, result.candidates, apply=False, runner=fail_if_called)
    assert report["removed"] == [] and target.is_dir()

    def fake_remove(_repo: Path, *args: str) -> str:
        calls.append(args)
        return ""

    report = MODULE.prune_candidates(repo, result.candidates, apply=True, runner=fake_remove)
    assert report["removed"] == [run_id]
    assert calls[-1][:3] == ("worktree", "remove", "--force")
    assert str(target) in calls[-1]
    # Text evidence survives either way.
    assert (data / "runs" / f"{run_id}.json").is_file()
    assert (data / "run-progress" / f"{run_id}.jsonl").is_file()


def test_nested_registered_worktree_goes_before_its_parent(tmp_path: Path) -> None:
    repo, data = tmp_path / "repo", tmp_path / "data"
    parent_id = "8" * 12 + "2" * 20
    _write_run(data, parent_id, "failed", 90)
    parent = _checkout(repo, parent_id[:12])
    nested = parent / ".tmp" / "nested"
    nested.mkdir(parents=True)
    calls: list[tuple[str, ...]] = []
    list_runner = _runner_for(repo, [parent, nested])

    def fake(_repo: Path, *args: str) -> str:
        if args[:2] == ("worktree", "list"):
            return list_runner(_repo, *args)
        calls.append(args)
        return ""

    result = MODULE.collect_candidates(repo, data, 30, NOW, fake)
    assert [c.run_id for c in result.candidates] == [parent_id]
    report = MODULE.prune_candidates(repo, result.candidates, apply=True, runner=fake)
    assert report["removed"] == [parent_id]
    assert report["nested_removed"] == [str(nested.resolve())]
    assert [c[-1] for c in calls] == [str(nested.resolve()), str(parent)]
