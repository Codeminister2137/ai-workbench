"""Server-side native-language -> English normalization for planning input.

Placement is server acceptance: callers translate at ingestion, BEFORE a user
turn is appended to history, so planning prompts, plans and runs always
consume English working text. The verbatim source is preserved next to it
with its language tag and translator id.

English posts exactly as before (no provider call, no spend). Non-English
input without a configured translator fails closed with 409 (block with
retry): nothing is stored.

The engine is provider-neutral: ``ChatTranslator`` runs over any
``ChatClient`` instead of direct provider HTTP, so metering and privacy flow
through the normal provider path.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Protocol

from ai_provider.contracts import (
    AIMessage,
    AIRequest,
    ChatClient,
    MessageRole,
    PrivacyClass,
)
from ai_provider.errors import ProviderError

logger = logging.getLogger(__name__)

ALLOWED_LANGUAGES = ("en", "pl")
LANGUAGE_NAMES = {"en": "English", "pl": "Polish"}
MAX_TRANSLATION_CHARS = 4000
TRANSLATION_MAX_OUTPUT_TOKENS = 2048

UNAVAILABLE_MESSAGE = (
    "Translation unavailable: configure a translation provider and retry, or send English text."
)


class TranslationError(Exception):
    """A typed translation failure mapped to an HTTP status by the web layer."""

    def __init__(self, status: int, message: str, *, headers: dict | None = None):
        super().__init__(message)
        self.status = status
        self.headers = dict(headers or {})


def normalize_language(tag: str) -> str:
    """Validate a BCP47 tag against the day-one allowlist; returns lowercase."""
    if not isinstance(tag, str) or tag.lower() not in ALLOWED_LANGUAGES:
        raise ValueError(f"Unsupported language: {tag!r}; supported languages: en, pl")
    return tag.lower()


@dataclass(frozen=True)
class TranslationResult:
    """English working text plus provenance for one translated input."""

    text: str
    source_lang: str
    translator_id: str


@dataclass(frozen=True)
class NormalizedText:
    """One ingestion input split into working text plus preserved source."""

    working: str
    source: str
    lang: str
    translated: bool
    translator_id: str


class Translator(Protocol):
    """Narrow engine interface; the free-later swap implements this too."""

    @property
    def id(self) -> str: ...

    def supported_languages(self) -> list[str]: ...

    def needs_key(self) -> bool: ...

    def estimate_cents(self, text: str) -> int: ...

    def translate(self, text: str, source_lang: str) -> TranslationResult: ...


class TranslationMetering(Protocol):
    """Narrow spend interface; the orchestrator binds it to its ledger."""

    def reserve(self, *, operation: str, estimated_cents: int, **kwargs: object) -> str: ...

    def commit(self, receipt_id: str, actual_cents: int) -> None: ...


def normalize_input(
    translator: Translator | None, text: str, language: str
) -> tuple[NormalizedText, dict | None]:
    """Validate and translate one ingestion input.

    Returns the normalized text plus the metering receipt (None when no
    provider call ran). Raises TranslationError(409) for non-English input
    without a translator; nothing is stored by callers on failure.
    """
    lang = normalize_language(language)
    if lang == "en":
        return NormalizedText(text, text, "en", False, "none"), None
    if translator is None:
        raise TranslationError(409, UNAVAILABLE_MESSAGE)
    result = translator.translate(text, lang)
    receipt = getattr(translator, "last_receipt", None)
    return (
        NormalizedText(result.text, text, result.source_lang, True, result.translator_id),
        receipt,
    )


def translation_manifest(thread: dict) -> dict:
    """Summarize translation provenance for review UI and run audit.

    Readers treat missing keys as legacy English; no backfill is performed.
    """
    langs: list[str] = []
    translators: list[str] = []
    untranslated = False

    def note(lang: str | None, translator_id: str | None, translated: object) -> None:
        nonlocal untranslated
        if lang in (None, "en"):
            return
        if translated:
            if lang not in langs:
                langs.append(lang)
            if translator_id not in translators:
                translators.append(translator_id or "none")
        else:
            untranslated = True

    prompt_lang = thread.get("prompt_lang", "en")
    prompt_translator = thread.get("prompt_translator", "none")
    note(prompt_lang, prompt_translator, prompt_translator != "none")
    for turn in thread.get("history", []):
        if not isinstance(turn, dict) or turn.get("role") != "user":
            continue
        note(
            turn.get("source_lang", "en"),
            turn.get("translator", "none"),
            turn.get("translated"),
        )
    return {"langs": langs, "translators": translators, "untranslated": untranslated}


class ChatTranslator:
    """Token-priced translation over any ChatClient.

    Metering reserves a coarse char-based estimate, then settles the provider
    reported cost when the response carries one, else the estimate. Estimates
    are deliberately coarse in this prototype; per-model pricing tables are a
    P5 follow-up.
    """

    def __init__(
        self,
        client: ChatClient,
        *,
        translator_id: str,
        metering: TranslationMetering | None = None,
        privacy_class: PrivacyClass = PrivacyClass.EXTERNAL_ALLOWED,
    ) -> None:
        self._client = client
        self._translator_id = translator_id
        self._metering = metering
        self._privacy_class = privacy_class
        self.last_receipt: dict | None = None

    @property
    def id(self) -> str:
        return self._translator_id

    def supported_languages(self) -> list[str]:
        return list(ALLOWED_LANGUAGES)

    def needs_key(self) -> bool:
        return True

    def estimate_cents(self, text: str) -> int:
        """Coarse char-based estimate (~4 chars/token in+out, 1c floor)."""
        return max(1, math.ceil(len(text) / 4 / 1000 * 2))

    def translate(self, text: str, source_lang: str) -> TranslationResult:
        self.last_receipt = None
        lang = normalize_language(source_lang)
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Translation requires non-empty text")
        if len(text) > MAX_TRANSLATION_CHARS:
            raise ValueError("Translation input exceeds 4000 characters")
        if lang == "en":
            return TranslationResult(text=text, source_lang="en", translator_id="none")
        estimate = self.estimate_cents(text)
        receipt_id = None
        if self._metering is not None:
            receipt_id = self._metering.reserve(operation="translate", estimated_cents=estimate)
        try:
            response = self._client.complete(
                AIRequest(
                    messages=(
                        AIMessage(
                            role=MessageRole.SYSTEM,
                            content=(
                                f"Translate the following {LANGUAGE_NAMES[lang]} text "
                                "to English. Return only the translation, no commentary."
                            ),
                        ),
                        AIMessage(role=MessageRole.USER, content=text),
                    ),
                    max_output_tokens=TRANSLATION_MAX_OUTPUT_TOKENS,
                    privacy_class=self._privacy_class,
                )
            )
        except ProviderError as exc:
            raise TranslationError(502, "Translation provider unavailable.") from exc
        working = response.message.content
        if not working.strip():
            raise TranslationError(502, "Translation provider returned an empty translation.")
        reported = response.usage.reported_cost_usd
        actual = max(1, math.ceil(reported * 100)) if reported else estimate
        receipt: dict = {
            "translator": self._translator_id,
            "source_lang": lang,
            "chars_in": len(text),
            "chars_out": len(working),
            "reservation_cents_estimate": estimate,
            "billed_cents_actual": actual,
            "spending_control": "local_estimate_not_provider_cap",
        }
        if self._metering is not None and receipt_id is not None:
            self._metering.commit(receipt_id, actual)
        self.last_receipt = receipt
        logger.info("translated %d chars from %s", len(text), lang)
        return TranslationResult(text=working, source_lang=lang, translator_id=self.id)


__all__ = [
    "ALLOWED_LANGUAGES",
    "LANGUAGE_NAMES",
    "MAX_TRANSLATION_CHARS",
    "TRANSLATION_MAX_OUTPUT_TOKENS",
    "TranslationError",
    "TranslationMetering",
    "TranslationResult",
    "Translator",
    "ChatTranslator",
    "NormalizedText",
    "normalize_input",
    "normalize_language",
    "translation_manifest",
]
