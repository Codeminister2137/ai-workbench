"""Preference filter contracts; all fixtures are synthetic."""

from __future__ import annotations

import pytest
from models import EmploymentType, JobVacancy, WorkMode
from preferences import JobPreferences, check_preferences, load_preferences_file


def vacancy(**overrides):
    fields = {
        "id": "vac-prefs",
        "company": "Example Corp",
        "title": "Senior Python Engineer",
        "location": "Warsaw, PL",
        "work_mode": WorkMode.HYBRID,
        "employment_type": EmploymentType.B2B,
    }
    fields.update(overrides)
    return JobVacancy(**fields)


def test_empty_preferences_pass_everything():
    assert check_preferences(JobPreferences(), vacancy()) == (True, ())


def test_excluded_company_rejected_caseless():
    prefs = JobPreferences(excluded_companies=("example corp",))
    assert check_preferences(prefs, vacancy()) == (False, ("excluded_company",))


def test_title_must_include_all_words():
    prefs = JobPreferences(title_must_include=("python", "senior"))
    assert check_preferences(prefs, vacancy())[0] is True
    prefs = JobPreferences(title_must_include=("python", "staff"))
    assert check_preferences(prefs, vacancy()) == (False, ("title_missing_required_words",))


def test_remote_excluded_only_when_remote_not_ok():
    remote = vacancy(work_mode=WorkMode.REMOTE)
    assert check_preferences(JobPreferences(), remote)[0] is True
    assert check_preferences(JobPreferences(remote_ok=False), remote) == (
        False,
        ("remote_excluded",),
    )


def test_location_match_is_substring_caseless():
    prefs = JobPreferences(locations=("warsaw",))
    assert check_preferences(prefs, vacancy())[0] is True
    prefs = JobPreferences(locations=("berlin",))
    assert check_preferences(prefs, vacancy()) == (False, ("location_excluded",))


def test_unspecified_modes_pass_through():
    vague = vacancy(
        work_mode=WorkMode.UNSPECIFIED,
        employment_type=EmploymentType.UNSPECIFIED,
        location="",
    )
    prefs = JobPreferences(locations=("berlin",), remote_ok=False, employment_types=("b2b",))
    assert check_preferences(prefs, vague) == (True, ())


def test_employment_type_excluded_when_known():
    prefs = JobPreferences(employment_types=("permanent",))
    assert check_preferences(prefs, vacancy()) == (False, ("employment_type_excluded",))
    prefs = JobPreferences(employment_types=("b2b",))
    assert check_preferences(prefs, vacancy())[0] is True


def test_location_filters_unknown_modes_with_location():
    vague = vacancy(work_mode=WorkMode.UNSPECIFIED)
    prefs = JobPreferences(locations=("berlin",))
    assert check_preferences(prefs, vague) == (False, ("location_excluded",))


def test_location_match_ignores_diacritics():
    vacancy_pl = vacancy(location="Kraków, PL", work_mode=WorkMode.ONSITE)
    assert check_preferences(JobPreferences(locations=("krakow",)), vacancy_pl)[0] is True
    assert check_preferences(JobPreferences(locations=("kraków",)), vacancy_pl)[0] is True
    vacancy_ascii = vacancy(location="Krakow, PL", work_mode=WorkMode.ONSITE)
    assert check_preferences(JobPreferences(locations=("kraków",)), vacancy_ascii)[0] is True


def test_load_preferences_file_roundtrip(tmp_path):
    path = tmp_path / "job-preferences.toml"
    path.write_text(
        'locations = ["Warsaw"]\nremote_ok = false\nemployment_types = ["b2b"]\n',
        encoding="utf-8",
    )
    prefs = load_preferences_file(path)
    assert prefs == JobPreferences(
        locations=("Warsaw",), remote_ok=False, employment_types=("b2b",)
    )


def test_load_preferences_file_all_optional(tmp_path):
    path = tmp_path / "job-preferences.toml"
    path.write_text("# empty\n", encoding="utf-8")
    assert load_preferences_file(path) == JobPreferences()


def test_load_preferences_file_rejects_unknown_keys_and_types(tmp_path):
    path = tmp_path / "job-preferences.toml"
    path.write_text("salary_min = 10000\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown preferences keys"):
        load_preferences_file(path)
    path.write_text('locations = "Warsaw"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="must be a string list"):
        load_preferences_file(path)
    path.write_text('remote_ok = "yes"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="must be a boolean"):
        load_preferences_file(path)


def test_load_preferences_file_missing_raises(tmp_path):
    with pytest.raises(OSError):
        load_preferences_file(tmp_path / "absent.toml")
