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
