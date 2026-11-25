"""Tests for scripts/supervision.py (supervision flip + self-check)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "supervision.py"


def _load():
    spec = importlib.util.spec_from_file_location("supervision_cli", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _repo(tmp_path: Path, *, with_serve: bool = True) -> Path:
    repo = tmp_path / "repo"
    (repo / "apps" / "workbench_dashboard").mkdir(parents=True)
    (repo / "apps" / "workbench_dashboard" / "dashboard.json").write_text(
        json.dumps({"title": "T", "supervision": "attended"}), encoding="utf-8"
    )
    if with_serve:
        serve = tmp_path / "ai-workbench-serve" / "apps" / "workbench_dashboard"
        serve.mkdir(parents=True)
    return repo


def _modes(mod, repo: Path) -> dict:
    return {
        label: mod._read_mode(path)
        for label, path in mod._targets(repo)  # noqa: SLF001
    }


def test_set_flips_both_configs_with_readback(tmp_path, capsys) -> None:
    mod = _load()
    repo = _repo(tmp_path)
    assert mod.main(["set", "unattended", "--repo", str(repo)]) == 0
    assert _modes(mod, repo) == {"main": "unattended", "serve": "unattended"}
    assert "supervision=unattended" in capsys.readouterr().out
    assert mod.main(["set", "attended", "--repo", str(repo)]) == 0
    assert _modes(mod, repo) == {"main": "attended", "serve": "attended"}


def test_set_preserves_other_keys_and_rejects_bad_mode(tmp_path, capsys) -> None:
    mod = _load()
    repo = _repo(tmp_path, with_serve=False)
    assert mod.main(["set", "unattended", "--repo", str(repo)]) == 0
    main_config = json.loads(
        (repo / "apps" / "workbench_dashboard" / "dashboard.json").read_text(encoding="utf-8")
    )
    assert main_config == {"title": "T", "supervision": "unattended"}
    assert "no serve worktree" in capsys.readouterr().err
    assert mod.main(["set", "sometimes", "--repo", str(repo)]) == 2


def test_check_reports_match_mismatch_and_expectation(tmp_path, capsys) -> None:
    mod = _load()
    repo = _repo(tmp_path)
    assert mod.main(["check", "--repo", str(repo)]) == 0
    assert "main: attended" in capsys.readouterr().out
    assert mod.main(["check", "--expect", "attended", "--repo", str(repo)]) == 0
    assert mod.main(["check", "--expect", "unattended", "--repo", str(repo)]) == 1
    assert "MISMATCH" in capsys.readouterr().err
    # Split brain fails even without --expect.
    (repo / "apps" / "workbench_dashboard" / "dashboard.json").write_text(
        json.dumps({"supervision": "unattended"}), encoding="utf-8"
    )
    assert mod.main(["check", "--repo", str(repo)]) == 1
    assert "disagree" in capsys.readouterr().err


def test_check_without_serve_worktree_uses_main_only(tmp_path, capsys) -> None:
    mod = _load()
    repo = _repo(tmp_path, with_serve=False)
    assert mod.main(["check", "--repo", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "main: attended" in out and "serve" not in out
