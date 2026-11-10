"""Vendor contact adapters (Prospeo, Apollo) behind the ContactSource interface.

Each adapter resolves at most one proposal per vacancy and returns None
when it has nothing: missing key, missing person/domain signals, vendor
errors, or transport failures. Keys come from the environment first,
then the repo-root ``.env``; keys are never logged. Trial bounds and
live shapes are recorded in the trial receipt, never the emails.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from contacts import (
    ContactProposal,
    ContactRegistry,
    ContactSource,
    ManualContactSource,
    is_generic_inbox,
)
from models import JobVacancy

FREEMAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "outlook.com",
        "hotmail.com",
        "live.com",
        "yahoo.com",
        "wp.pl",
        "o2.pl",
        "interia.pl",
        "onet.pl",
        "tlen.pl",
        "poczta.fm",
        "proton.me",
        "protonmail.com",
        "icloud.com",
    }
)

APOLLO_MATCH_URL = "https://api.apollo.io/api/v1/people/match"
PROSPEO_ENRICH_URL = "https://api.prospeo.io/enrich-person"
PROSPEO_SEARCH_COMPANY_URL = "https://api.prospeo.io/search-company"
TIMEOUT_SECONDS = 30


class VendorError(Exception):
    """Vendor transport or protocol failure (never carries secrets)."""


def _read_env_or_dotenv(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    try:
        from ai_provider.secrets import read_secret_key
    except ImportError:
        return None
    try:
        return read_secret_key(
            Path(__file__).resolve().parents[3] / ".env", name, label="Vendor credential"
        )
    except (OSError, ValueError):
        return None


def _vacancy_domain(vacancy: JobVacancy) -> str | None:
    """Employer domain from the vacancy contact email, minus freemail."""
    email = (vacancy.contact_email or "").strip()
    if "@" not in email:
        return None
    domain = email.rsplit("@", 1)[1].lower()
    if not domain or "." not in domain or domain in FREEMAIL_DOMAINS:
        return None
    return domain


def _split_name(recruiter_name: str | None) -> tuple[str, str] | None:
    """Split a recruiter name into (first, last); None when unusable."""
    if not recruiter_name:
        return None
    parts = [part for part in recruiter_name.strip().split() if part]
    if len(parts) < 2:
        return None
    first, last = parts[0], parts[-1]
    if not first.replace("-", "").isalpha() or not last.replace("-", "").isalpha():
        return None
    return first, last


def _post_json(
    url: str, headers: dict[str, str], payload: dict[str, Any], timeout: float
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            status = response.status
    except urllib.error.HTTPError as exc:
        raise VendorError(f"{url} returned HTTP {exc.code}") from None
    except Exception as exc:
        raise VendorError(f"{url} unreachable: {type(exc).__name__}") from None
    if status != 200:
        raise VendorError(f"{url} returned HTTP {status}")
    try:
        decoded = json.loads(body)
    except ValueError:
        raise VendorError(f"{url} returned non-JSON") from None
    if not isinstance(decoded, dict):
        raise VendorError(f"{url} returned a non-object")
    return decoded


PostTransport = Callable[[str, dict[str, str], dict[str, Any], float], dict[str, Any]]


@dataclass
class _VendorSourceBase:
    """Shared key/transport plumbing; subclasses map one vendor API."""

    key_env: str
    api_key: str | None = None
    post: PostTransport = _post_json

    def __post_init__(self) -> None:
        if not self.api_key:
            self.api_key = _read_env_or_dotenv(self.key_env)

    @property
    def ready(self) -> bool:
        return bool(self.api_key)


@dataclass
class ApolloContactSource(_VendorSourceBase):
    """Apollo People Match: recruiter name + employer domain to one email."""

    name: str = "apollo"
    key_env: str = "APOLLO_API_KEY"

    def resolve(self, vacancy: JobVacancy) -> ContactProposal | None:
        if not self.ready:
            return None
        name_parts = _split_name(vacancy.recruiter_name)
        domain = _vacancy_domain(vacancy)
        if name_parts is None or domain is None:
            return None
        first, last = name_parts
        try:
            decoded = self.post(
                APOLLO_MATCH_URL,
                {"x-api-key": self.api_key or ""},
                {"first_name": first, "last_name": last, "domain": domain},
                TIMEOUT_SECONDS,
            )
        except VendorError:
            return None
        person = decoded.get("person")
        if not isinstance(person, dict):
            return None
        email = str(person.get("email") or "").strip()
        if not email or "@" not in email:
            return None
        status = str(person.get("email_status") or "").strip().lower()
        return ContactProposal(
            email=email,
            name=str(person.get("name") or f"{first} {last}"),
            title=str(person.get("title") or "") or None,
            source="apollo:people/match",
            verified=status == "verified",
            generic_inbox=is_generic_inbox(email),
            evidence=("apollo:people/match", f"email_status:{status or 'unknown'}"),
        )


@dataclass
class ProspeoContactSource(_VendorSourceBase):
    """Prospeo Enrich Person: recruiter name + company domain to one email."""

    name: str = "prospeo"
    key_env: str = "PROSPEO_API_KEY"

    def resolve(self, vacancy: JobVacancy) -> ContactProposal | None:
        if not self.ready:
            return None
        name_parts = _split_name(vacancy.recruiter_name)
        domain = _vacancy_domain(vacancy)
        if name_parts is None or domain is None:
            return None
        first, last = name_parts
        try:
            decoded = self.post(
                PROSPEO_ENRICH_URL,
                {"X-KEY": self.api_key or ""},
                {
                    "data": {
                        "first_name": first,
                        "last_name": last,
                        "company_name": vacancy.company,
                        "company_website": domain,
                    },
                    "only_verified_email": True,
                },
                TIMEOUT_SECONDS,
            )
        except VendorError:
            return None
        person = decoded.get("person")
        if not isinstance(person, dict):
            return None
        email_obj = person.get("email")
        if not isinstance(email_obj, dict):
            return None
        email = str(email_obj.get("email") or "").strip()
        if not email or "@" not in email:
            return None
        verified = str(email_obj.get("status") or "").strip().upper() == "VERIFIED"
        return ContactProposal(
            email=email,
            name=str(person.get("full_name") or f"{first} {last}"),
            title=str(person.get("current_job_title") or person.get("headline") or "") or None,
            source="prospeo:enrich-person",
            verified=verified,
            generic_inbox=is_generic_inbox(email),
            evidence=("prospeo:enrich-person", f"verified:{str(verified).lower()}"),
        )


@dataclass(frozen=True, slots=True)
class ProspeoCompany:
    """One company row from Prospeo search (any field may be null upstream)."""

    company_id: str | None
    name: str
    domain: str | None
    industry: str | None
    employee_count: int | None
    employee_range: str | None
    hq_country: str | None
    hq_city: str | None
    keywords: tuple[str, ...]
    description: str | None


@dataclass(frozen=True, slots=True)
class ProspeoCompanyPage:
    """One 25-row search page with pagination totals."""

    companies: tuple[ProspeoCompany, ...]
    current_page: int
    total_pages: int
    total_count: int
    served_free_dedup: bool


def _prospeo_company_from_raw(raw: Any) -> ProspeoCompany | None:
    if not isinstance(raw, dict):
        return None
    company = raw.get("company", raw)
    if not isinstance(company, dict):
        return None
    name = company.get("name") or ""
    if not isinstance(name, str) or not name.strip():
        return None
    location = company.get("location")
    location = location if isinstance(location, dict) else {}
    keywords = company.get("keywords")
    keywords = (
        tuple(k for k in keywords if isinstance(k, str)) if isinstance(keywords, list) else ()
    )
    description = (
        company.get("description_ai")
        or company.get("description")
        or company.get("description_seo")
    )
    count = company.get("employee_count")
    return ProspeoCompany(
        company_id=company.get("company_id")
        if isinstance(company.get("company_id"), str)
        else None,
        name=name.strip(),
        domain=company.get("domain") if isinstance(company.get("domain"), str) else None,
        industry=company.get("industry") if isinstance(company.get("industry"), str) else None,
        employee_count=count if isinstance(count, int) else None,
        employee_range=company.get("employee_range")
        if isinstance(company.get("employee_range"), str)
        else None,
        hq_country=location.get("country") if isinstance(location.get("country"), str) else None,
        hq_city=location.get("city") if isinstance(location.get("city"), str) else None,
        keywords=keywords,
        description=description if isinstance(description, str) else None,
    )


def search_prospeo_companies(
    *,
    api_key: str,
    filters: dict[str, Any],
    page: int = 1,
    timeout: float = TIMEOUT_SECONDS,
    post: PostTransport = _post_json,
) -> ProspeoCompanyPage:
    """Run one Prospeo company-search page (1 credit per non-empty page).

    ``filters`` must carry at least one positive filter (the API rejects
    exclude-only searches). Raises VendorError on transport, protocol, or
    vendor errors; never logs the key.
    """
    if not api_key:
        raise VendorError("Prospeo search needs an API key")
    if not isinstance(filters, dict) or not filters:
        raise VendorError("Prospeo search needs at least one filter")
    if not isinstance(page, int) or page < 1:
        raise VendorError("Prospeo search page must be >= 1")
    decoded = post(
        PROSPEO_SEARCH_COMPANY_URL,
        {"X-KEY": api_key},
        {"filters": filters, "page": page},
        timeout,
    )
    if decoded.get("error") is True:
        code = decoded.get("error_code", "unknown")
        raise VendorError(f"Prospeo search failed: {code}")
    rows = decoded.get("companies", [])
    if not isinstance(rows, list):
        raise VendorError("Prospeo search returned a non-list")
    companies = tuple(
        parsed for raw in rows if (parsed := _prospeo_company_from_raw(raw)) is not None
    )
    return ProspeoCompanyPage(
        companies=companies,
        current_page=decoded.get("current_page", page)
        if isinstance(decoded.get("current_page"), int)
        else page,
        total_pages=decoded.get("total_page", 0)
        if isinstance(decoded.get("total_page"), int)
        else 0,
        total_count=decoded.get("total_count", 0)
        if isinstance(decoded.get("total_count"), int)
        else 0,
        served_free_dedup=decoded.get("free") is True,
    )


def default_contact_registry() -> ContactRegistry:
    """Manual first (free, already-known), then ready vendors in order.

    Dormant vendors (no key) are skipped; ``registry.source_names``
    shows what is active. Apollo stays dormant until its 403 clears.
    """
    sources: list[ContactSource] = [ManualContactSource()]
    for cls in (ProspeoContactSource, ApolloContactSource):
        try:
            source = cls()
        except Exception:
            continue
        if source.ready:
            sources.append(source)
    return ContactRegistry(sources)
