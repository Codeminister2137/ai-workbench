"""Local Ollama runtime helpers."""

from __future__ import annotations

import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ai_provider.errors import ProviderError, ProviderErrorCategory

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"


def is_ollama_server_available(
    base_url: str | None = None,
    *,
    timeout_seconds: float = 1.0,
) -> bool:
    """Return whether the local Ollama HTTP API is reachable."""

    request = Request(f"{_ollama_base_url(base_url)}/api/tags", method="GET")
    try:
        with urlopen(request, timeout=timeout_seconds):
            return True
    except HTTPError:
        return True
    except (OSError, TimeoutError, URLError):
        return False


def ensure_ollama_server(
    base_url: str | None = None,
    *,
    command: str = "ollama",
    startup_timeout_seconds: float = 10.0,
    probe_timeout_seconds: float = 1.0,
) -> bool:
    """Start `ollama serve` if the local Ollama API is not already reachable.

    Returns `True` when this call launched a server process and `False` when an
    existing server was already available.
    """

    if startup_timeout_seconds <= 0:
        raise ProviderError(
            "Ollama startup timeout must be greater than zero seconds.",
            category=ProviderErrorCategory.CONFIGURATION,
            provider="ollama",
        )

    if is_ollama_server_available(base_url, timeout_seconds=probe_timeout_seconds):
        return False

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        subprocess.Popen(
            [command, "serve"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
    except FileNotFoundError as exc:
        raise ProviderError(
            f"Could not start Ollama because command {command!r} was not found.",
            category=ProviderErrorCategory.CONFIGURATION,
            provider="ollama",
            raw_error=exc,
        ) from exc
    except OSError as exc:
        raise ProviderError(
            "Could not start Ollama.",
            category=ProviderErrorCategory.RETRYABLE,
            retryable=True,
            provider="ollama",
            raw_error=exc,
        ) from exc

    deadline = time.monotonic() + startup_timeout_seconds
    while time.monotonic() < deadline:
        if is_ollama_server_available(base_url, timeout_seconds=probe_timeout_seconds):
            return True
        time.sleep(0.25)

    raise ProviderError(
        "Started Ollama but the local API did not become reachable before timeout.",
        category=ProviderErrorCategory.TIMEOUT,
        retryable=True,
        provider="ollama",
    )


def _ollama_base_url(base_url: str | None) -> str:
    return (base_url or DEFAULT_OLLAMA_BASE_URL).rstrip("/")
