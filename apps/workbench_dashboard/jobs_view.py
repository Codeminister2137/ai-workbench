"""Job review endpoint backend (M3): vacancy in, match report out.

Builds a JobVacancy from posted JSON, runs preferences + the M2 match
core against the owner's private profile, and returns everything one
review screen needs. Read-only: no records are written.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any


def _job_email():
    """Import the hyphenated job-email modules by path (cached).

    Siblings import each other by plain top-level name, and nothing else
    in the dashboard process claims those names, so modules register
    under their real names.
    """
    if "jobemail_matcher" in sys.modules:
        cached = sys.modules["jobemail_matcher"]
        return cached, sys.modules["models"], sys.modules["preferences"], sys.modules["profiles"]
    root = Path(__file__).resolve().parents[2] / "apps" / "job_search" / "job-email"

    def load(name: str):
        spec = importlib.util.spec_from_file_location(name, root / f"{name}.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module

    # models first: every sibling imports it.
    load("models")
    load("evidence")
    load("preferences")
    load("profiles")
    matcher = load("matcher")
    sys.modules["jobemail_matcher"] = matcher
    return matcher, sys.modules["models"], sys.modules["preferences"], sys.modules["profiles"]


def review_vacancy(payload: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    """Validate posted JSON and return the review bundle.

    Raises ValueError on bad input and FileNotFoundError when the
    private candidate profile is absent.
    """
    matcher, models, preferences, profiles = _job_email()
    if not isinstance(payload, dict):
        raise ValueError("vacancy payload must be an object")
    title = str(payload.get("title") or "").strip()
    company = str(payload.get("company") or "").strip()
    if not title or not company:
        raise ValueError("title and company are required")
    try:
        work_mode = models.WorkMode(str(payload.get("work_mode") or "unspecified"))
    except ValueError:
        valid = sorted(member.value for member in models.WorkMode)
        raise ValueError(f"unknown work_mode; valid: {valid}") from None
    try:
        employment_type = models.EmploymentType(
            str(payload.get("employment_type") or "unspecified")
        )
    except ValueError:
        valid = sorted(member.value for member in models.EmploymentType)
        raise ValueError(f"unknown employment_type; valid: {valid}") from None
    required = payload.get("required_skills") or []
    preferred = payload.get("preferred_skills") or []
    if not isinstance(required, list) or not isinstance(preferred, list):
        raise ValueError("required_skills and preferred_skills must be arrays")
    vacancy = models.JobVacancy(
        id=str(payload.get("id") or "review-draft"),
        company=company,
        title=title,
        location=str(payload.get("location") or ""),
        work_mode=work_mode,
        employment_type=employment_type,
        required_skills=tuple(str(skill) for skill in required),
        preferred_skills=tuple(str(skill) for skill in preferred),
        experience_requirement=payload.get("experience_requirement"),
        source="dashboard-review",
    )
    prefs_path = repo_root / "data" / "profiles" / "job-preferences.toml"
    prefs = preferences.load_preferences_file(prefs_path) if prefs_path.is_file() else None
    passes, reasons = (True, ()) if prefs is None else preferences.check_preferences(prefs, vacancy)
    profile_path = repo_root / "data" / "profiles" / "candidate.toml"
    if not profile_path.is_file():
        raise FileNotFoundError(
            "candidate profile missing at data/profiles/candidate.toml; "
            "add it before reviewing matches"
        )
    profile = profiles.load_profile(profile_path)
    report = matcher.build_match_report(vacancy, profile)
    return {
        "vacancy": {
            "title": vacancy.title,
            "company": vacancy.company,
            "location": vacancy.location,
            "work_mode": vacancy.work_mode.value,
            "employment_type": vacancy.employment_type.value,
        },
        "preferences": {"passes": passes, "reasons": list(reasons)},
        "match": report.to_dict(),
    }
