"""Vacancy shortlist CLI contracts; all fixtures are synthetic."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import vacancies_cli
from vacancies_cli import main


@pytest.fixture(autouse=True)
def _no_ambient_prefs(tmp_path, monkeypatch):
    """Neutralize the owner's real prefs file; tests set prefs explicitly."""
    monkeypatch.setattr(
        vacancies_cli, "default_preferences_path", lambda: tmp_path / "absent-prefs.toml"
    )


PROFILE_TOML = """
applicant_name = "Synthetic Applicant"
applicant_location = "Nowhere"
applicant_summary = "Synthetic."
portfolio_url = "https://example.invalid"
linkedin_url = "https://example.invalid"

[[skills]]
name = "Python"
status = "demonstrated"
source_kinds = ["cv"]
"""

EXPORT_ROWS = [
    {
        "job_id": "a1",
        "company": "Example Corp",
        "title": "Senior Python Engineer",
        "location": "Warsaw, PL",
        "description": "Python backend.",
    },
    {
        "job_id": "b2",
        "company": "Other Inc",
        "title": "Java Developer",
        "location": "Berlin, DE",
        "description": "Java backend.",
    },
]


def write_inputs(tmp_path: Path):
    profile = tmp_path / "candidate.toml"
    profile.write_text(PROFILE_TOML, encoding="utf-8")
    export = tmp_path / "export.json"
    export.write_text(json.dumps(EXPORT_ROWS), encoding="utf-8")
    return export, profile


def test_shortlist_ranks_and_counts(tmp_path, capsys):
    export, profile = write_inputs(tmp_path)
    assert main([str(export), "--profile", str(profile)]) == 0
    out = capsys.readouterr().out
    assert "Senior Python Engineer at Example Corp" in out
    assert "2 shown, 0 excluded by preferences" in out


def test_preferences_exclude(tmp_path, capsys):
    export, profile = write_inputs(tmp_path)
    assert main([str(export), "--profile", str(profile), "--location", "warsaw"]) == 0
    out = capsys.readouterr().out
    assert "1 shown, 1 excluded by preferences" in out


def test_missing_export_fails_cleanly(tmp_path, capsys):
    _, profile = write_inputs(tmp_path)
    assert main([str(tmp_path / "absent.json"), "--profile", str(profile)]) == 1
    assert "error:" in capsys.readouterr().err


def test_prefs_file_filters(tmp_path, capsys):
    export, profile = write_inputs(tmp_path)
    prefs = tmp_path / "prefs.toml"
    prefs.write_text('locations = ["warsaw"]\n', encoding="utf-8")
    assert main([str(export), "--profile", str(profile), "--prefs-file", str(prefs)]) == 0
    out = capsys.readouterr().out
    assert "1 shown, 1 excluded by preferences" in out


def test_cli_flags_override_prefs_file(tmp_path, capsys):
    export, profile = write_inputs(tmp_path)
    prefs = tmp_path / "prefs.toml"
    prefs.write_text('locations = ["warsaw"]\nremote_ok = false\n', encoding="utf-8")
    argv = [
        str(export),
        "--profile",
        str(profile),
        "--prefs-file",
        str(prefs),
        "--location",
        "berlin",
    ]
    assert main(argv) == 0
    out = capsys.readouterr().out
    assert "Java Developer at Other Inc" in out
    assert "1 shown, 1 excluded by preferences" in out


def test_missing_prefs_file_fails_cleanly(tmp_path, capsys):
    export, profile = write_inputs(tmp_path)
    argv = [str(export), "--profile", str(profile), "--prefs-file", str(tmp_path / "absent.toml")]
    assert main(argv) == 1
    assert "error:" in capsys.readouterr().err
