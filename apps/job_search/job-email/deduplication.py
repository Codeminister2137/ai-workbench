"""Deterministic vacancy normalization and duplicate detection.

Prevents processing or applying to the same vacancy multiple times across discovery runs.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence

from models import JobVacancy

_LEGAL_SUFFIXES = (
    r"\bsp\.?\s*z\s*o\.?\s*o\.?\b",
    r"\bs\.?a\.?\b",
    r"\binc\.?\b",
    r"\bllc\.?\b",
    r"\bltd\.?\b",
    r"\bgmbh\.?\b",
    r"\bcorp\.?\b",
    r"\bco\.?\b",
)

_SUFFIX_REGEX = re.compile("|".join(_LEGAL_SUFFIXES), flags=re.IGNORECASE)
_NON_ALPHANUM_REGEX = re.compile(r"[^a-z0-9]+")


def normalize_entity_name(name: str) -> str:
    """Normalize a company or organization name by stripping legal forms and punctuation."""
    cleaned = _SUFFIX_REGEX.sub("", name.lower())
    cleaned = _NON_ALPHANUM_REGEX.sub(" ", cleaned).strip()
    return cleaned


def normalize_job_title(title: str) -> str:
    """Normalize common title variations into canonical forms."""
    text = title.lower()
    # Normalize senior / junior / mid prefixes and punctuation
    text = re.sub(r"\bsr\.?\b", "senior", text)
    text = re.sub(r"\bjr\.?\b", "junior", text)
    text = re.sub(r"\bdev\b", "developer", text)
    cleaned = _NON_ALPHANUM_REGEX.sub(" ", text).strip()
    return cleaned


def compute_duplicate_key(company: str, title: str, location: str) -> str:
    """Generate a deterministic signature for deduplicating vacancies."""
    norm_company = normalize_entity_name(company)
    norm_title = normalize_job_title(title)
    norm_location = _NON_ALPHANUM_REGEX.sub(" ", location.lower()).strip()
    payload = f"{norm_company}|{norm_title}|{norm_location}".encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def is_duplicate_vacancy(
    vacancy: JobVacancy,
    existing_vacancies: Sequence[JobVacancy],
) -> bool:
    """Check if a vacancy matches any existing vacancy by key or explicit identifiers."""
    key = vacancy.duplicate_key or compute_duplicate_key(
        vacancy.company, vacancy.title, vacancy.location
    )
    for existing in existing_vacancies:
        existing_key = existing.duplicate_key or compute_duplicate_key(
            existing.company, existing.title, existing.location
        )
        if key == existing_key:
            return True
        if (
            vacancy.source_url
            and existing.source_url
            and vacancy.source_url.strip() == existing.source_url.strip()
        ):
            return True
    return False


def deduplicate_vacancies(
    vacancies: Sequence[JobVacancy],
) -> tuple[JobVacancy, ...]:
    """Return a deduplicated sequence of vacancies preserving the first occurrence."""
    seen_keys: set[str] = set()
    seen_urls: set[str] = set()
    result: list[JobVacancy] = []

    for vacancy in vacancies:
        key = vacancy.duplicate_key or compute_duplicate_key(
            vacancy.company, vacancy.title, vacancy.location
        )
        url = vacancy.source_url.strip() if vacancy.source_url else None
        if key in seen_keys or (url and url in seen_urls):
            continue
        seen_keys.add(key)
        if url:
            seen_urls.add(url)
        # Ensure the duplicate_key is set on the normalized record
        if not vacancy.duplicate_key:
            from dataclasses import replace

            vacancy = replace(vacancy, duplicate_key=key)
        result.append(vacancy)

    return tuple(result)
