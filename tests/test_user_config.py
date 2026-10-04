"""Private defaults retain strict validation and explicit command-line precedence."""

from pathlib import Path

import pytest
from ai_provider.repo_assistant_args import build_argument_parser
from ai_provider.repo_coding_assistant import _configure_away_mode
from ai_provider.user_config import UserConfig, apply_user_defaults, load_user_config


def config_file(tmp_path: Path, settings: str) -> Path:
    path = tmp_path / "user-config.toml"
    path.write_text("[defaults]\n" + settings, encoding="utf-8")
    return path


def test_missing_and_old_config_retain_execution_defaults(tmp_path):
    assert load_user_config(tmp_path / "missing") == UserConfig()
    config = load_user_config(config_file(tmp_path, 'cost_policy = "allowances_allowed"'))
    args = build_argument_parser().parse_args([])
    before = vars(args).copy()
    apply_user_defaults(args, config)
    for key in (
        "quality",
        "context_budget_chars",
        "context_file_budget_chars",
        "instruction_budget_chars",
        "timeout_seconds",
        "validation_timeout_seconds",
        "max_repair_cycles",
        "privacy",
        "approval_policy",
    ):
        assert getattr(args, key, None) == before.get(key)


def test_all_execution_preferences_apply(tmp_path):
    config = load_user_config(
        config_file(
            tmp_path,
            """quality = "high"
context_budget_chars = 0
context_file_budget_chars = 700
instruction_budget_chars = 90000
timeout_seconds = 75
validation_timeout_seconds = 125.5
max_repair_cycles = -1
""",
        )
    )
    args = build_argument_parser().parse_args([])
    apply_user_defaults(args, config)
    assert (
        args.quality,
        args.context_budget_chars,
        args.context_file_budget_chars,
        args.instruction_budget_chars,
        args.timeout_seconds,
        args.validation_timeout_seconds,
        args.max_repair_cycles,
    ) == ("high", 0, 700, 90000, 75.0, 125.5, -1)


@pytest.mark.parametrize(
    "setting",
    [
        'quality = "excellent"',
        "context_budget_chars = -1",
        "context_budget_chars = true",
        "context_file_budget_chars = 0",
        "instruction_budget_chars = 0",
        "max_repair_cycles = -2",
        "max_repair_cycles = 1.5",
        "timeout_seconds = 0",
        "timeout_seconds = inf",
        "timeout_seconds = nan",
        "validation_timeout_seconds = -1",
        "validation_timeout_seconds = true",
        'timeout_seconds = "90"',
        "unknown = 1",
    ],
)
def test_invalid_defaults_rejected(tmp_path, setting):
    with pytest.raises(ValueError):
        load_user_config(config_file(tmp_path, setting))


@pytest.mark.parametrize(
    "option,key,value",
    [
        ("--quality", "quality", "standard"),
        ("--context-budget-chars", "context_budget_chars", 0),
        ("--context-file-budget-chars", "context_file_budget_chars", 2500),
        ("--instruction-budget-chars", "instruction_budget_chars", 64000),
        ("--timeout-seconds", "timeout_seconds", 180.0),
        ("--validation-timeout-seconds", "validation_timeout_seconds", 300.0),
        ("--max-repair-cycles", "max_repair_cycles", 0),
    ],
)
@pytest.mark.parametrize("syntax", ["separate", "equals", "abbreviated"])
def test_explicit_cli_value_wins_even_if_equal_to_shipped_default(
    tmp_path, option, key, value, syntax
):
    config = load_user_config(
        config_file(
            tmp_path,
            """quality = "high"
context_budget_chars = 100
context_file_budget_chars = 100
instruction_budget_chars = 100
timeout_seconds = 100
validation_timeout_seconds = 100
max_repair_cycles = 10
""",
        )
    )
    if syntax == "equals":
        argv = [f"{option}={value}"]
    else:
        argv = [option[:-1] if syntax == "abbreviated" else option, str(value)]
    args = build_argument_parser().parse_args(argv)
    apply_user_defaults(args, config)
    assert getattr(args, key) == value


@pytest.mark.parametrize(
    "configured,argv,expected",
    [
        ("", [], 600),
        ("timeout_seconds = 75", [], 75),
        ("timeout_seconds = 75", ["--timeout-second", "180"], 180),
    ],
)
def test_away_timeout_respects_explicit_preferences(tmp_path, configured, argv, expected):
    parser = build_argument_parser()
    argv = ["--away-minutes", "10", *argv]
    args = parser.parse_args(argv)
    apply_user_defaults(args, load_user_config(config_file(tmp_path, configured)))
    _configure_away_mode(args, argv, parser)
    assert args.timeout_seconds == expected


def test_cli_loads_preferences_before_readiness_without_provider_calls(tmp_path, monkeypatch):
    from ai_provider import repo_coding_assistant as cli

    path = config_file(tmp_path, 'quality = "high"\ntimeout_seconds = 75')
    observed = []

    def readiness(args, repo_root):
        observed.append((args.quality, args.timeout_seconds, repo_root))
        return 0

    monkeypatch.setattr(cli, "_print_fallback_readiness", readiness)
    assert (
        cli.main(
            [
                "--repo-root",
                str(tmp_path),
                "--user-config",
                str(path),
                "--fallback-readiness",
            ]
        )
        == 0
    )
    assert observed == [("high", 75.0, tmp_path)]
