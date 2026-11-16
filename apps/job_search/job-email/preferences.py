"""Owner job preferences and hard-exclude vacancy filtering.

Deterministic only: decides whether a vacancy is worth matching at all,
before any AI-heavy analysis. Salary parsing is deliberately out of scope
(compensation is free text); that stays an open question.

The owner's live preferences live at ``data/profiles/job-preferences.toml``
(git-ignored, never committed); see ``job-preferences.toml.example``.
All keys are optional; unknown keys raise so typos fail loud.
"""

from __future__ import annotations

import tomllib
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from models import EmploymentType, JobVacancy, WorkMode

PREFS_KEYS = frozenset(
    {
        "locations",
        "remote_ok",
        "excluded_companies",
        "title_must_include",
        "employment_types",
    }
)


@dataclass(frozen=True, slots=True)
class JobPreferences:
    """Owner-stated job search preferences; empty collections mean no constraint."""

    locations: tuple[str, ...] = ()
    remote_ok: bool = True
    excluded_companies: tuple[str, ...] = ()
    title_must_include: tuple[str, ...] = ()
    employment_types: tuple[str, ...] = field(default_factory=tuple)


def default_preferences_path() -> Path:
    """Return the repo-local private preferences path (ignored by git)."""
    return Path(__file__).resolve().parents[3] / "data" / "profiles" / "job-preferences.toml"


def load_preferences_file(path: Path) -> JobPreferences:
    """Load owner preferences from TOML; all keys optional, unknown keys rejected."""

    def _str_list(raw: object, key: str) -> tuple[str, ...]:
        if raw is None:
            return ()
        if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
            raise ValueError(f"{key} must be a string list")
        return tuple(raw)

    with open(path, "rb") as handle:
        raw = tomllib.load(handle)
    unknown = sorted(set(raw) - PREFS_KEYS)
    if unknown:
        raise ValueError(f"unknown preferences keys: {unknown}")
    remote_ok = raw.get("remote_ok", True)
    if not isinstance(remote_ok, bool):
        raise ValueError("remote_ok must be a boolean")
    return JobPreferences(
        locations=_str_list(raw.get("locations"), "locations"),
        remote_ok=remote_ok,
        excluded_companies=_str_list(raw.get("excluded_companies"), "excluded_companies"),
        title_must_include=_str_list(raw.get("title_must_include"), "title_must_include"),
        employment_types=_str_list(raw.get("employment_types"), "employment_types"),
    )


def _fold(text: str) -> str:
    """Casefold plus diacritic stripping so Krakow matches Kraków."""
    decomposed = unicodedata.normalize("NFKD", text.strip().casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _normalized(values: tuple[str, ...]) -> set[str]:
    return {_fold(value) for value in values if value.strip()}


def check_preferences(
    preferences: JobPreferences, vacancy: JobVacancy
) -> tuple[bool, tuple[str, ...]]:
    """Return (passes, exclusion_reasons) for a vacancy against preferences."""
    reasons: list[str] = []
    if _normalized(preferences.excluded_companies) and (
        _fold(vacancy.company) in _normalized(preferences.excluded_companies)
    ):
        reasons.append("excluded_company")
    required_words = _normalized(preferences.title_must_include)
    title = _fold(vacancy.title)
    if required_words and not all(word in title for word in required_words):
        reasons.append("title_missing_required_words")
    wanted_types = _normalized(preferences.employment_types)
    if (
        wanted_types
        and vacancy.employment_type is not EmploymentType.UNSPECIFIED
        and _fold(vacancy.employment_type.value) not in wanted_types
    ):
        reasons.append("employment_type_excluded")
    if vacancy.work_mode is WorkMode.REMOTE and not preferences.remote_ok:
        reasons.append("remote_excluded")
    places = _normalized(preferences.locations)
    location = _fold(vacancy.location)
    if (
        places
        and location
        and vacancy.work_mode is not WorkMode.REMOTE
        and not any(place in location or location in place for place in places)
    ):
        reasons.append("location_excluded")
    return (not reasons, tuple(reasons))
