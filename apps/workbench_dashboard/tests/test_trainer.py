"""Bank-first trainer: covered answers quote facts, gaps file clarifications."""

from __future__ import annotations

from trainer import (
    answer_from_bank,
    ask_trainer,
    backfill_clarification,
    gap_check_profile,
    route_gap_check,
    significant_tokens,
)


def test_significant_tokens_drop_stopwords_and_shorts() -> None:
    assert significant_tokens("What languages do I know?") == ("languages",)
    assert significant_tokens("Docker, AWS and Linux!") == ("docker", "linux")


def test_covered_answer_quotes_supporting_facts() -> None:
    answer = answer_from_bank(
        "Do I know Polish and English?",
        ["Polish native", "English C2/fluent", "Docker, AWS"],
    )
    assert answer.covered is True
    assert answer.answer_text is not None
    assert "Polish native" in answer.answer_text
    assert "English C2/fluent" in answer.answer_text
    assert "Docker" not in answer.answer_text
    assert answer.missing_hints == ()


def test_uncovered_names_missing_hints_without_guessing() -> None:
    answer = answer_from_bank("What languages do I know?", ["Docker, AWS"])
    assert answer.covered is False
    assert answer.answer_text is None
    assert set(answer.missing_hints) == {"languages"}


def test_empty_question_is_not_covered() -> None:
    answer = answer_from_bank("   ", ["Docker"])
    assert answer.covered is False
    assert answer.missing_hints == ()


def test_backfill_draft_points_at_missing_topics() -> None:
    draft = backfill_clarification("What languages?", ("languages",))
    assert "languages" in draft["body"]
    assert "Nothing was guessed" in draft["body"]


def test_ask_trainer_answers_when_covered(tmp_path) -> None:
    from dashboard_stores import DashboardStores

    stores = DashboardStores(tmp_path / "data")
    outcome = ask_trainer("Do I know Polish?", ["Polish native"], stores)
    assert outcome == {"covered": True, "answer_text": "- Polish native"}
    assert stores.open_inbox_count() == 0


def test_ask_trainer_files_and_reuses_clarification(tmp_path) -> None:
    from dashboard_stores import DashboardStores

    stores = DashboardStores(tmp_path / "data")
    first = ask_trainer("Do I know Klingon?", ["Polish native"], stores)
    assert first["covered"] is False
    assert first["reused"] is False
    second = ask_trainer("Do I know Klingon?", ["Polish native"], stores)
    assert second["covered"] is False
    assert second["reused"] is True
    assert second["clarification_id"] == first["clarification_id"]
    clar_id = first["clarification_id"]
    assert isinstance(clar_id, str)
    item = stores.inbox.get(clar_id)
    assert item is not None
    assert item["type"] == "clarification"
    assert item["assignee"] == "owner"


def test_gap_check_profile_is_local_only() -> None:
    from ai_orchestrator.models import CostPolicyTier, PrivacyClass

    profile = gap_check_profile()
    assert profile.privacy_class is PrivacyClass.LOCAL_ONLY
    assert profile.cost_policy_tier is CostPolicyTier.LOCAL_ONLY


def test_route_gap_check_selects_without_pinning() -> None:
    from ai_orchestrator import (
        AccessMethod,
        AccessRoute,
        AuthMethod,
        BackendLocation,
        BillingSource,
        CostPolicyTier,
        ModelBackend,
        ModelCapabilities,
        ModelCatalogEntry,
        QualityThreshold,
    )

    def entry(route: str) -> ModelCatalogEntry:
        return ModelCatalogEntry(
            backend=ModelBackend(
                route=AccessRoute(
                    route_id=route,
                    provider="test",
                    product="test",
                    model=route,
                    location=BackendLocation.LOCAL,
                    access_method=AccessMethod.LOCAL_RUNTIME,
                    auth_method=AuthMethod.NONE,
                    billing_source=BillingSource.LOCAL_FREE,
                    cost_policy_tier=CostPolicyTier.LOCAL_ONLY,
                ),
                capabilities=ModelCapabilities(chat=True, tools=True),
            ),
            quality=QualityThreshold.STANDARD,
        )

    routed = route_gap_check("Is the bank enough?", (entry("local-a"), entry("local-b")))
    assert routed["ready"] == "True"
    assert routed["route_id"] in ("local-a", "local-b")
    assert "model" in routed and "provider" in routed


def test_route_gap_check_reports_unroutable() -> None:
    routed = route_gap_check("Is the bank enough?", ())
    assert routed["ready"] == "False"
    assert routed["reason"]
