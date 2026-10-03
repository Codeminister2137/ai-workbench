"""Offline acceptance planning must never start inference or create run state."""

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[1] / "scripts/research-acceptance.py"
_SPEC = importlib.util.spec_from_file_location("research_acceptance", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
acceptance = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(acceptance)


@pytest.fixture
def offline_only(monkeypatch, tmp_path):
    monkeypatch.setattr(acceptance, "__file__", str(tmp_path / "scripts" / "acceptance.py"))

    def forbidden(*args, **kwargs):
        pytest.fail("Planning/validation started execution or created run state")

    monkeypatch.setattr(acceptance, "run_research", forbidden)
    monkeypatch.setattr(acceptance, "SQLiteOrchestratedRunStore", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    monkeypatch.setattr(Path, "mkdir", forbidden)
    return tmp_path


def option(arguments, flag):
    return arguments[arguments.index(flag) + 1]


def test_default_plan_preserves_short_legacy_acceptance(offline_only, capsys):
    assert acceptance.main(["--model", "gpt-oss:20b", "--plan"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["status"] == "PLANNED"
    assert plan["budget_seconds"] == 600
    args = plan["worker_arguments"]
    assert option(args, "--max-repair-cycles") == "3"
    assert option(args, "--research-review-policy") == "legacy"
    assert option(args, "--privacy") == option(args, "--cost-policy") == "local_only"
    assert option(args, "--tool-profile") == "research"
    assert not Path(plan["artifact_directory"]).exists()
    assert not list(offline_only.iterdir())


def test_sustained_plan_forwards_approved_reviewer_settings(offline_only, capsys):
    tokenizer = offline_only / "missing tokenizer.json"
    assert (
        acceptance.main(
            [
                "--model",
                "gpt-oss:20b",
                "--plan",
                "--away-minutes",
                "110",
                "--max-repair-cycles",
                "-1",
                "--research-review-policy",
                "quality_first",
                "--research-review-model",
                "qwen3:14b",
                "--research-review-mode",
                "deliberative",
                "--research-review-output-tokens",
                "8192",
                "--research-review-timeout-seconds",
                "250",
                "--research-review-tokenizer-file",
                str(tokenizer),
            ]
        )
        == 0
    )
    plan = json.loads(capsys.readouterr().out)
    assert plan["budget_seconds"] == 6600
    args = plan["worker_arguments"]
    for flag, expected in {
        "--model": "gpt-oss:20b",
        "--max-repair-cycles": "-1",
        "--research-review-policy": "quality_first",
        "--research-review-model": "qwen3:14b",
        "--research-review-mode": "deliberative",
        "--research-review-output-tokens": "8192",
        "--research-review-timeout-seconds": "250.0",
        "--research-review-tokenizer-file": str(tokenizer),
    }.items():
        assert option(args, flag) == expected
    assert not list(offline_only.iterdir())


@pytest.mark.parametrize(
    "extra",
    [
        ["--model", " "],
        ["--away-minutes", "0"],
        ["--away-minutes", "nan"],
        ["--away-minutes", "inf"],
        ["--away-minutes", "1e308"],
        ["--max-repair-cycles", "-2"],
        ["--research-review-model", "qwen3:14b"],
        ["--research-review-tokenizer-file", "tokenizer.json"],
        ["--research-review-policy", "quality_first", "--research-review-model", " "],
        ["--research-review-policy", "quality_first", "--research-review-output-tokens", "8193"],
        ["--research-review-policy", "quality_first", "--research-review-timeout-seconds", "301"],
    ],
)
@pytest.mark.parametrize("planning", [True, False])
def test_invalid_settings_fail_before_any_run_state(offline_only, extra, planning):
    arguments = ["--model", "gpt-oss:20b", *extra]
    if planning:
        arguments.append("--plan")
    with pytest.raises(SystemExit) as error:
        acceptance.main(arguments)
    assert error.value.code == 2


def test_execution_forwards_settings_and_preserves_worker_failure(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(acceptance, "__file__", str(tmp_path / "scripts" / "acceptance.py"))
    calls = []

    def fake_worker(arguments):
        calls.append(arguments)
        assert Path(option(arguments, "--research-report")).parent.is_dir()
        return 7

    monkeypatch.setattr(acceptance, "run_research", fake_worker)
    assert (
        acceptance.main(
            [
                "--model",
                "gpt-oss:20b",
                "--research-review-policy",
                "quality_first",
                "--research-review-model",
                "qwen3:14b",
                "--research-review-mode",
                "deliberative",
                "--research-review-tokenizer-file",
                "local.json",
                "--max-repair-cycles",
                "-1",
            ]
        )
        == 7
    )
    assert len(calls) == 1
    assert option(calls[0], "--research-review-tokenizer-file") == "local.json"
    assert option(calls[0], "--research-review-model") == "qwen3:14b"
    assert option(calls[0], "--max-repair-cycles") == "-1"
    assert "Acceptance incomplete: exit=7" in capsys.readouterr().out
