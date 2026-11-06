"""Fail-loud triage verdict application (replaces one-off apply scripts)."""

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/triage-apply.py"
SPEC = importlib.util.spec_from_file_location("triage_apply", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)


def _ledger(tmp_path: Path) -> Path:
    path = tmp_path / "ledger.md"
    path.write_text(
        "# Ledger\n"
        "\n"
        "- Widget frobnicator leaks **UNREVIEWED**\n"
        "- Gadget allocator hangs **UNREVIEWED**\n",
        encoding="utf-8",
    )
    return path


def _verdicts(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "verdicts.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_happy_path_replaces_marker(tmp_path, capsys) -> None:
    ledger = _ledger(tmp_path)
    verdicts = _verdicts(
        tmp_path,
        {
            "Widget frobnicator": "FALSE POSITIVE 2026-11-06 (reason)",
            "Gadget allocator": "REAL 2026-11-06 (reason)",
        },
    )
    assert helper.main(["--ledger", str(ledger), "--verdicts", str(verdicts)]) == 0
    text = ledger.read_text(encoding="utf-8")
    assert "**UNREVIEWED**" not in text
    assert "**FALSE POSITIVE 2026-11-06 (reason)**" in text
    assert "**REAL 2026-11-06 (reason)**" in text
    assert "applied 2 verdicts" in capsys.readouterr().out


def test_miss_aborts_without_writing(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    before = ledger.read_bytes()
    verdicts = _verdicts(tmp_path, {"No such title": "REAL (x)"})
    assert helper.main(["--ledger", str(ledger), "--verdicts", str(verdicts)]) == 1
    assert ledger.read_bytes() == before


def test_ambiguous_title_aborts_without_writing(tmp_path) -> None:
    ledger = tmp_path / "ledger.md"
    ledger.write_text(
        "- Widget alpha **UNREVIEWED**\n- Widget beta **UNREVIEWED**\n",
        encoding="utf-8",
    )
    before = ledger.read_bytes()
    verdicts = _verdicts(tmp_path, {"Widget": "REAL (x)"})
    assert helper.main(["--ledger", str(ledger), "--verdicts", str(verdicts)]) == 1
    assert ledger.read_bytes() == before


def test_dry_run_checks_without_writing(tmp_path, capsys) -> None:
    ledger = _ledger(tmp_path)
    before = ledger.read_bytes()
    verdicts = _verdicts(tmp_path, {"Widget frobnicator": "REAL (x)"})
    assert helper.main(["--ledger", str(ledger), "--verdicts", str(verdicts), "--dry-run"]) == 0
    assert ledger.read_bytes() == before
    assert "would apply 1 verdict" in capsys.readouterr().out


def test_rerun_after_apply_fails_loud(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    verdicts = _verdicts(tmp_path, {"Widget frobnicator": "REAL (x)"})
    assert helper.main(["--ledger", str(ledger), "--verdicts", str(verdicts)]) == 0
    assert helper.main(["--ledger", str(ledger), "--verdicts", str(verdicts)]) == 1


def test_invalid_verdicts_file_rejected(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    bad = tmp_path / "bad.json"
    bad.write_text('{"title": ""}', encoding="utf-8")
    assert helper.main(["--ledger", str(ledger), "--verdicts", str(bad)]) == 1
    bad.write_text("not json", encoding="utf-8")
    assert helper.main(["--ledger", str(ledger), "--verdicts", str(bad)]) == 1
