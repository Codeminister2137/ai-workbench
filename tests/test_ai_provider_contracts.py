from __future__ import annotations

import pytest
from ai_provider import (
    AIMessage,
    AIRequest,
    BackendInfo,
    BackendLocation,
    MessageRole,
    PrivacyClass,
    ProviderError,
    ProviderErrorCategory,
)
from ai_provider.privacy import enforce_privacy_policy


def test_request_defaults_to_local_only_privacy() -> None:
    request = AIRequest(messages=(AIMessage(MessageRole.USER, "Hello"),))

    assert request.privacy_class is PrivacyClass.LOCAL_ONLY


def test_local_backend_accepts_all_prototype_privacy_classes() -> None:
    backend = BackendInfo(provider="ollama", model="llama3.2", location=BackendLocation.LOCAL)

    for privacy_class in PrivacyClass:
        enforce_privacy_policy(backend, privacy_class)


def test_external_backend_rejects_local_only_request() -> None:
    backend = BackendInfo(
        provider="requesty", model="some-model", location=BackendLocation.EXTERNAL
    )

    with pytest.raises(ProviderError) as error:
        enforce_privacy_policy(backend, PrivacyClass.LOCAL_ONLY)

    assert error.value.category is ProviderErrorCategory.PRIVACY_POLICY
    assert error.value.retryable is False


def test_external_backend_rejects_sensitive_request_without_review() -> None:
    backend = BackendInfo(provider="openai", model="some-model", location=BackendLocation.EXTERNAL)

    with pytest.raises(ProviderError):
        enforce_privacy_policy(backend, PrivacyClass.SENSITIVE_REVIEW_REQUIRED)


def test_external_backend_accepts_explicit_external_classes() -> None:
    backend = BackendInfo(
        provider="requesty", model="some-model", location=BackendLocation.EXTERNAL
    )

    enforce_privacy_policy(backend, PrivacyClass.EXTERNAL_ALLOWED)
    enforce_privacy_policy(backend, PrivacyClass.PUBLIC_OR_LOW_RISK)
