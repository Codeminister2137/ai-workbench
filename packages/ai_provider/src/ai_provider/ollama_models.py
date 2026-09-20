"""Local Ollama model inventory and pull helpers."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ai_provider.errors import ProviderError, ProviderErrorCategory
from ai_provider.ollama_runtime import DEFAULT_OLLAMA_BASE_URL, ensure_ollama_server

BYTES_PER_GIB = 1024**3


@dataclass(frozen=True, slots=True)
class LocalOllamaModel:
    """One locally installed Ollama model."""

    name: str
    model: str
    size_bytes: int
    digest: str | None = None
    modified_at: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OllamaPullConstraints:
    """Local resource limits for an Ollama model pull."""

    min_free_bytes: int = 0
    max_download_bytes: int | None = None
    models_path: Path | None = None

    @classmethod
    def from_gib(
        cls,
        *,
        min_free_gib: float = 0,
        max_download_gib: float | None = None,
        models_path: Path | None = None,
    ) -> OllamaPullConstraints:
        """Build constraints from GiB values used by CLI callers."""

        if min_free_gib < 0:
            raise ValueError("min_free_gib must not be negative.")
        if max_download_gib is not None and max_download_gib <= 0:
            raise ValueError("max_download_gib must be greater than zero.")
        return cls(
            min_free_bytes=int(min_free_gib * BYTES_PER_GIB),
            max_download_bytes=(
                int(max_download_gib * BYTES_PER_GIB) if max_download_gib is not None else None
            ),
            models_path=models_path,
        )


@dataclass(frozen=True, slots=True)
class OllamaPullProgress:
    """One streamed progress event from an Ollama pull."""

    status: str
    digest: str | None = None
    total_bytes: int | None = None
    completed_bytes: int | None = None


@dataclass(frozen=True, slots=True)
class OllamaPullResult:
    """Completed Ollama pull summary."""

    model: str
    events: tuple[OllamaPullProgress, ...]

    @property
    def max_reported_total_bytes(self) -> int | None:
        totals = [event.total_bytes for event in self.events if event.total_bytes is not None]
        return max(totals) if totals else None


def list_local_ollama_models(
    base_url: str | None = None,
    *,
    timeout_seconds: float = 10.0,
    start_ollama: bool = False,
) -> tuple[LocalOllamaModel, ...]:
    """Return models currently installed in the local Ollama library."""

    if start_ollama:
        ensure_ollama_server(base_url)
    payload = _request_json(
        "GET",
        f"{_base_url(base_url)}/api/tags",
        timeout_seconds=timeout_seconds,
    )
    raw_models = payload.get("models", [])
    if not isinstance(raw_models, list):
        raise _unexpected_response("Ollama model list did not include a models array.", payload)

    return tuple(_local_model_from_raw(item) for item in raw_models if isinstance(item, dict))


def show_ollama_model(
    model: str,
    base_url: str | None = None,
    *,
    timeout_seconds: float = 10.0,
    start_ollama: bool = False,
) -> dict[str, Any]:
    """Return Ollama's local model details for one installed model."""

    if start_ollama:
        ensure_ollama_server(base_url)
    return _request_json(
        "POST",
        f"{_base_url(base_url)}/api/show",
        payload={"model": model},
        timeout_seconds=timeout_seconds,
    )


def pull_ollama_model(
    model: str,
    base_url: str | None = None,
    *,
    constraints: OllamaPullConstraints | None = None,
    progress_callback: Callable[[OllamaPullProgress], None] | None = None,
    timeout_seconds: float = 120.0,
    start_ollama: bool = True,
) -> OllamaPullResult:
    """Pull an Ollama model while enforcing local disk constraints."""

    if start_ollama:
        ensure_ollama_server(base_url)
    effective_constraints = constraints or OllamaPullConstraints()
    _enforce_min_free_space(effective_constraints)

    events: list[OllamaPullProgress] = []
    for event in stream_ollama_model_pull(
        model,
        base_url,
        timeout_seconds=timeout_seconds,
    ):
        if progress_callback is not None:
            progress_callback(event)
        _enforce_max_download_size(event, effective_constraints)
        events.append(event)
    _enforce_min_free_space(effective_constraints)
    return OllamaPullResult(model=model, events=tuple(events))


