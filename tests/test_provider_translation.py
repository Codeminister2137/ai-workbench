"""Ingestion-time normalization plus the ChatClient-backed translator."""

from __future__ import annotations

import pytest
from ai_provider import (
    AIMessage,
    AIResponse,
    BackendInfo,
    BackendLocation,
    MessageRole,
    UsageMetadata,
    UsageSource,
)
from ai_provider.translation import (
    ChatTranslator,
    TranslationError,
    normalize_input,
    translation_manifest,
)


class _FakeClient:
    def __init__(self, text: str, usage: UsageMetadata | None = None) -> None:
        self.text = text
        self.usage = usage or UsageMetadata()
        self.requests: list = []

    @property
    def backend(self) -> BackendInfo:
        return BackendInfo(provider="fake", model="fake-1", location=BackendLocation.EXTERNAL)

    def complete(self, request) -> AIResponse:
        self.requests.append(request)
        return AIResponse(
            message=AIMessage(role=MessageRole.ASSISTANT, content=self.text),
            backend=self.backend,
            usage=self.usage,
        )

    def stream(self, request):
        raise NotImplementedError


class _FakeMetering:
    def __init__(self) -> None:
        self.reserved: list[dict] = []
        self.committed: list[dict] = []

    def reserve(self, *, operation: str, estimated_cents: int, **kwargs: object) -> str:
        receipt = f"rcpt-{len(self.reserved)}"
        self.reserved.append({"operation": operation, "estimated": estimated_cents})
        return receipt

    def commit(self, receipt_id: str, actual_cents: int) -> None:
        self.committed.append({"receipt": receipt_id, "actual": actual_cents})


class TestNormalizeInput:
    def test_english_posts_without_provider_call(self):
        client = _FakeClient("unused")
        translator = ChatTranslator(client, translator_id="fake:t")
        normalized, receipt = normalize_input(translator, "Hello", "en")
        assert normalized.translated is False
        assert normalized.working == "Hello"
        assert receipt is None
        assert client.requests == []

    def test_non_english_without_translator_fails_closed(self):
        with pytest.raises(TranslationError) as excinfo:
            normalize_input(None, "Czesc", "pl")
        assert excinfo.value.status == 409

    def test_non_english_translates_with_receipt(self):
        metering = _FakeMetering()
        translator = ChatTranslator(_FakeClient("Hello"), translator_id="fake:t", metering=metering)
        normalized, receipt = normalize_input(translator, "Czesc", "pl")
        assert normalized.translated is True
        assert normalized.working == "Hello"
        assert normalized.source == "Czesc"
        assert normalized.lang == "pl"
        assert receipt is not None
        assert receipt["translator"] == "fake:t"
        assert metering.committed

    def test_reported_cost_settles_actual(self):
        usage = UsageMetadata(source=UsageSource.PROVIDER_REPORTED, reported_cost_usd=0.02)
        metering = _FakeMetering()
        translator = ChatTranslator(
            _FakeClient("Hello", usage), translator_id="fake:t", metering=metering
        )
        normalize_input(translator, "Czesc", "pl")
        assert metering.committed[0]["actual"] == 2

    def test_empty_text_rejected(self):
        translator = ChatTranslator(_FakeClient("x"), translator_id="fake:t")
        with pytest.raises(ValueError, match="non-empty"):
            normalize_input(translator, "  ", "pl")


class TestManifest:
    def test_summarizes_provenance(self):
        thread = {
            "prompt_lang": "pl",
            "prompt_translator": "fake:t",
            "history": [
                {"role": "user", "source_lang": "pl", "translator": "fake:t", "translated": True},
                {"role": "user", "source_lang": "pl", "translator": "none", "translated": False},
                {"role": "assistant", "content": "hi"},
            ],
        }
        assert translation_manifest(thread) == {
            "langs": ["pl"],
            "translators": ["fake:t"],
            "untranslated": True,
        }

    def test_legacy_thread_reads_as_english(self):
        assert translation_manifest({}) == {
            "langs": [],
            "translators": [],
            "untranslated": False,
        }
