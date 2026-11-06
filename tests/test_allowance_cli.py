"""Shared allowance CLI runner: one JSON wrapper for all native readers."""

import json

import pytest
from ai_provider import codex_usage, copilot_usage, kiro_usage
from ai_provider.native_account_usage import run_allowance_cli


def _reader(status, seen=None):
    def read(*, timeout_seconds=15):
        if seen is not None:
            seen.append(timeout_seconds)
        if timeout_seconds <= 0:
            raise ValueError("bad timeout")
        return {"status": status, "source": "stub"}

    return read


def test_available_exits_zero_with_json(capsys) -> None:
    code = run_allowance_cli(description="stub", reader=_reader("available"), argv=[])
    assert code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "available"


def test_unavailable_exits_one(capsys) -> None:
    code = run_allowance_cli(description="stub", reader=_reader("timeout"), argv=[])
    assert code == 1
    assert json.loads(capsys.readouterr().out)["status"] == "timeout"


def test_timeout_flag_reaches_reader() -> None:
    seen: list = []
    code = run_allowance_cli(
        description="stub", reader=_reader("available", seen), argv=["--timeout-seconds", "7"]
    )
    assert code == 0
    assert seen == [7.0]


def test_invalid_timeout_exits_parser_error(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        run_allowance_cli(
            description="stub", reader=_reader("available"), argv=["--timeout-seconds", "-1"]
        )
    assert exc.value.code == 2


@pytest.mark.parametrize(
    ("module", "reader_name"),
    [
        (codex_usage, "read_codex_allowance"),
        (copilot_usage, "read_copilot_allowance"),
        (kiro_usage, "read_kiro_allowance"),
    ],
)
def test_usage_mains_delegate_to_shared_runner(module, reader_name, monkeypatch, capsys) -> None:
    monkeypatch.setattr(module, reader_name, _reader("available"))
    assert module.main([]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "available"