def stream_ollama_model_pull(
    model: str,
    base_url: str | None = None,
    *,
    timeout_seconds: float = 120.0,
) -> Iterator[OllamaPullProgress]:
    """Stream Ollama pull progress events for one model."""

    body = json.dumps({"model": model, "stream": True}).encode("utf-8")
    request = Request(
        f"{_base_url(base_url)}/api/pull",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            for line in response:
                raw_line = line.strip()
                if not raw_line:
                    continue
                raw_event = json.loads(raw_line.decode("utf-8"))
                if not isinstance(raw_event, dict):
                    raise _unexpected_response(
                        "Ollama pull returned an invalid progress event.",
                        raw_event,
                    )
                yield _pull_progress_from_raw(raw_event)
    except json.JSONDecodeError as exc:
        raise ProviderError(
            "Ollama pull returned invalid JSON.",
            category=ProviderErrorCategory.NON_RETRYABLE,
            provider="ollama",
            raw_error=exc,
        ) from exc
    except TimeoutError as exc:
        raise ProviderError(
            "Ollama pull timed out.",
            category=ProviderErrorCategory.TIMEOUT,
            retryable=True,
            provider="ollama",
            raw_error=exc,
        ) from exc
    except HTTPError as exc:
        category = (
            ProviderErrorCategory.RETRYABLE
            if 500 <= exc.code < 600
            else ProviderErrorCategory.NON_RETRYABLE
        )
        raise ProviderError(
            f"Ollama pull returned HTTP {exc.code}.",
            category=category,
            retryable=category is ProviderErrorCategory.RETRYABLE,
            provider="ollama",
            raw_error=exc,
        ) from exc
    except URLError as exc:
        raise ProviderError(
            "Could not connect to Ollama for model pull.",
            category=ProviderErrorCategory.RETRYABLE,
            retryable=True,
            provider="ollama",
            raw_error=exc,
        ) from exc


def _request_json(
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout_seconds: float,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"} if body is not None else {},
        method=method,
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            raw_payload = json.loads(response.read().decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ProviderError(
            "Ollama returned invalid JSON.",
            category=ProviderErrorCategory.NON_RETRYABLE,
            provider="ollama",
            raw_error=exc,
        ) from exc
    except TimeoutError as exc:
        raise ProviderError(
            "Ollama request timed out.",
            category=ProviderErrorCategory.TIMEOUT,
            retryable=True,
            provider="ollama",
            raw_error=exc,
        ) from exc
    except HTTPError as exc:
        category = (
            ProviderErrorCategory.RETRYABLE
            if 500 <= exc.code < 600
            else ProviderErrorCategory.NON_RETRYABLE
        )
        raise ProviderError(
            f"Ollama returned HTTP {exc.code}.",
            category=category,
            retryable=category is ProviderErrorCategory.RETRYABLE,
            provider="ollama",
            raw_error=exc,
        ) from exc
    except URLError as exc:
        raise ProviderError(
            "Could not connect to Ollama.",
            category=ProviderErrorCategory.RETRYABLE,
            retryable=True,
            provider="ollama",
            raw_error=exc,
        ) from exc

    if not isinstance(raw_payload, dict):
        raise _unexpected_response("Ollama returned a non-object response.", raw_payload)
    return raw_payload


def _local_model_from_raw(raw_model: dict[str, Any]) -> LocalOllamaModel:
    name = raw_model.get("name") or raw_model.get("model")
    model = raw_model.get("model") or name
    size = raw_model.get("size")
    if not isinstance(name, str) or not isinstance(model, str) or not isinstance(size, int):
        raise _unexpected_response("Ollama model entry had an unexpected shape.", raw_model)
    details = raw_model.get("details", {})
    return LocalOllamaModel(
        name=name,
        model=model,
        size_bytes=size,
        digest=raw_model.get("digest") if isinstance(raw_model.get("digest"), str) else None,
        modified_at=(
            raw_model.get("modified_at") if isinstance(raw_model.get("modified_at"), str) else None
        ),
        details=details if isinstance(details, dict) else {},
    )


def _pull_progress_from_raw(raw_event: dict[str, Any]) -> OllamaPullProgress:
    status = raw_event.get("status")
    if not isinstance(status, str):
        raise _unexpected_response("Ollama pull progress did not include a status.", raw_event)
    total = raw_event.get("total")
    completed = raw_event.get("completed")
    digest = raw_event.get("digest")
    return OllamaPullProgress(
        status=status,
        digest=digest if isinstance(digest, str) else None,
        total_bytes=total if isinstance(total, int) else None,
        completed_bytes=completed if isinstance(completed, int) else None,
    )


def _enforce_min_free_space(constraints: OllamaPullConstraints) -> None:
    if constraints.min_free_bytes <= 0:
        return
    target = constraints.models_path or Path.cwd()
    free_bytes = shutil.disk_usage(target).free
    if free_bytes < constraints.min_free_bytes:
        raise ProviderError(
            "Ollama model pull would violate the configured minimum free space.",
            category=ProviderErrorCategory.CONFIGURATION,
            provider="ollama",
            raw_error={
                "free_bytes": free_bytes,
                "min_free_bytes": constraints.min_free_bytes,
                "models_path": str(target),
            },
        )


def _enforce_max_download_size(
    event: OllamaPullProgress,
    constraints: OllamaPullConstraints,
) -> None:
    if constraints.max_download_bytes is None or event.total_bytes is None:
        return
    if event.total_bytes > constraints.max_download_bytes:
        raise ProviderError(
            "Ollama model pull exceeded the configured maximum download size.",
            category=ProviderErrorCategory.CONFIGURATION,
            provider="ollama",
            raw_error={
                "status": event.status,
                "total_bytes": event.total_bytes,
                "max_download_bytes": constraints.max_download_bytes,
            },
        )


def _unexpected_response(message: str, raw_error: object) -> ProviderError:
    return ProviderError(
        message,
        category=ProviderErrorCategory.NON_RETRYABLE,
        provider="ollama",
        raw_error=raw_error,
    )


def _base_url(base_url: str | None) -> str:
    return (base_url or DEFAULT_OLLAMA_BASE_URL).rstrip("/")
