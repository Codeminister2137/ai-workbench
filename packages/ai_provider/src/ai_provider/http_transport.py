"""HTTP transport rules for authenticated provider requests."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ai_provider.errors import ProviderError, ProviderErrorCategory

#: Shared bound for a single provider response body (2 MiB, matching the
#: catalog/probe readers). Adapters must read through :func:`read_bounded` or
#: :func:`iter_response_lines` so a rogue or huge body fails closed instead of
#: exhausting process memory.
MAX_RESPONSE_BYTES = 2_097_152

#: Incremental read size used by the bounded readers.
_READ_CHUNK_SIZE = 65_536


class _RejectRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Neither credentials nor prompts may follow a provider redirect.
        return None


def urlopen(request: Request, *, timeout: float):
    """Open one provider request without following redirects."""
    return build_opener(_RejectRedirect()).open(request, timeout=timeout)


def _content_length(response: Any) -> int | None:
    """Return the declared Content-Length, or None when absent/unparseable."""
    raw: Any = None
    getheader = getattr(response, "getheader", None)
    if callable(getheader):
        try:
            raw = getheader("Content-Length")
        except Exception:
            raw = None
    if raw is None:
        headers = getattr(response, "headers", None)
        get = getattr(headers, "get", None)
        if callable(get):
            try:
                raw = get("Content-Length")
            except Exception:
                raw = None
    if raw is None:
        return None
    try:
        length = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return length if length >= 0 else None


def _overflow_error(*, provider: str | None, limit: int) -> ProviderError:
    return ProviderError(
        f"Provider response exceeded the {limit} byte body limit.",
        category=ProviderErrorCategory.NON_RETRYABLE,
        provider=provider,
    )


def _check_content_length(response: Any, *, provider: str | None, limit: int) -> None:
    declared = _content_length(response)
    if declared is not None and declared > limit:
        raise _overflow_error(provider=provider, limit=limit)


def read_bounded(response: Any, *, provider: str | None = None, limit: int | None = None) -> bytes:
    """Read one response body, failing closed past the shared byte bound.

    A declared Content-Length above the bound raises before any body bytes
    are read; otherwise the body is read incrementally so an unbounded or
    lying sender cannot exhaust memory. Overflow raises ProviderError and
    never returns a silently truncated body.
    """
    bound = MAX_RESPONSE_BYTES if limit is None else limit
    _check_content_length(response, provider=provider, limit=bound)
    read = response.read
    try:
        first = read(_READ_CHUNK_SIZE)
    except TypeError:
        # Legacy no-arg read() stub: single read, then enforce the bound.
        body = read()
        if len(body) > bound:
            raise _overflow_error(provider=provider, limit=bound) from None
        return body
    chunks: list[bytes] = []
    total = 0
    chunk = first
    while chunk:
        chunks.append(chunk)
        total += len(chunk)
        if total > bound:
            raise _overflow_error(provider=provider, limit=bound)
        chunk = read(_READ_CHUNK_SIZE)
    return b"".join(chunks)


def iter_response_lines(
    response: Any, *, provider: str | None = None, limit: int | None = None
) -> Iterator[bytes]:
    """Yield response lines, failing closed past the shared byte bound.

    The cumulative byte count across all lines is enforced; overflow raises
    ProviderError and never truncates the stream silently.
    """
    bound = MAX_RESPONSE_BYTES if limit is None else limit
    _check_content_length(response, provider=provider, limit=bound)
    total = 0
    for line in response:
        total += len(line)
        if total > bound:
            raise _overflow_error(provider=provider, limit=bound)
        yield line
