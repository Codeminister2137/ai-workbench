from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Consensus = Literal["full", "partial", "none"]


@dataclass(frozen=True)
class CouncilMember:
    name: str
    model: str
    system_prompt: str
    temperature: float = 0.7


@dataclass(frozen=True)
class Disagreement:
    holders: tuple[str, ...]
    point: str


@dataclass(frozen=True)
class SynthesisVerdict:
    """Machine-readable chair synthesis (slice 2).

    ``parse_ok`` is False when the chair prose did not follow the
    contract; fields are then best-effort (usually empty) and callers
    must fall back to the raw answer instead of trusting them.
    """

    agreed: tuple[str, ...]
    disagreements: tuple[Disagreement, ...]
    next_actions: tuple[str, ...]
    consensus: Consensus
    parse_ok: bool


_VERDICT_HEADERS = ("AGREED:", "DISAGREEMENTS:", "NEXT:", "CONSENSUS:")


def parse_synthesis(text: str) -> SynthesisVerdict:
    """Parse chair prose in the synthesis contract into a verdict.

    Contract: AGREED / DISAGREEMENTS / NEXT bullet sections plus a
    CONSENSUS line (full|partial|none). Disagreement bullets name
    holders before a colon or em-dash (``Alice, Bob: point``).
    """
    sections: dict[str, list[str]] = {header: [] for header in _VERDICT_HEADERS}
    current: str | None = None
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        upper = line.upper()
        if upper in _VERDICT_HEADERS:
            current = upper
            continue
        if upper.startswith("CONSENSUS:"):
            sections["CONSENSUS:"].append(line.split(":", 1)[1].strip())
            current = None
            continue
        if current is None or not line.startswith(("-", "*")):
            continue
        sections[current].append(line[1:].strip())
    consensus_raw = " ".join(sections["CONSENSUS:"]).strip().lower()
    consensus: Consensus = consensus_raw if consensus_raw in ("full", "partial", "none") else "none"
    disagreements: list[Disagreement] = []
    malformed = False
    for bullet in sections["DISAGREEMENTS:"]:
        holders, separator, point = bullet.partition(":")
        if not separator:
            holders, separator, point = bullet.partition("—")
        names = tuple(name.strip() for name in holders.split(",") if name.strip())
        if not separator or not names or not point.strip():
            malformed = True
            continue
        disagreements.append(Disagreement(holders=names, point=point.strip()))
    parse_ok = (
        bool(sections["AGREED:"] or sections["DISAGREEMENTS:"] or sections["NEXT:"])
        and consensus_raw in ("full", "partial", "none")
        and not malformed
    )
    return SynthesisVerdict(
        agreed=tuple(bullet for bullet in sections["AGREED:"] if bullet),
        disagreements=tuple(disagreements),
        next_actions=tuple(bullet for bullet in sections["NEXT:"] if bullet),
        consensus=consensus,
        parse_ok=parse_ok,
    )
