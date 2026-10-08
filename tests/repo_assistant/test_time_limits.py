"""CLI time limits must fail before starting sessions, processes or providers."""

from pathlib import Path

import pytest
from ai_agent.repo_assistant_args import build_argument_parser
from ai_agent.repo_coding_assistant import main

TIME_OPTIONS = (
    "--max-latency-seconds",
    "--timeout-seconds",
    "--away-minutes",
    "--validation-timeout-seconds",
    "--ollama-startup-timeout-seconds",
    "--command-timeout-seconds",
)


@pytest.mark.parametrize("option", TIME_OPTIONS)
@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "0", "-1", "1e999", "invalid"])
def test_cli_rejects_invalid_time_limits(option: str, value: str):
    with pytest.raises(SystemExit) as error:
        build_argument_parser().parse_args(["task", f"{option}={value}"])
    assert error.value.code == 2


@pytest.mark.parametrize("option", TIME_OPTIONS)
def test_cli_accepts_fractional_positive_time_limits(option: str):
    args = build_argument_parser().parse_args(["task", f"{option}=0.25"])
    assert getattr(args, option[2:].replace("-", "_")) == 0.25


def test_minutes_that_overflow_the_seconds_budget_are_rejected():
    with pytest.raises(SystemExit) as error:
        build_argument_parser().parse_args(["task", "--away-minutes=1e308"])
    assert error.value.code == 2


@pytest.mark.parametrize("option", ["--away-minutes", "--validation-timeout-seconds"])
def test_invalid_time_limit_does_not_create_persistent_session(tmp_path: Path, option: str):
    database = tmp_path / "sessions.sqlite3"
    with pytest.raises(SystemExit) as error:
        main(
            [
                "task",
                "--mode",
                "implement",
                "--execute",
                "--coding-session",
                "new",
                "--coding-session-db",
                str(database),
                "--repo-root",
                str(tmp_path),
                f"{option}=nan",
            ]
        )
    assert error.value.code == 2
    assert not database.exists()
