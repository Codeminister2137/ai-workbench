"""Local Ollama runtime helpers."""

from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ai_provider.errors import ProviderError, ProviderErrorCategory

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"


@dataclass(frozen=True, slots=True)
class OllamaResourceProfile:
    """Server settings balancing model capacity against local responsiveness."""

    name: str
    context_length: int
    num_parallel: int = 1
    max_loaded_models: int = 1

    def environment(self) -> dict[str, str]:
        """Return Ollama environment variables for this profile."""

        return {
            "OLLAMA_CONTEXT_LENGTH": str(self.context_length),
            "OLLAMA_NUM_PARALLEL": str(self.num_parallel),
            "OLLAMA_MAX_LOADED_MODELS": str(self.max_loaded_models),
        }


OLLAMA_RESOURCE_PROFILES = {
    "gaming": OllamaResourceProfile("gaming", context_length=4096),
    "balanced": OllamaResourceProfile("balanced", context_length=8192),
    "full": OllamaResourceProfile("full", context_length=32768),
}


def get_ollama_resource_profile(name: str) -> OllamaResourceProfile:
    """Return a named local Ollama resource profile."""

    try:
        return OLLAMA_RESOURCE_PROFILES[name]
    except KeyError as exc:
        available = ", ".join(sorted(OLLAMA_RESOURCE_PROFILES))
        raise ProviderError(
            f"Unknown Ollama resource profile {name!r}; choose from {available}.",
            category=ProviderErrorCategory.CONFIGURATION,
            provider="ollama",
        ) from exc


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


def get_ollama_version(
    base_url: str | None = None,
    *,
    timeout_seconds: float = 2.0,
) -> str | None:
    """Return the local Ollama server version when it exposes one."""

    request = Request(f"{_ollama_base_url(base_url)}/api/version", method="GET")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = response.read().decode("utf-8")
    except (OSError, TimeoutError, URLError):
        return None
    try:
        value = json.loads(payload).get("version")
    except (ValueError, AttributeError):
        return None
    return value if isinstance(value, str) and value else None


def ensure_ollama_server(
    base_url: str | None = None,
    *,
    command: str = "ollama",
    startup_timeout_seconds: float = 10.0,
    probe_timeout_seconds: float = 1.0,
    log_path: Path | None = None,
    resource_profile: OllamaResourceProfile | None = None,
    environment: Mapping[str, str] | None = None,
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
    log_file = None
    popen_output = subprocess.DEVNULL
    process_environment = None
    if resource_profile is not None or environment is not None:
        process_environment = dict(os.environ)
        if resource_profile is not None:
            process_environment.update(resource_profile.environment())
        if environment is not None:
            process_environment.update(environment)
    try:
        if log_path is not None:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_file = log_path.open("ab")
            popen_output = log_file
        subprocess.Popen(
            [command, "serve"],
            stdin=subprocess.DEVNULL,
            stdout=popen_output,
            stderr=subprocess.STDOUT if log_file is not None else subprocess.DEVNULL,
            creationflags=creationflags,
            env=process_environment,
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
    finally:
        if log_file is not None:
            log_file.close()

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
