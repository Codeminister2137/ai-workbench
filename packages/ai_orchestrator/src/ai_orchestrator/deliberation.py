"""Deliberation port: orchestrator-side contract for council verdicts.

The Orchestrator depends on this port, never on council implementations:
an app layer injects the adapter (see ai_council/deliberation_port.py).
Verdicts are plain data so routing decisions can consume them without
importing council code.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, TypedDict


class DisagreementDict(TypedDict):
    holders: list[str]
    point: str


class VerdictDict(TypedDict):
    agreed: list[str]
    disagreements: list[DisagreementDict]
    next_actions: list[str]
    consensus: str
    parse_ok: bool


class DeliberationPort(Protocol):
    """Ask a council for a structured verdict on a question."""

    def deliberate(
        self,
        question: str,
        members: list[dict[str, Any]],
        *,
        rounds: int = 3,
    ) -> VerdictDict:
        """Return the chair's verdict; raises RuntimeError when unavailable."""
        ...


CONSENSUS_VALUES = frozenset({"full", "partial", "none"})


def validate_verdict(payload: Mapping[str, Any]) -> VerdictDict:
    """Coerce raw adapter output to VerdictDict; raises ValueError when malformed."""
    if not isinstance(payload, Mapping):
        raise ValueError("verdict must be an object")
    agreed = payload.get("agreed", [])
    disagreements = payload.get("disagreements", [])
    next_actions = payload.get("next_actions", [])
    consensus = payload.get("consensus")
    if (
        not isinstance(agreed, list)
        or not isinstance(disagreements, list)
        or not isinstance(next_actions, list)
        or consensus not in CONSENSUS_VALUES
    ):
        raise ValueError("verdict has malformed sections or consensus")
    for item in disagreements:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("holders"), list)
            or not isinstance(item.get("point"), str)
        ):
            raise ValueError("verdict disagreement needs holders + point")
    return VerdictDict(
        agreed=[str(point) for point in agreed],
        disagreements=[
            {"holders": [str(name) for name in item["holders"]], "point": item["point"]}
            for item in disagreements
        ],
        next_actions=[str(action) for action in next_actions],
        consensus=consensus,
        parse_ok=bool(payload.get("parse_ok", False)),
    )


def request_verdict(
    port: DeliberationPort,
    question: str,
    members: list[dict[str, Any]] | None = None,
    *,
    rounds: int = 3,
) -> VerdictDict:
    """Delegate one question to the injected council port (sync call).

    The orchestrator never imports council code: the app layer injects
    the adapter. Adapter output is re-validated at the seam so a
    non-conformant adapter fails here instead of corrupting routing.
    Consuming the verdict for routing decisions is follow-up work.
    """
    if not isinstance(question, str) or not question.strip():
        raise ValueError("deliberation needs a non-empty question")
    if not isinstance(rounds, int) or rounds < 1:
        raise ValueError("deliberation needs at least one round")
    return validate_verdict(port.deliberate(question, members or [], rounds=rounds))
