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

from contacts import ContactProposal, ContactRegistry, ManualContactSource, is_generic_inbox
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


def default_contact_registry() -> ContactRegistry:
    """Manual first (free, already-known), then ready vendors in order.

    Dormant vendors (no key) are skipped; ``registry.source_names``
    shows what is active. Apollo stays dormant until its 403 clears.
    """
    sources = [ManualContactSource()]
    for cls in (ProspeoContactSource, ApolloContactSource):
        try:
            source = cls()
        except Exception:
            continue
        if source.ready:
            sources.append(source)
    return ContactRegistry(sources)
