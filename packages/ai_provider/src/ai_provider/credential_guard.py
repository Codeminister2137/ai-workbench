"""Refuse known credentials in model input without copying them into diagnostics."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping
from dataclasses import fields, is_dataclass

from ai_provider.errors import ProviderError, ProviderErrorCategory


def credential_values(extra: Iterable[str | None] = ()) -> tuple[str, ...]:
    """Use explicit keys and current secret-named environment values, never files."""
    suffixes = (
        "_API_KEY",
        "_TOKEN",
        "_TOKEN_ID",
        "_TOKEN_SECRET",
        "_SECRET",
        "_PASSWORD",
        "_PRIVATE_KEY",
        "_ACCESS_KEY",
        "_ACCESS_KEY_ID",
        "_SECRET_ACCESS_KEY",
    )
    values = {value for value in extra if isinstance(value, str) and value}
    values.update(
        value
        for name, value in os.environ.items()
        if len(value) >= 16
        and (
            name.upper().endswith(suffixes)
            or name.upper() in {"API_KEY", "TOKEN", "SECRET", "PASSWORD"}
        )
    )
    # Provider adapters trim authentication values before constructing headers.
    values.update(value.strip() for value in tuple(values) if value.strip())
    return tuple(values)


def contains_credentials(value: object, *, extra: Iterable[str | None] = ()) -> bool:
    """Match exact known values, including JSON escapes; do not decode opaque data."""
    credentials = credential_values(extra)
    if not credentials:
        return False
    variants = {
        form
        for secret in credentials
        for form in (secret, json.dumps(secret)[1:-1], json.dumps(secret, ensure_ascii=False)[1:-1])
    }
    seen: set[int] = set()

    def matches(item: object) -> bool:
        if isinstance(item, str):
            return any(secret in item for secret in variants)
        if type(item) in (int, float, bool):
            return any(secret in str(item) for secret in variants)
        if id(item) in seen:
            return False
        seen.add(id(item))
        if isinstance(item, Mapping):
            return any(matches(key) or matches(child) for key, child in item.items())
        if isinstance(item, (list, tuple)):
            return any(matches(child) for child in item)
        if is_dataclass(item) and not isinstance(item, type):
            return any(matches(getattr(item, part.name)) for part in fields(item))
        return False

    return matches(value)


def enforce_credential_policy(value: object, *, extra: Iterable[str | None] = ()) -> None:
    """Stop before transport with fixed diagnostics and no raw-input error fields."""
    if contains_credentials(value, extra=extra):
        raise ProviderError(
            "Credential-bearing model input refused; no provider request was sent.",
            category=ProviderErrorCategory.PRIVACY_POLICY,
            retryable=False,
        )
