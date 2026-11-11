"""Doctor preflight: offline probes, fake transports, fix-it list."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from ai_agent.doctor import format_report, main, run_doctor

CATALOG_TOML = """\
[[models]]
provider = "ollama"
model = "fake"
location = "local"
"""


def _repo(tmp_path: Path, *, catalog: bool = True, dotenv: bool = True) -> Path:
    if sys.platform == "win32":
        python = tmp_path / ".venv" / "Scripts" / "python.exe"
    else:
        python = tmp_path / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("x", encoding="utf-8")
    if dotenv:
        (tmp_path / ".env").write_text("K=V\n", encoding="utf-8")
    if catalog:
        target = tmp_path / "packages/ai_orchestrator/examples/model_catalog.toml"
        target.parent.mkdir(parents=True)
        target.write_text(CATALOG_TOML, encoding="utf-8")
    return tmp_path


class _TagsResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def _tags_ok(url, timeout=5):
    return _TagsResponse({"models": [{"name": "m1"}, {"name": "m2"}]})


def _tags_down(url, timeout=5):
    raise ConnectionError("refused")


def test_healthy_tree_reports_ok(tmp_path, monkeypatch) -> None:
    import urllib.request

    monkeypatch.setattr("shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(urllib.request, "urlopen", _tags_ok)
    checks = run_doctor(
        _repo(tmp_path), urlopen=_tags_ok, client_command=lambda method: f"/bin/{method}"
    )
    by_name = {check.name: check for check in checks}
    assert by_name["python"].ok
    assert by_name["uv"].ok
    assert by_name["repo .venv"].ok
    assert by_name["ollama"].ok and "2 model(s)" in by_name["ollama"].detail
    assert by_name["catalog"].ok and by_name["catalog"].detail == "1 entries"
    assert by_name[".env"].ok
    assert main(["--repo-root", str(tmp_path)]) == 0


def test_missing_pieces_land_in_fix_list(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr("shutil.which", lambda name: None)
    checks = run_doctor(tmp_path, urlopen=_tags_down, client_command=lambda method: None)
    by_name = {check.name: check for check in checks}
    assert not by_name["uv"].ok
    assert not by_name["repo .venv"].ok
    assert not by_name["ollama"].ok
    assert not by_name["catalog"].ok
    assert not by_name[".env"].ok  # optional: prints, never fails the exit
    report = format_report(checks)
    assert "[FAIL] catalog" in report
    assert "[WARN] client:codex" in report
    assert "Fix:" in report
    assert main(["--repo-root", str(tmp_path)]) == 1
    assert "Fix:" in capsys.readouterr().out


def test_old_python_fails(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(sys, "version_info", (3, 12, 0))
    (by_python,) = [c for c in run_doctor(tmp_path) if c.name == "python"]
    assert not by_python.ok and "3.13" in by_python.fix


def test_unparseable_catalog_fails(tmp_path) -> None:
    root = _repo(tmp_path)
    (root / "packages/ai_orchestrator/examples/model_catalog.toml").write_text(
        "models = 42\n", encoding="utf-8"
    )
    (by_catalog,) = [c for c in run_doctor(root) if c.name == "catalog"]
    assert not by_catalog.ok


def test_no_secrets_in_report(tmp_path, monkeypatch) -> None:
    root = _repo(tmp_path)
    (root / ".env").write_text("GMAIL_PASSWORD=hunter2\n", encoding="utf-8")
    monkeypatch.setattr("shutil.which", lambda name: f"/bin/{name}")
    report = format_report(run_doctor(root, urlopen=_tags_ok))
    assert "hunter2" not in report
    assert "GMAIL_PASSWORD" not in report


def test_cli_dispatches_doctor(monkeypatch, tmp_path, capsys) -> None:
    import urllib.request

    from ai_agent.cli import main as cli_main

    _repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(urllib.request, "urlopen", _tags_ok)
    assert cli_main(["doctor", "--repo-root", str(tmp_path)]) == 0
    assert "Workbench doctor:" in capsys.readouterr().out


def test_cli_rejects_doctor_as_mode() -> None:
    from ai_agent.cli import main as cli_main

    # Not the doctor path: falls through to mode parsing, which rejects it.
    with pytest.raises(SystemExit) as exc:
        cli_main(["--mode", "doctor"])
    assert exc.value.code != 0
