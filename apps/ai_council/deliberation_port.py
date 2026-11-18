"""Council adapter for the orchestrator deliberation port.

Lives on the council side so dependency direction stays clean:
orchestrator -> port <- council adapter, wired by the app layer.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from ai_orchestrator.deliberation import VerdictDict, validate_verdict
from config import CouncilConfig
from council import LocalCouncil
from storage import ConversationStore


class CouncilDeliberationPort:
    """DeliberationPort backed by council config + store."""

    def __init__(self, config: CouncilConfig, store: ConversationStore) -> None:
        self._config = config
        self._store = store

    def deliberate(
        self,
        question: str,
        members: list[dict[str, Any]],
        *,
        rounds: int = 3,
    ) -> VerdictDict:
        """Ask a member subset for a verdict; unknown names raise ValueError."""
        wanted = [str(entry.get("name", "")).strip() for entry in members or []]
        roster = list(self._config.members)
        if wanted:
            known = {member.name for member in roster}
            unknown = [name for name in wanted if name not in known]
            if unknown:
                raise ValueError(f"unknown council members: {', '.join(unknown)}")
            roster = [member for member in roster if member.name in set(wanted)]
        council = LocalCouncil(replace(self._config, members=roster), self._store)
        answers = council.ask(question, rounds=rounds)
        synthesis = next(
            (
                entry
                for entry in reversed(answers)
                if str(entry.get("member", "")).endswith(":synthesis")
            ),
            {},
        )
        verdict = synthesis.get("verdict")
        if not isinstance(verdict, dict):
            raise RuntimeError("council returned no structured verdict")
        return validate_verdict(verdict)
