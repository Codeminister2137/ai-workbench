"""Orchestrator-routed CV/message suggestion pass over match verdicts.

Deterministic prompt building plus a neutral routing seam: callers route
through the Orchestrator, adapt the returned execution target to an
executor, and record the outcome per package. Live model calls happen only
through explicit executor use, never at import or prompt-build time.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from evidence import RequirementVerdict
from models import CandidateProfile, JobVacancy, utc_now_iso

if TYPE_CHECKING:
    from ai_orchestrator.planner import ExecutionPlan

SUGGESTION_TASK_TYPE = "general"
LOCAL_PROVIDERS = frozenset({"ollama"})
SUPPORTED_EXECUTOR_PROVIDERS = frozenset({"ollama", "meta"})


def build_suggestion_prompt(
    vacancy: JobVacancy,
    verdicts: tuple[RequirementVerdict, ...],
    profile: CandidateProfile,
) -> str:
    """Build the deterministic tailoring prompt for one vacancy."""
    verdict_lines = [
        f"- {verdict.requirement}: {verdict.verdict} "
        f"[{verdict.status.value}]"
        + (
            f" (evidence: {', '.join(verdict.source_kinds)})"
            if verdict.source_kinds
            else " (no recorded evidence)"
        )
        for verdict in verdicts
    ]
    skill_lines = [
        f"- {name}: {evidence.status.value}" + (f" — {evidence.notes}" if evidence.notes else "")
        for name, evidence in sorted(profile.skills.items())
    ]
    return "\n".join(
        [
            "Tailor application material for the vacancy below using ONLY the",
            "evidenced skills. Never invent experience, tools, or credentials.",
            "Reply with numbered suggestion lines, then a PROHIBITED section",
            "listing claims that must NOT be made.",
            "",
            f"VACANCY: {vacancy.title} at {vacancy.company} ({vacancy.location})",
            f"DESCRIPTION: {vacancy.description or '(none provided)'}",
            "",
            "REQUIREMENT VERDICTS:",
            *verdict_lines,
            "",
            "EVIDENCED SKILLS:",
            *skill_lines,
        ]
    )


def parse_suggestions(text: str) -> tuple[str, ...]:
    """Split a model reply into stripped non-empty suggestion lines."""
    return tuple(line.strip() for line in text.splitlines() if line.strip())


@dataclass(frozen=True, slots=True)
class SuggestionRecord:
    """Recorded outcome of one routed suggestion pass."""

    route_id: str
    provider: str
    model: str
    cost_policy_tier: str
    prompt_sha256: str
    suggestions: tuple[str, ...] = ()
    created_at_utc: str = field(default_factory=utc_now_iso)


def route_suggestion_task(
    catalog: Any,
    prompt: str,
    *,
    cost_policy_tier: str = "local_only",
    privacy_class: str = "local_only",
) -> ExecutionPlan:
    """Route the tailoring task through the Orchestrator (no model call)."""
    from ai_orchestrator import (  # noqa: PLC0415 - optional orchestrated path
        CostPolicyTier,
        PrivacyClass,
        TaskProfile,
        TaskType,
        prepare_execution,
    )

    profile = TaskProfile(
        task_type=TaskType(SUGGESTION_TASK_TYPE),
        privacy_class=PrivacyClass(privacy_class),
        cost_policy_tier=CostPolicyTier(cost_policy_tier),
    )
    result = prepare_execution(prompt, profile, catalog, review_prompt=False)
    if not result.is_ready or result.execution_plan is None:
        raise ValueError(f"suggestion routing failed: {result.failure_reason}")
    return result.execution_plan


def execute_suggestion_plan(
    plan: ExecutionPlan,
    prompt: str,
    *,
    timeout_seconds: float = 180.0,
    max_output_tokens: int = 512,
) -> str:
    """Execute a routed plan through the matching provider client."""
    from ai_provider.adapters.meta import META_BASE_URL, MetaResponsesChatClient
    from ai_provider.adapters.ollama import OllamaChatClient
    from ai_provider.config import BackendConfig, ProviderKind
    from ai_provider.contracts import (
        AIMessage,
        AIRequest,
        MessageRole,
    )
    from ai_provider.contracts import (
        PrivacyClass as ProviderPrivacy,
    )
    from ai_provider.secrets import read_secret_key

    target = plan.target
    if target.provider not in SUPPORTED_EXECUTOR_PROVIDERS:
        raise ValueError(f"unsupported suggestion executor: {target.provider}")
    if target.provider == "ollama":
        client: Any = OllamaChatClient(
            BackendConfig(
                provider=ProviderKind.OLLAMA,
                model=target.model,
                base_url=target.base_url or "http://127.0.0.1:11434",
                timeout_seconds=timeout_seconds,
            )
        )
        privacy = ProviderPrivacy.LOCAL_ONLY
    else:
        repo_root = Path(__file__).resolve().parents[3]
        key = read_secret_key(
            repo_root / ".env",
            "META_API_KEY",
            label="Meta API credential",
        )
        client = MetaResponsesChatClient(
            BackendConfig(
                provider=ProviderKind.META,
                model=target.model,
                base_url=target.base_url or META_BASE_URL,
                api_key=key,
                timeout_seconds=timeout_seconds,
            )
        )
        privacy = ProviderPrivacy.EXTERNAL_ALLOWED
    request = AIRequest(
        messages=(AIMessage(role=MessageRole.USER, content=prompt),),
        model=target.model,
        max_output_tokens=max_output_tokens,
        privacy_class=privacy,
    )
    return client.complete(request).message.content


def record_suggestions(plan: ExecutionPlan, prompt: str, response_text: str) -> SuggestionRecord:
    """Build the per-package record for one executed suggestion pass."""
    target = plan.target
    return SuggestionRecord(
        route_id=target.route_id,
        provider=target.provider,
        model=target.model,
        cost_policy_tier=target.cost_policy_tier.value,
        prompt_sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        suggestions=parse_suggestions(response_text),
    )
