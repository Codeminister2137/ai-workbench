"""Session-handoff prompt: pressure detection plus resume-prompt rendering.

Smallest slice: pure functions with tests. Live wiring (which loop calls
detection, at which cadence, and which thresholds emit a prompt) needs
owner confirmation and is deliberately absent here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Provisional emit thresholds. Tuned values and live wiring need owner
# confirmation before any loop calls assess_pressure to emit prompts.
PRESSURE_TOKEN_FRACTION_ELEVATED = 0.70
PRESSURE_TOKEN_FRACTION_HIGH = 0.88
PRESSURE_TURNS_ELEVATED = 40
PRESSURE_TURNS_HIGH = 80


@dataclass(frozen=True, slots=True)
class SessionPressure:
    """Observed session load; unknown fields stay None, never guessed."""

    tokens_used: int | None = None
    token_budget: int | None = None
    turns: int = 0
    consecutive_errors: int = 0


@dataclass(frozen=True, slots=True)
class HandoffPointers:
    """Resume pointers for the next session (paths, ids, branches)."""

    context_file: str = "CURRENT_CONTEXT.md"
    branch: str = "develop"
    base_commit: str = ""
    inbox_ids: tuple[str, ...] = ()
    run_ids: tuple[str, ...] = ()
    extra: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class HandoffBounds:
    """Finite allowances the next session must respect."""

    bounds_id: str = ""
    notes: tuple[str, ...] = ()


def assess_pressure(pressure: SessionPressure) -> str:
    """Rate context pressure as low, elevated, or high (pure assessment).

    Token fraction dominates when both sides are known; turn count is
    the fallback signal; repeated errors escalate one step. Unknown
    inputs never inflate the rating.
    """
    fraction = None
    if (
        pressure.tokens_used is not None
        and pressure.token_budget is not None
        and pressure.token_budget > 0
        and pressure.tokens_used >= 0
    ):
        fraction = pressure.tokens_used / pressure.token_budget
    if fraction is not None:
        if fraction >= PRESSURE_TOKEN_FRACTION_HIGH:
            level = "high"
        elif fraction >= PRESSURE_TOKEN_FRACTION_ELEVATED:
            level = "elevated"
        else:
            level = "low"
    elif pressure.turns >= PRESSURE_TURNS_HIGH:
        level = "high"
    elif pressure.turns >= PRESSURE_TURNS_ELEVATED:
        level = "elevated"
    else:
        level = "low"
    if pressure.consecutive_errors >= 3:
        level = {"low": "elevated", "elevated": "high", "high": "high"}[level]
    return level


@dataclass(frozen=True, slots=True)
class HandoffState:
    """What the next session must know to resume safely."""

    summary: str = ""
    next_action: str = ""
    completion_condition: str = ""
    pointers: HandoffPointers = field(default_factory=HandoffPointers)
    bounds: HandoffBounds = field(default_factory=HandoffBounds)


def render_handoff_prompt(state: HandoffState) -> str:
    """Render a copy-paste resume prompt (no side effects)."""
    lines = [
        "Resume this session from repository state (do not rely on transcript).",
        "",
        f"State: {state.summary or '(none recorded)'}",
        f"Next action: {state.next_action or '(none recorded)'}",
        f"Done when: {state.completion_condition or '(none recorded)'}",
        "",
        "Pointers:",
        f"- context: {state.pointers.context_file}",
        f"- branch: {state.pointers.branch}",
    ]
    if state.pointers.base_commit:
        lines.append(f"- base commit: {state.pointers.base_commit}")
    lines.extend(f"- inbox: {item}" for item in state.pointers.inbox_ids)
    lines.extend(f"- run: {item}" for item in state.pointers.run_ids)
    lines.extend(f"- {item}" for item in state.pointers.extra)
    if state.bounds.bounds_id or state.bounds.notes:
        lines += ["", f"Bounds ({state.bounds.bounds_id or 'unnamed'}):"]
        lines.extend(f"- {note}" for note in state.bounds.notes)
    return "\n".join(lines).strip() + "\n"
