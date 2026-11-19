"""Bank-first KnowMe trainer: answer from facts, ask on gaps.

Owner answers A (f12017f8 + 2a98a139, 2026-11-18): the trainer reads the
KnowMe bank and answers only from banked facts. When facts are missing it
files an inbox clarification to populate the bank instead of guessing.
Sufficiency judging (the gap check) routes through the Orchestrator with
privacy + cheapest-first cost inputs; no model is ever pinned. Running the
routed judgment is follow-up work — this slice routes and records.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_orchestrator.models import TaskProfile

_WORD_RE = re.compile(r"[a-z0-9][a-z0-9_/-]*")
_STOPWORDS = frozenset(
    {
        "what",
        "whats",
        "which",
        "who",
        "whom",
        "whose",
        "when",
        "where",
        "how",
        "does",
        "do",
        "is",
        "are",
        "was",
        "were",
        "the",
        "a",
        "an",
        "and",
        "or",
        "for",
        "of",
        "my",
        "me",
        "i",
        "you",
        "your",
        "we",
        "our",
        "it",
        "its",
        "in",
        "on",
        "at",
        "to",
        "with",
        "about",
        "tell",
        "know",
        "list",
        "give",
    }
)


@dataclass(frozen=True, slots=True)
class BankAnswer:
    """Outcome of answering one question from banked facts."""

    covered: bool
    answer_text: str | None
    missing_hints: tuple[str, ...]


def significant_tokens(text: str) -> tuple[str, ...]:
    """Lowercased content tokens: length > 3, stopwords dropped, order kept."""
    seen: list[str] = []
    for token in _WORD_RE.findall(text.lower()):
        if len(token) > 3 and token not in _STOPWORDS and token not in seen:
            seen.append(token)
    return tuple(seen)


def answer_from_bank(question: str, facts: list[str]) -> BankAnswer:
    """Answer strictly from banked facts; gaps stay gaps (never guessed).

    A question is covered only when every significant token appears in at
    least one fact. Covered answers quote the supporting facts; uncovered
    ones name the missing tokens as backfill hints.
    """
    wanted = significant_tokens(question)
    if not wanted:
        return BankAnswer(covered=False, answer_text=None, missing_hints=())
    haystacks = [fact.lower() for fact in facts]
    missing = tuple(token for token in wanted if not any(token in hay for hay in haystacks))
    if missing:
        return BankAnswer(covered=False, answer_text=None, missing_hints=missing)
    supporting = [fact for fact in facts if any(token in fact.lower() for token in wanted)]
    return BankAnswer(
        covered=True, answer_text="\n".join(f"- {fact}" for fact in supporting), missing_hints=()
    )


def backfill_clarification(question: str, missing: tuple[str, ...]) -> dict[str, str]:
    """Draft the inbox clarification that populates the bank for a gap."""
    hints = ", ".join(missing) if missing else "more detail"
    return {
        "title": f"Trainer needs facts: {question[:60]}",
        "body": (
            f"The trainer could not answer from the KnowMe bank:\n\n{question}\n\n"
            f"Missing topics: {hints}\n\n"
            "Reply with the facts (one per line) and they will be banked for "
            "next time. Nothing was guessed."
        ),
    }


def gap_check_profile() -> TaskProfile:
    """TaskProfile routing the sufficiency judgment: local-only + cheapest.

    Privacy-matters and hobby-tier cost (owner answer 2a98a139) map to the
    LOCAL_ONLY privacy class and cost ceiling; the Orchestrator picks the
    actual route from the catalog. Imported lazily — ai_orchestrator is an
    optional peer, not a hard dashboard dependency.
    """
    from ai_orchestrator.models import (
        CostPolicyTier,
        PrivacyClass,
        QualityThreshold,
        TaskCapability,
        TaskProfile,
        TaskType,
    )

    return TaskProfile(
        task_type=TaskType.GENERAL,
        privacy_class=PrivacyClass.LOCAL_ONLY,
        cost_policy_tier=CostPolicyTier.LOCAL_ONLY,
        quality_threshold=QualityThreshold.STANDARD,
        required_capabilities=frozenset({TaskCapability.CHAT}),
    )


def route_gap_check(question: str, catalog: tuple) -> dict[str, str | None]:
    """Route one sufficiency judgment; returns the chosen target, runs nothing.

    The returned route/model names the model the Orchestrator selected for
    judging whether the bank covers ``question``. Executing that judgment
    is follow-up work; ``ready=False`` carries the reason when unroutable.
    """
    from ai_orchestrator import prepare_execution

    profile = gap_check_profile()
    try:
        prepared = prepare_execution(question, profile, catalog, review_prompt=False)
    except Exception as exc:  # noqa: BLE001 - routing failure is data, not a crash
        return {"ready": "False", "reason": str(exc)[:300]}
    plan = prepared.execution_plan
    if plan is None:
        return {
            "ready": "False",
            "reason": prepared.failure_reason or "no execution plan",
        }
    target = plan.target
    return {
        "ready": "True",
        "route_id": target.route_id,
        "model": target.model,
        "provider": target.provider,
    }


def ask_trainer(
    question: str,
    facts: list[str],
    stores: object,
) -> dict[str, object]:
    """Answer from the bank or file a clarification; returns the outcome.

    Covered questions answer inline. Gaps file one inbox clarification
    (duplicate-safe: an open clarification for the same question is reused)
    and return its id for the caller to surface.
    """
    answer = answer_from_bank(question, facts)
    if answer.covered:
        return {"covered": True, "answer_text": answer.answer_text}
    draft = backfill_clarification(question, answer.missing_hints)
    inbox = stores.inbox  # type: ignore[attr-defined]
    items, _total = inbox.list(limit=200)
    for item in items:
        if (
            isinstance(item, dict)
            and item.get("status") == "open"
            and item.get("type") == "clarification"
            and item.get("title") == draft["title"]
        ):
            return {"covered": False, "clarification_id": item["id"], "reused": True}
    created = stores.create_inbox_task(  # type: ignore[attr-defined]
        title=draft["title"], body=draft["body"], task_type="clarification"
    )
    return {"covered": False, "clarification_id": created["id"], "reused": False}
