"""Validation command interpreter selection stays explicit and observable."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest
from ai_provider import repo_coding_assistant as cli


def test_default_pytest_validation_uses_current_agent_interpreter(tmp_path, monkeypatch):
    captured = {}

    def run(arguments, **kwargs):
        captured["arguments"] = arguments
        captured.update(kwargs)
        return SimpleNamespace(returncode=0, stdout="passed", stderr="")

    monkeypatch.setattr(cli.subprocess, "run", run)

    results = cli._run_validation_commands(
        (cli.DEFAULT_VALIDATION_COMMAND,),
        repo_root=tmp_path,
        timeout_seconds=30,
        progress_callback=lambda _message: None,
        default_python=sys.executable,
    )

    assert captured["arguments"] == [sys.executable, "-m", "pytest", "-q"]
    assert captured["cwd"] == tmp_path
    assert results[0].executable == sys.executable
    assert cli._validation_results_json(results)[0]["executable"] == sys.executable


def test_default_validation_python_is_repo_assistant_executable():
    args = cli.build_argument_parser().parse_args([])

    assert cli._default_validation_python(args) == sys.executable


def test_blank_validation_python_is_rejected():
    with pytest.raises(SystemExit):
        cli.build_argument_parser().parse_args(["--validation-python", "  "])


def test_explicit_validation_python_overrides_only_default_pytest(tmp_path, monkeypatch):
    captured = {}

    def run(arguments, **kwargs):
        captured["arguments"] = arguments
        return SimpleNamespace(returncode=0, stdout="passed", stderr="")

    monkeypatch.setattr(cli.subprocess, "run", run)
    selected_python = str(tmp_path / "selected python.exe")
    args = cli.build_argument_parser().parse_args(["--validation-python", selected_python])

    assert cli._default_validation_python(args) == selected_python
    results = cli._run_validation_commands(
        (cli.DEFAULT_VALIDATION_COMMAND,),
        repo_root=tmp_path,
        timeout_seconds=30,
        default_python=cli._default_validation_python(args),
        progress_callback=lambda _message: None,
    )

    assert captured["arguments"] == [selected_python, "-m", "pytest", "-q"]
    assert results[0].executable == selected_python


def test_custom_validation_command_keeps_selected_executable(tmp_path, monkeypatch):
    captured = {}

    def run(arguments, **kwargs):
        captured["arguments"] = arguments
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(cli.subprocess, "run", run)
    custom_python = str(tmp_path / "python.exe")
    command = f"{custom_python} -m pytest tests -q"

    results = cli._run_validation_commands(
        (command,),
        repo_root=tmp_path,
        timeout_seconds=30,
        default_python=None,
        progress_callback=lambda _message: None,
    )

    assert captured["arguments"] == [custom_python, "-m", "pytest", "tests", "-q"]
    assert results[0].executable == custom_python


def test_validation_python_does_not_rewrite_explicit_commands(tmp_path, monkeypatch):
    captured = {}

    def run(arguments, **kwargs):
        captured["arguments"] = arguments
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(cli.subprocess, "run", run)
    args = cli.build_argument_parser().parse_args(
        ["--validation-command", "python -m pytest -q", "--validation-python", "selected-python"]
    )

    assert cli._default_validation_python(args) is None
    cli._run_validation_commands(
        cli._validation_commands_from_args(args),
        repo_root=tmp_path,
        timeout_seconds=30,
        default_python=cli._default_validation_python(args),
        progress_callback=lambda _message: None,
    )

    assert captured["arguments"] == ["python", "-m", "pytest", "-q"]


def test_validation_python_is_inactive_when_validation_is_skipped_or_research():
    parser = cli.build_argument_parser()
    selected_python = "C:\\project\\.venv\\Scripts\\python.exe"

    skipped = parser.parse_args(["--skip-validation", "--validation-python", selected_python])
    assert cli._default_validation_python(skipped) is None

    research = parser.parse_args(
        ["--validation-python", selected_python, "--tool-profile", "research"]
    )
    assert cli._default_validation_python(research) is None


def test_blank_validation_commands_still_use_selected_default_interpreter():
    selected_python = "C:\\project\\.venv\\Scripts\\python.exe"
    args = cli.build_argument_parser().parse_args(
        ["--validation-command", "  ", "--validation-python", selected_python]
    )

    assert cli._validation_commands_from_args(args) == (cli.DEFAULT_VALIDATION_COMMAND,)
    assert cli._default_validation_python(args) == selected_python


def test_windows_validation_command_unquotes_paths_without_stripping_backslashes():
    command = (
        '"C:\\Users\\Jakub Example\\.venv\\Scripts\\python.exe" '
        '-m pytest ".\\tests\\integration suite" -q'
    )

    assert cli._split_validation_command(command, windows=True) == [
        "C:\\Users\\Jakub Example\\.venv\\Scripts\\python.exe",
        "-m",
        "pytest",
        ".\\tests\\integration suite",
        "-q",
    ]
