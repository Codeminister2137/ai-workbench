"""Host composition for Mai relay R and the complete orchestrator fallback tree."""

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from ai_agent.relay_client import decode_request, message_payload, response_payload
from ai_orchestrator import ExecutionTarget, ModelCatalogEntry, TaskProfile
from ai_provider.contracts import AIMessage, AIRequest, AIResponse, PrivacyClass
from ai_provider.fallback_executor import FallbackExecutor
from relay_mailbox import HostMediator, RelayError, RelayGrant


def build_mai_relay(
    mailbox: str,
    grant: RelayGrant,
    profile: TaskProfile,
    catalog: tuple[ModelCatalogEntry, ...],
    initial: ExecutionTarget,
    execute: Callable[[ExecutionTarget, AIRequest], AIResponse],
    *,
    privacy: PrivacyClass,
) -> HostMediator:
    """Build a Mai-only mailbox mediator; legacy fixed-model turns fail closed."""

    def refuse_legacy(*_: Any) -> dict[str, Any]:
        raise RelayError("Mai requires the neutral request protocol")

    return HostMediator(
        mailbox,
        grant,
        refuse_legacy,
        complete_request=HostRelayInference(profile, catalog, initial, execute, privacy=privacy),
    )


class HostRelayInference:
    """Bind one run to its host-owned fallback executor and scoped executor.

    The supplied executor MUST enforce live admission, shared budget, privacy,
    timeout and cancellation for EVERY target attempt. It must never run worker
    tools on the host. No clients are constructed here and no auth enters files.
    The executor retains exhausted billing buckets/routes across turns and
    delegates candidate selection to the orchestrator without a model-count cap.
    """

    def __init__(
        self,
        profile: TaskProfile,
        catalog: tuple[ModelCatalogEntry, ...],
        initial: ExecutionTarget,
        execute: Callable[[ExecutionTarget, AIRequest], AIResponse],
        *,
        privacy: PrivacyClass,
        excluded_route_ids: frozenset[str] = frozenset(),
        deadline: float | None = None,
        priority: tuple[str, ...] = (),
    ) -> None:
        if privacy.value != profile.privacy_class.value:
            raise ValueError("relay privacy must match the host routing profile")
        self.execute_turn = execute
        self.privacy = privacy
        self._turn_request: AIRequest | None = None
        self._turn_sent: AIRequest | None = None
        self.executor = FallbackExecutor(
            profile,
            catalog,
            initial,
            execute=self._invoke,
            observe=lambda _: "",
            is_limited=lambda _: False,
            excluded_route_ids=excluded_route_ids,
            deadline=deadline,
            priority=priority,
        )
        self._history: tuple[AIMessage, ...] = ()
        self._last_route: str | None = None

    def _invoke(self, target: ExecutionTarget, _: str) -> AIResponse:
        request = self._turn_request
        assert request is not None
        current_request = request
        if target.route_id != self._last_route:
            current_request = replace(
                request,
                messages=tuple(replace(message, continuation=None) for message in request.messages),
            )
        self._turn_sent = current_request
        return self.execute_turn(target, current_request)

    def __call__(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = decode_request(payload, privacy=self.privacy)
        # Restore opaque state only for an unchanged observable history prefix.
        # Compaction/rewrites invalidate it rather than reattaching stale state.
        history = self._history
        if (
            history
            and len(history) <= len(request.messages)
            and all(
                message_payload(old) == message_payload(new)
                for old, new in zip(history, request.messages, strict=False)
            )
        ):
            request = replace(
                request,
                messages=history + request.messages[len(history) :],
            )

        self._turn_request = request
        response = self.executor.run("Relay inference turn")
        sent = self._turn_sent
        assert sent is not None
        self._history = (*sent.messages, response.message)
        self._last_route = self.executor.current.route_id
        return response_payload(response)
