"""Auto-handoff slice: pressure detection plus prompt rendering."""

from __future__ import annotations

from ai_agent.handoff_prompt import (
    HandoffBounds,
    HandoffPointers,
    HandoffState,
    SessionPressure,
    assess_pressure,
    render_handoff_prompt,
)


def test_pressure_prefers_token_fraction() -> None:
    assert assess_pressure(SessionPressure(tokens_used=10, token_budget=100)) == "low"
    assert assess_pressure(SessionPressure(tokens_used=70, token_budget=100)) == "elevated"
    assert assess_pressure(SessionPressure(tokens_used=88, token_budget=100)) == "high"


def test_pressure_falls_back_to_turns() -> None:
    assert assess_pressure(SessionPressure(turns=10)) == "low"
    assert assess_pressure(SessionPressure(turns=40)) == "elevated"
    assert assess_pressure(SessionPressure(turns=80)) == "high"


def test_pressure_ignores_unknowns_and_escalates_on_errors() -> None:
    assert assess_pressure(SessionPressure()) == "low"
    assert assess_pressure(SessionPressure(tokens_used=5)) == "low"
    assert assess_pressure(SessionPressure(token_budget=0, tokens_used=10)) == "low"
    assert assess_pressure(SessionPressure(turns=10, consecutive_errors=3)) == "elevated"
    assert assess_pressure(SessionPressure(turns=80, consecutive_errors=9)) == "high"


def test_render_includes_state_pointers_and_bounds() -> None:
    state = HandoffState(
        summary="Battery running",
        next_action="Score arms",
        completion_condition="scores.json written",
        pointers=HandoffPointers(
            base_commit="d498eff", inbox_ids=("a",), run_ids=("r",), extra=("x",)
        ),
        bounds=HandoffBounds(bounds_id="b1", notes=("30min caps",)),
    )
    prompt = render_handoff_prompt(state)
    for needle in (
        "Battery running",
        "Next action: Score arms",
        "Done when: scores.json written",
        "context: CURRENT_CONTEXT.md",
        "branch: develop",
        "base commit: d498eff",
        "inbox: a",
        "run: r",
        "- x",
        "Bounds (b1):",
        "30min caps",
    ):
        assert needle in prompt


def test_render_marks_missing_state_without_guessing() -> None:
    prompt = render_handoff_prompt(HandoffState())
    assert "(none recorded)" in prompt
    assert "Bounds" not in prompt
