from __future__ import annotations

from ai_provider.contracts import BackendInfo, BackendLocation, PrivacyClass
from ai_provider.errors import ProviderError, ProviderErrorCategory


def enforce_privacy_policy(backend: BackendInfo, privacy_class: PrivacyClass) -> None:
    if backend.location is BackendLocation.LOCAL:
        return

    if privacy_class is PrivacyClass.LOCAL_ONLY:
        raise ProviderError(
            "Local-only requests cannot be sent to an external backend.",
            category=ProviderErrorCategory.PRIVACY_POLICY,
            retryable=False,
            provider=backend.provider,
        )

    if privacy_class is PrivacyClass.SENSITIVE_REVIEW_REQUIRED:
        raise ProviderError(
            "Sensitive requests require explicit review before external processing.",
            category=ProviderErrorCategory.PRIVACY_POLICY,
            retryable=False,
            provider=backend.provider,
        )
