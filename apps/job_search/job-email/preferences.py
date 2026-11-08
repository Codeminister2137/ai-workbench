"""Owner job preferences and hard-exclude vacancy filtering.

Deterministic only: decides whether a vacancy is worth matching at all,
before any AI-heavy analysis. Salary parsing is deliberately out of scope
(compensation is free text); that stays an open question.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from models import EmploymentType, JobVacancy, WorkMode


@dataclass(frozen=True, slots=True)
class JobPreferences:
    """Owner-stated job search preferences; empty collections mean no constraint."""

    locations: tuple[str, ...] = ()
    remote_ok: bool = True
    excluded_companies: tuple[str, ...] = ()
    title_must_include: tuple[str, ...] = ()
    employment_types: tuple[str, ...] = field(default_factory=tuple)


def _normalized(values: tuple[str, ...]) -> set[str]:
    return {value.strip().casefold() for value in values if value.strip()}


def check_preferences(
    preferences: JobPreferences, vacancy: JobVacancy
) -> tuple[bool, tuple[str, ...]]:
    """Return (passes, exclusion_reasons) for a vacancy against preferences."""
    reasons: list[str] = []
    if _normalized(preferences.excluded_companies) and (
        vacancy.company.strip().casefold() in _normalized(preferences.excluded_companies)
    ):
        reasons.append("excluded_company")
    required_words = _normalized(preferences.title_must_include)
    title = vacancy.title.strip().casefold()
    if required_words and not all(word in title for word in required_words):
        reasons.append("title_missing_required_words")
    wanted_types = _normalized(preferences.employment_types)
    if (
        wanted_types
        and vacancy.employment_type is not EmploymentType.UNSPECIFIED
        and vacancy.employment_type.value.casefold() not in wanted_types
    ):
        reasons.append("employment_type_excluded")
    if vacancy.work_mode is WorkMode.REMOTE and not preferences.remote_ok:
        reasons.append("remote_excluded")
    places = _normalized(preferences.locations)
    location = vacancy.location.strip().casefold()
    if (
        places
        and location
        and vacancy.work_mode is not WorkMode.REMOTE
        and not any(place in location or location in place for place in places)
    ):
        reasons.append("location_excluded")
    return (not reasons, tuple(reasons))
