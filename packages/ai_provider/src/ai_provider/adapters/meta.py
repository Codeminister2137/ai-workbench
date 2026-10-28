"""Meta Model API Responses adapter.

Meta exposes an OpenAI-compatible Responses protocol at ``api.meta.ai/v1``, so
this adapter inherits the generic Responses client. It adds only Meta's endpoint
default, Muse model admission and a non-persistent ``store: false`` request.

Admission refuses two things the generic base cannot know about:

* model ids outside the ``muse-`` family, which the endpoint does not serve;
* Contributor variants, which Meta documents as trading content-training
  permission for discounted pricing. Sending repository content there is a
  privacy decision this adapter does not make on a caller's behalf.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_provider.adapters.openai_responses import OpenAIResponsesChatClient
from ai_provider.config import BackendConfig, ProviderKind
from ai_provider.contracts import AIRequest
from ai_provider.errors import ProviderError, ProviderErrorCategory

META_BASE_URL = "https://api.meta.ai/v1"
MUSE_MODEL_PREFIX = "muse-"
CONTRIBUTOR_MODEL_SUFFIX = "-contributor"


@dataclass(slots=True)
class MetaResponsesChatClient(OpenAIResponsesChatClient):
    """Chat client for Meta Muse Spark models on the Responses protocol."""

    config: BackendConfig

    def __post_init__(self) -> None:
        if self.config.provider is not ProviderKind.META:
            raise ProviderError(
                "Meta responses client requires ProviderKind.META.",
                category=ProviderErrorCategory.CONFIGURATION,
                provider=self.config.provider.value,
            )
        _require_muse_model(self.config.model, provider=self.config.provider.value)

    @property
    def base_url(self) -> str:
        return (self.config.base_url or META_BASE_URL).rstrip("/")

    def _responses_payload(self, request: AIRequest, *, stream: bool) -> dict[str, Any]:
        _require_muse_model(
            request.model or self.config.model,
            provider=self.config.provider.value,
        )
        payload = super()._responses_payload(request, stream=stream)
        # Repository content is never stored on Meta's side. Server-side response
        # storage would need its own privacy decision, so it stays off here.
        payload["store"] = False
        return payload


def _require_muse_model(model: str, *, provider: str) -> None:
    """Refuse models the Meta route cannot serve or must not send content to."""

    normalized = model.strip().casefold()
    if not normalized.startswith(MUSE_MODEL_PREFIX):
        raise ProviderError(
            f"Meta Model API models must start with {MUSE_MODEL_PREFIX!r}; got {model!r}.",
            category=ProviderErrorCategory.CONFIGURATION,
            provider=provider,
        )
    if normalized.endswith(CONTRIBUTOR_MODEL_SUFFIX):
        raise ProviderError(
            "Meta Contributor variants train on request data; this route refuses them.",
            category=ProviderErrorCategory.PRIVACY_POLICY,
            provider=provider,
        )
