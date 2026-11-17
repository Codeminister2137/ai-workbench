"""Tests for scripts/e2e-promotion.py (ADR-087 workflow)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "e2e-promotion.py"


def _load():
    spec = importlib.util.spec_from_file_location("e2e_promotion_cli", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def cli():
    return _load()


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return completed.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "master", str(root)], check=True, timeout=60)
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    (root / "app.py").write_text("one", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "one")
    return root


def test_load_reports_skips_bad_files(cli, tmp_path: Path) -> None:
    data = tmp_path / "data"
    (data / "e2e_reports").mkdir(parents=True)
    (data / "e2e_reports" / "good.json").write_text('{"commit": "x"}', encoding="utf-8")
    (data / "e2e_reports" / "bad.json").write_text("nope", encoding="utf-8")
    assert cli.load_reports(data) == [{"commit": "x"}]
    assert cli.load_reports(tmp_path / "missing") == []


def test_gate_exit_codes(cli, tmp_path: Path, capsys) -> None:
    data = tmp_path / "data"
    (data / "e2e_reports").mkdir(parents=True)
    (data / "e2e_reports" / "r.json").write_text(
        json.dumps({"commit": "abc", "overall": "pass", "built_utc": "2026-01-01T00:00:00+00:00"}),
        encoding="utf-8",
    )
    assert cli.main(["gate", "abc", "--data-dir", str(data)]) == 0
    assert cli.main(["gate", "zzz", "--data-dir", str(data)]) == 1
    assert "no E2E report" in capsys.readouterr().out


def test_generate_dry_run_lists_checklist(cli, repo: Path, capsys, monkeypatch) -> None:
    (repo / "second.py").write_text("two", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "two")
    head = _git(repo, "rev-parse", "HEAD")
    monkeypatch.setattr(cli, "REPO_ROOT", repo)
    code = cli.main(["generate", head, "--dry-run", "--data-dir", str(repo / "data")])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["merge_commit"] == head
    assert payload["items"]


def test_promote_refuses_uncovered_merges(cli, repo: Path, capsys, monkeypatch) -> None:
    _git(repo, "checkout", "-qb", "develop")
    _git(repo, "checkout", "-qb", "feature")
    (repo / "feat.py").write_text("f", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "feat")
    _git(repo, "checkout", "-q", "develop")
    _git(repo, "merge", "--no-ff", "feature", "-m", "merge feature")
    monkeypatch.setattr(cli, "REPO_ROOT", repo)
    code = cli.main(["promote", "--target", "master", "--data-dir", str(repo / "data")])
    assert code == 3
    assert "lack a passing E2E report" in capsys.readouterr().out


def _task_file(data: Path, name: str, merge: str, status: str) -> None:
    tasks = data / "e2e_tasks"
    tasks.mkdir(parents=True, exist_ok=True)
    (tasks / name).write_text(
        json.dumps({"id": name[:-5], "merge_commit": merge, "status": status}),
        encoding="utf-8",
    )


def test_covering_task_blocks_open_and_submitted_but_not_drafts(cli, tmp_path: Path) -> None:
    data = tmp_path / "data"
    _task_file(data, "open.json", "aaa", "open")
    _task_file(data, "done.json", "bbb", "submitted")
    _task_file(data, "draft.json", "ccc", "draft")
    assert cli._existing_covering_task(data, "aaa")["id"] == "open"
    assert cli._existing_covering_task(data, "bbb")["id"] == "done"
    assert cli._existing_covering_task(data, "ccc") is None
    assert cli._existing_covering_task(data, "zzz") is None
    assert cli._existing_covering_task(tmp_path / "missing", "aaa") is None


def _agent_checklist() -> dict:
    runnable = {"action": "Run `x`", "expected": "y", "agent_runnable": True}
    return {
        "items": [
            {"id": "behavior:a", "kind": "behavior", "status": "pending", "steps": [runnable]},
            {
                "id": "behavior:b",
                "kind": "behavior",
                "status": "pending",
                "steps": [dict(runnable)],
            },
            {"id": "nonbehavioral:docs", "kind": "nonbehavioral", "status": "auto-pass"},
        ]
    }


def test_all_agent_steps_accepts_and_rejects(cli) -> None:
    assert cli._all_agent_steps(_agent_checklist()) == [("behavior:a", 0), ("behavior:b", 0)]
    mixed = _agent_checklist()
    mixed["items"][0]["steps"][0]["agent_runnable"] = False
    assert cli._all_agent_steps(mixed) is None
    regressed = _agent_checklist()
    regressed["items"].append(
        {
            "id": "regression:c",
            "kind": "regression",
            "status": "pending",
            "steps": [{"agent_runnable": True}],
        }
    )
    assert cli._all_agent_steps(regressed) is None
    assert cli._all_agent_steps({"items": []}) is None


def test_auto_submit_posts_checks_then_agent_verdict(cli) -> None:
    calls: list = []

    def poster(url, payload, token):
        calls.append((url, payload))
        if url.endswith("/agent-check"):
            return {"ok": True, "evidence": {"evidence_exit": 0}}
        return {"ok": True, "overall": "pass", "report_id": "r1"}

    line = cli.auto_submit_agent_task("http://x", None, "t1", _agent_checklist(), poster=poster)
    assert "auto-submitted overall=pass" in line
    assert [url for url, _payload in calls].count("http://x/api/e2e/tasks/t1/submit") == 1
    submit_payload = calls[-1][1]
    assert submit_payload["verdict_by"] == "agent"
    assert submit_payload["results"] == [
        {"item_id": "behavior:a", "steps": ["pass"], "notes": ""},
        {"item_id": "behavior:b", "steps": ["pass"], "notes": ""},
    ]


def test_auto_submit_leaves_open_on_red_check(cli) -> None:
    def poster(url, payload, token):
        if url.endswith("/agent-check"):
            return {"ok": True, "evidence": {"evidence_exit": 3}}
        raise AssertionError("must not submit on red")

    with pytest.raises(RuntimeError, match="leaving open"):
        cli.auto_submit_agent_task("http://x", None, "t1", _agent_checklist(), poster=poster)


def test_covering_task_matches_short_hashes(cli, tmp_path: Path) -> None:
    data = tmp_path / "data"
    _task_file(data, "full.json", "abcdef1234567890", "submitted")
    assert cli._existing_covering_task(data, "abcdef1")["id"] == "full"


def test_generate_refuses_covered_merge_without_retest(
    cli, repo: Path, tmp_path: Path, capsys, monkeypatch
) -> None:
    (repo / "second.py").write_text("two", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "two")
    head = _git(repo, "rev-parse", "HEAD")
    data = tmp_path / "data"
    _task_file(data, "old.json", head, "submitted")
    monkeypatch.setattr(cli, "REPO_ROOT", repo)
    filed: list = []
    monkeypatch.setattr(
        cli, "file_task", lambda *args: filed.append(args) or {"ok": True, "id": "new"}
    )
    code = cli.main(["generate", head, "--data-dir", str(data)])
    assert code == 1
    assert filed == []
    assert "already covers" in capsys.readouterr().out
    monkeypatch.setattr(cli, "submit_task", lambda *args: {"report_id": "r"})
    code = cli.main(["generate", head, "--retest", "--data-dir", str(data)])
    assert code == 0
    assert len(filed) == 1
