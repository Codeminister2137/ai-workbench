"""Private candidate profile loading from local TOML.

The real profile lives at ``data/profiles/candidate.toml`` (git-ignored,
never committed) and is hand-maintained by the owner. Loading is strict:
unknown keys or statuses raise, because a silently misread profile would
corrupt matching, tailoring, and sending. See ``candidate.toml.example``.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from models import CandidateProfile, EvidenceStatus, SkillEvidence

PROFILE_KEYS = frozenset(
    {
        "applicant_name",
        "applicant_location",
        "applicant_summary",
        "portfolio_url",
        "linkedin_url",
        "skills",
    }
)
SKILL_KEYS = frozenset({"name", "status", "notes", "sources", "source_kinds"})


def default_profile_path() -> Path:
    """Return the repo-local private profile path (ignored by git)."""
    return Path(__file__).resolve().parents[3] / "data" / "profiles" / "candidate.toml"


def load_profile(path: Path) -> CandidateProfile:
    """Load and strictly validate a candidate profile from TOML."""
    with open(path, "rb") as handle:
        raw = tomllib.load(handle)
    unknown = sorted(set(raw) - PROFILE_KEYS)
    if unknown:
        raise ValueError(f"unknown profile keys: {unknown}")
    skills: dict[str, SkillEvidence] = {}
    for entry in raw.get("skills", []):
        if not isinstance(entry, dict):
            raise ValueError("each [[skills]] entry must be a table")
        unknown_skill = sorted(set(entry) - SKILL_KEYS)
        if unknown_skill:
            raise ValueError(f"unknown skill keys: {unknown_skill}")
        name = entry.get("name", "")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("each [[skills]] entry needs a nonempty name")
        status_raw = entry.get("status", "")
        try:
            status = EvidenceStatus(status_raw)
        except ValueError:
            raise ValueError(f"unknown evidence status: {status_raw!r}") from None
        notes = entry.get("notes", "")
        sources = entry.get("sources", [])
        kinds = entry.get("source_kinds", [])
        if not isinstance(notes, str):
            raise ValueError(f"notes must be a string for skill {name!r}")
        if not isinstance(sources, list) or not all(isinstance(s, str) for s in sources):
            raise ValueError(f"sources must be a string list for skill {name!r}")
        if not isinstance(kinds, list) or not all(isinstance(k, str) for k in kinds):
            raise ValueError(f"source_kinds must be a string list for skill {name!r}")
        skills[name] = SkillEvidence(
            name,
            status,
            notes=notes,
            evidence_sources=tuple(sources),
            source_kinds=tuple(kinds),
        )
    missing = [key for key in PROFILE_KEYS - {"skills"} if key not in raw]
    if missing:
        raise ValueError(f"missing profile keys: {sorted(missing)}")
    return CandidateProfile(
        applicant_name=raw["applicant_name"],
        applicant_location=raw["applicant_location"],
        applicant_summary=raw["applicant_summary"],
        portfolio_url=raw["portfolio_url"],
        linkedin_url=raw["linkedin_url"],
        skills=skills,
    )
