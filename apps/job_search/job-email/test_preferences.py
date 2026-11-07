"""Preference filter contracts; all fixtures are synthetic."""

from __future__ import annotations

from models import EmploymentType, JobVacancy, WorkMode
from preferences import JobPreferences, check_preferences


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
    vague = vacancy(work_mode=WorkMode.UNSPECIFIED, employment_type=EmploymentType.UNSPECIFIED)
    prefs = JobPreferences(locations=("berlin",), remote_ok=False, employment_types=("b2b",))
    assert check_preferences(prefs, vague) == (True, ())


def test_employment_type_excluded_when_known():
    prefs = JobPreferences(employment_types=("permanent",))
    assert check_preferences(prefs, vacancy()) == (False, ("employment_type_excluded",))
    prefs = JobPreferences(employment_types=("b2b",))
    assert check_preferences(prefs, vacancy())[0] is True
