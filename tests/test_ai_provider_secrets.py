from __future__ import annotations

import os

from ai_provider.secrets import load_dotenv, parse_dotenv_lines


def test_parse_dotenv_lines_skips_noise() -> None:
    text = "\n".join(
        [
            "# comment",
            "",
            "VALID_KEY=fake-value-1",
            "QUOTED='fake-value-2'",
            'DQUOTED="fake-value-3"',
            "EMPTY=",
            "NOEQUALS",
            "BAD NAME=x",
            "  SPACED  =  fake-value-4  ",
        ]
    )
    parsed = parse_dotenv_lines(text)
    assert parsed == {
        "VALID_KEY": "fake-value-1",
        "QUOTED": "fake-value-2",
        "DQUOTED": "fake-value-3",
        "EMPTY": "",
        "SPACED": "fake-value-4",
    }


def test_load_dotenv_returns_names_only(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("FAKE_ROUTE_EVAL_KEY=fake-secret\n", encoding="utf-8")
    monkeypatch.delenv("FAKE_ROUTE_EVAL_KEY", raising=False)
    loaded = load_dotenv(tmp_path)
    assert loaded == ("FAKE_ROUTE_EVAL_KEY",)
    assert "fake-secret" not in loaded
    assert os.environ["FAKE_ROUTE_EVAL_KEY"] == "fake-secret"


def test_load_dotenv_missing_store_is_empty(tmp_path) -> None:
    assert load_dotenv(tmp_path) == ()


def test_load_dotenv_existing_env_wins_by_default(tmp_path, monkeypatch) -> None:
    (tmp_path / ".env").write_text("FAKE_KEEP_KEY=store-value\n", encoding="utf-8")
    monkeypatch.setenv("FAKE_KEEP_KEY", "ambient-value")
    assert load_dotenv(tmp_path) == ()
    assert os.environ["FAKE_KEEP_KEY"] == "ambient-value"
    assert load_dotenv(tmp_path, override=True) == ("FAKE_KEEP_KEY",)
    assert os.environ["FAKE_KEEP_KEY"] == "store-value"


def test_parse_dotenv_lines_export_prefix() -> None:
    text = "\n".join(
        [
            "export FOO=bar",
            "export  FOO = spaced",
        ]
    )
    parsed = parse_dotenv_lines(text)
    assert parsed["FOO"] == "spaced"


def test_parse_dotenv_lines_inline_comment_kept() -> None:
    parsed = parse_dotenv_lines("KEY=value # keep me")
    assert parsed["KEY"] == "value # keep me"


def test_parse_dotenv_lines_duplicate_last_wins() -> None:
    text = "\n".join(["DUP=first", "DUP=second"])
    parsed = parse_dotenv_lines(text)
    assert parsed["DUP"] == "second"


def test_parse_dotenv_lines_bare_export_skipped() -> None:
    parsed = parse_dotenv_lines("export")
    assert parsed == {}
