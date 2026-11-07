from __future__ import annotations

import os
from pathlib import Path

import pytest
from ai_provider.secrets import (
    _iter_assignments,
    load_dotenv,
    parse_dotenv_lines,
    read_dotenv_values,
    read_secret_key,
)


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


def test_read_secret_key_happy_path(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("MY_KEY=secret-value\n", encoding="utf-8")
    assert read_secret_key(env_file, "MY_KEY", label="my-label") == "secret-value"


def test_read_secret_key_missing_file_raises(tmp_path: Path) -> None:
    missing = tmp_path / ".env"
    with pytest.raises(ValueError) as excinfo:
        read_secret_key(missing, "MY_KEY", label="my-label")
    assert "my-label" in str(excinfo.value)
    assert str(missing) in str(excinfo.value)


def test_read_secret_key_missing_key_raises(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("OTHER=1\n", encoding="utf-8")
    with pytest.raises(ValueError) as excinfo:
        read_secret_key(env_file, "MY_KEY", label="my-label")
    assert "my-label" in str(excinfo.value)
    assert str(env_file) in str(excinfo.value)


def test_read_secret_key_empty_value_raises(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("MY_KEY=\n", encoding="utf-8")
    with pytest.raises(ValueError) as excinfo:
        read_secret_key(env_file, "MY_KEY", label="my-label")
    assert "my-label" in str(excinfo.value)
    assert str(env_file) in str(excinfo.value)


def test_read_secret_key_quoted_empty_raises(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text('MY_KEY=""\n', encoding="utf-8")
    with pytest.raises(ValueError) as excinfo:
        read_secret_key(env_file, "MY_KEY", label="my-label")
    assert "my-label" in str(excinfo.value)
    assert str(env_file) in str(excinfo.value)


def test_read_secret_key_duplicate_key_raises(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("MY_KEY=one\nMY_KEY=two\n", encoding="utf-8")
    with pytest.raises(ValueError) as excinfo:
        read_secret_key(env_file, "MY_KEY", label="my-label")
    assert "my-label" in str(excinfo.value)
    assert str(env_file) in str(excinfo.value)


def test_read_dotenv_values_filtering(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("A=1\nB=2\nC=3\n", encoding="utf-8")
    assert read_dotenv_values(env_file, ["A", "C"]) == {"A": "1", "C": "3"}
    assert read_dotenv_values(env_file) == {"A": "1", "B": "2", "C": "3"}


def test_read_dotenv_values_last_wins(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("DUP=first\nDUP=second\n", encoding="utf-8")
    assert read_dotenv_values(env_file) == {"DUP": "second"}


def test_read_dotenv_values_keeps_empty(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("EMPTY=\nFULL=x\n", encoding="utf-8")
    values = read_dotenv_values(env_file)
    assert values == {"EMPTY": "", "FULL": "x"}
    assert "EMPTY" in values


def test_read_dotenv_values_missing_empty(tmp_path: Path) -> None:
    assert read_dotenv_values(tmp_path / "nope.env") == {}


def test_read_dotenv_values_missing_raise(tmp_path: Path) -> None:
    missing = tmp_path / "nope.env"
    with pytest.raises(FileNotFoundError) as excinfo:
        read_dotenv_values(missing, missing="raise")
    assert str(missing) in str(excinfo.value)


def test_pinned_quote_whitespace_parity(tmp_path: Path) -> None:
    pinned = '  KEY  =  "  secret-value  "  '
    assert parse_dotenv_lines(pinned) == {"KEY": "  secret-value  "}
    assert list(_iter_assignments(pinned)) == [("KEY", "  secret-value  ")]
    env_file = tmp_path / ".env"
    env_file.write_text(pinned + "\n", encoding="utf-8")
    assert read_secret_key(env_file, "KEY", label="lbl") == "  secret-value  "
    assert read_dotenv_values(env_file) == {"KEY": "  secret-value  "}


def test_quote_whitespace_export_parity(tmp_path: Path) -> None:
    exported = 'export KEY="  secret-value  "'
    assert parse_dotenv_lines(exported) == {"KEY": "  secret-value  "}
    assert list(_iter_assignments(exported)) == [("KEY", "  secret-value  ")]
    env_file = tmp_path / ".env"
    env_file.write_text(exported + "\n", encoding="utf-8")
    assert read_secret_key(env_file, "KEY", label="lbl") == "  secret-value  "
    assert read_dotenv_values(env_file) == {"KEY": "  secret-value  "}


def test_parse_dotenv_lines_iter_assignments_grammar_parity() -> None:
    text = "\n".join(
        [
            "# comment",
            "",
            "VALID=1",
            "QUOTED='a'",
            'DQUOTED="b"',
            "EMPTY=",
            "NOEQUALS",
            "BAD NAME=x",
            "  SPACED  =  v  ",
            "export EXP=val",
            "export  EXP2  =  spaced  ",
            "export",
            "DUP=first",
            "DUP=second",
            "KEY=value # keep me",
            '  KEY  =  "  secret-value  "  ',
            "SINGLE='  secret-value  '",
        ]
    )
    expected: dict[str, str] = {}
    for name, value in _iter_assignments(text):
        expected[name] = value
    assert parse_dotenv_lines(text) == expected
    # Spot-check pinned and export rows through both APIs.
    assert parse_dotenv_lines('  KEY  =  "  secret-value  "  ')["KEY"] == "  secret-value  "
    assert dict(_iter_assignments('export KEY="  secret-value  "'))["KEY"] == "  secret-value  "
