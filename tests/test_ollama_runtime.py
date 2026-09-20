from __future__ import annotations

from typing import Any
from urllib.error import URLError

import pytest
from ai_provider import ProviderError, ProviderErrorCategory
from ai_provider.ollama_runtime import ensure_ollama_server, is_ollama_server_available


class FakeHttpResponse:
    def __enter__(self) -> FakeHttpResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_is_ollama_server_available_returns_true_when_api_responds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, timeout: float) -> FakeHttpResponse:
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return FakeHttpResponse()

    monkeypatch.setattr("ai_provider.ollama_runtime.urlopen", fake_urlopen)

    assert is_ollama_server_available("http://ollama.test/", timeout_seconds=0.5) is True
    assert captured == {"url": "http://ollama.test/api/tags", "timeout": 0.5}


def test_is_ollama_server_available_returns_false_when_api_is_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: Any, timeout: float) -> FakeHttpResponse:
        raise URLError("connection refused")

    monkeypatch.setattr("ai_provider.ollama_runtime.urlopen", fake_urlopen)

    assert is_ollama_server_available("http://ollama.test") is False


def test_ensure_ollama_server_starts_process_when_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = iter((False, True))
    popen_calls: list[list[str]] = []

    monkeypatch.setattr(
        "ai_provider.ollama_runtime.is_ollama_server_available",
        lambda base_url, *, timeout_seconds: next(attempts),
    )

    def fake_popen(command: list[str], **kwargs: object) -> object:
        popen_calls.append(command)
        return object()

    monkeypatch.setattr("ai_provider.ollama_runtime.subprocess.Popen", fake_popen)
    monkeypatch.setattr("ai_provider.ollama_runtime.time.sleep", lambda seconds: None)

    assert ensure_ollama_server("http://ollama.test", command="ollama-test") is True
    assert popen_calls == [["ollama-test", "serve"]]


def test_ensure_ollama_server_does_not_start_when_already_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ai_provider.ollama_runtime.is_ollama_server_available",
        lambda base_url, *, timeout_seconds: True,
    )

    def fake_popen(command: list[str], **kwargs: object) -> object:
        raise AssertionError("should not start a process")

    monkeypatch.setattr("ai_provider.ollama_runtime.subprocess.Popen", fake_popen)

    assert ensure_ollama_server("http://ollama.test") is False


def test_ensure_ollama_server_wraps_missing_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "ai_provider.ollama_runtime.is_ollama_server_available",
        lambda base_url, *, timeout_seconds: False,
    )

    def fake_popen(command: list[str], **kwargs: object) -> object:
        raise FileNotFoundError

    monkeypatch.setattr("ai_provider.ollama_runtime.subprocess.Popen", fake_popen)

    with pytest.raises(ProviderError) as error:
        ensure_ollama_server("http://ollama.test", command="missing-ollama")

    assert error.value.category is ProviderErrorCategory.CONFIGURATION
    assert error.value.provider == "ollama"
