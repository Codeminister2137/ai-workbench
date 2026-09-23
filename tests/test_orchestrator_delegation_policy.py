from ai_orchestrator import DelegationKind, TaskType, assess_delegation


def test_coding_context_work_is_suitable_for_local_delegation() -> None:
    decision = assess_delegation(
        task_type=TaskType.CODING,
        delegation_kind=DelegationKind.CONTEXT_EXTRACTION,
    )

    assert decision.allowed is True


def test_coding_architecture_decisions_stay_with_primary_model() -> None:
    decision = assess_delegation(
        task_type=TaskType.CODING,
        delegation_kind=DelegationKind.ARCHITECTURAL_RECOMMENDATION,
    )

    assert decision.allowed is False


def test_coding_prompt_refinement_is_bounded_local_support() -> None:
    decision = assess_delegation(
        task_type=TaskType.CODING,
        delegation_kind=DelegationKind.PROMPT_REFINEMENT,
    )

    assert decision.allowed is True
