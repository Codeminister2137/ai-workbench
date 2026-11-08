"""Profile loading contracts; all fixtures are synthetic."""

from __future__ import annotations

from pathlib import Path

import pytest
from models import EvidenceStatus
from profiles import default_profile_path, load_profile

VALID_TOML = """
applicant_name = "Synthetic Applicant"
applicant_location = "Nowhere"
applicant_summary = "Synthetic."
portfolio_url = "https://example.invalid"
linkedin_url = "https://example.invalid"

[[skills]]
name = "Python"
status = "demonstrated"
notes = "Backend work."
sources = ["cv"]
source_kinds = ["cv", "github"]
"""


def write_profile(tmp_path: Path, text: str = VALID_TOML) -> Path:
    path = tmp_path / "candidate.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_load_valid_profile(tmp_path):
    profile = load_profile(write_profile(tmp_path))
    assert profile.applicant_name == "Synthetic Applicant"
    assert profile.skills["Python"].status is EvidenceStatus.DEMONSTRATED
    assert profile.skills["Python"].source_kinds == ("cv", "github")


def test_unknown_top_level_key_rejected(tmp_path):
    bad = VALID_TOML.replace(
        'linkedin_url = "https://example.invalid"',
        'linkedin_url = "https://example.invalid"\nnickname = "x"',
    )
    with pytest.raises(ValueError, match="unknown profile keys"):
        load_profile(write_profile(tmp_path, bad))


def test_unknown_status_rejected(tmp_path):
    bad = VALID_TOML.replace('status = "demonstrated"', 'status = "wizard"')
    with pytest.raises(ValueError, match="unknown evidence status"):
        load_profile(write_profile(tmp_path, bad))


def test_unknown_source_kind_rejected_through_model(tmp_path):
    bad = VALID_TOML.replace('["cv", "github"]', '["cv", "scrape"]')
    with pytest.raises(ValueError, match="unknown evidence source kinds"):
        load_profile(write_profile(tmp_path, bad))


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_profile(tmp_path / "absent.toml")


def test_default_path_is_ignored_data_dir():
    path = default_profile_path()
    assert path.parts[-3:] == ("data", "profiles", "candidate.toml")
