"""Host composition for Mai relay R and the complete orchestrator fallback tree."""

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from ai_agent.relay_client import decode_request, message_payload, response_payload
from ai_orchestrator import ExecutionTarget
from ai_provider.contracts import AIMessage, AIRequest, AIResponse, PrivacyClass
from ai_provider.execution_fallback import FallbackSession
from relay_mailbox import HostMediator, RelayError, RelayGrant


def build_mai_relay(
    mailbox: str,
    grant: RelayGrant,
    session: FallbackSession,
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
        complete_request=HostRelayInference(session, execute, privacy=privacy),
    )


class HostRelayInference:
    """Bind one run to its host-owned fallback session and scoped executor.

    The supplied executor MUST enforce live admission, shared budget, privacy,
    timeout and cancellation for EVERY target attempt. It must never run worker
    tools on the host. No clients are constructed here and no auth enters files.
    FallbackSession retains exhausted billing buckets/routes across turns and
    delegates candidate selection to the orchestrator without a model-count cap.
    """

    def __init__(
        self,
        session: FallbackSession,
        execute: Callable[[ExecutionTarget, AIRequest], AIResponse],
        *,
        privacy: PrivacyClass,
    ) -> None:
        if privacy.value != session.profile.privacy_class.value:
            raise ValueError("relay privacy must match the host routing profile")
        self.session = session
        self.execute = execute
        self.privacy = privacy
        self._history: tuple[AIMessage, ...] = ()
        self._last_route: str | None = None

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

        completed_request = request

        def execute(target: ExecutionTarget, _: str) -> AIResponse:
            nonlocal completed_request
            current_request = request
            if target.route_id != self._last_route:
                current_request = replace(
                    request,
                    messages=tuple(
                        replace(message, continuation=None) for message in request.messages
                    ),
                )
            completed_request = current_request
            return self.execute(target, current_request)

        response = self.session.run(
            "Relay inference turn",
            execute,
            lambda _: False,
            observe=lambda _: "",
        )
        self._history = (*completed_request.messages, response.message)
        self._last_route = self.session.current.route_id
        return response_payload(response)
