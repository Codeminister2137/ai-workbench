"""Tests for scripts/validate-p7-intake.py."""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = ROOT / "scripts" / "validate-p7-intake.py"


def _load():
    spec = importlib.util.spec_from_file_location("validate_p7_intake", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _example() -> dict:
    return json.loads(
        (ROOT / "company-site" / "intake" / "example.json").read_text(encoding="utf-8")
    )


def _write(tmp_path: Path, doc: dict) -> Path:
    path = tmp_path / "intake.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def test_example_is_valid_with_pinned_date(tmp_path: Path) -> None:
    mod = _load()
    result = mod.validate_file(
        _write(tmp_path, _example()), as_of=datetime(2026, 11, 13, tzinfo=UTC)
    )
    assert result["valid"] is True, result["errors"]
    assert result["errors"] == []
    # The example embeds a contact email in success_criteria: warning, not error.
    assert any("email/phone" in item for item in result["warnings"])


def test_structural_rejections(tmp_path: Path) -> None:
    mod = _load()
    as_of = datetime(2026, 11, 13, tzinfo=UTC)
    base = _example()

    def check(mutate, needle: str) -> None:
        doc = json.loads(json.dumps(base))
        mutate(doc)
        result = mod.validate_file(_write(tmp_path, doc), as_of=as_of)
        assert result["valid"] is False
        assert any(needle in err for err in result["errors"]), result["errors"]

    check(lambda doc: doc.pop("goal_summary"), "missing required")
    check(lambda doc: doc.update(extra_key=1), "extra top-level key")
    check(lambda doc: doc.update(format_version="2.0.0"), "format_version")
    check(lambda doc: doc.update(project_id="BAD ID!"), "project_id")
    check(lambda doc: doc.update(created_at="yesterday"), "created_at")
    check(lambda doc: doc.update(budget_range="millions"), "budget_range")
    check(lambda doc: doc["timeline"].update(deadline="next friday"), "deadline")
    check(lambda doc: doc["client_contact"].update(email="not-an-email"), "email")
    check(lambda doc: doc["client_contact"].update(phone="123"), "phone")
    check(lambda doc: doc["features_in"].clear(), "features_in")
    check(lambda doc: doc.update(goal_summary="  padded  "), "trimmed")


def test_semantic_rejections(tmp_path: Path) -> None:
    mod = _load()
    as_of = datetime(2026, 11, 13, tzinfo=UTC)
    base = _example()

    def check(mutate, needle: str) -> None:
        doc = json.loads(json.dumps(base))
        mutate(doc)
        result = mod.validate_file(_write(tmp_path, doc), as_of=as_of)
        assert result["valid"] is False
        assert any(needle in err for err in result["errors"]), result["errors"]

    check(
        lambda doc: doc["features_out"].append(doc["features_in"][0]),
        "scope overlap",
    )
    filler = json.loads(json.dumps(base))
    filler["goal_summary"] = "I want a website"
    result = mod.validate_file(_write(tmp_path, filler), as_of=as_of)
    assert result["valid"] is False
    assert any("filler" in err for err in result["errors"])
    check(lambda doc: doc["timeline"].update(deadline="2026-11-02"), "48h")
    check(
        lambda doc: doc["timeline"].update(deadline="2027-06-01", urgency="urgent"),
        "contradictory",
    )
    check(lambda doc: doc.update(problem_statement="my api_key: sk-fake12345"), "secret")


def test_expiry_and_weak_criteria(tmp_path: Path) -> None:
    mod = _load()
    old = _example()
    result = mod.validate_file(_write(tmp_path, old), as_of=datetime(2026, 12, 15, tzinfo=UTC))
    assert result["valid"] is False
    assert any("expired" in err for err in result["errors"])

    weak = _example()
    weak["success_criteria"] = ["Nice overall feeling today"]
    result = mod.validate_file(_write(tmp_path, weak), as_of=datetime(2026, 11, 13, tzinfo=UTC))
    assert result["valid"] is True
    assert any("untestable" in item for item in result["warnings"])


def test_oversize_and_malformed_rejected(tmp_path: Path) -> None:
    mod = _load()
    big = tmp_path / "big.json"
    big.write_bytes(b'{"format_version": "' + b"x" * (32 * 1024) + b'"}')
    result = mod.validate_file(big)
    assert result["valid"] is False
    assert any("32 KB" in err or "exceeds" in err for err in result["errors"])

    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    result = mod.validate_file(broken)
    assert result["valid"] is False

    missing = tmp_path / "missing.json"
    result = mod.validate_file(missing)
    assert result["valid"] is False
    assert any("unreadable" in err for err in result["errors"])
