"""Deterministic vacancy-to-profile matching (M2, no AI).

Builds a `MatchReport` from the evidence verdicts: score, best CV
variant by title/role overlap, extractive per-requirement suggestions,
and warning flags. Suggestions never invent qualifications — gaps are
framed as document-or-drop guidance. The generative tailoring pass
(S3) needs the D2 model/cost grant and lives behind the Orchestrator.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from evidence import RequirementVerdict, analyze_vacancy_fit
from models import CandidateProfile, EvidenceStatus, JobVacancy


@dataclass(frozen=True, slots=True)
class MatchSuggestion:
    """Extractive guidance for one requirement; never an invented claim."""

    requirement: str
    suggestion: str
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MatchReport:
    """Match/tailor core output; JSON-serializable for the ledger."""

    vacancy_id: str
    match_score: float
    verdicts: tuple[RequirementVerdict, ...]
    suggested_cv_variant: str | None
    variant_basis: str
    suggestions: tuple[MatchSuggestion, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def _variant_overlap(variant_words: set[str], title_words: set[str]) -> int:
    return len(variant_words & title_words)


def pick_cv_variant(vacancy: JobVacancy, profile: CandidateProfile) -> tuple[str | None, str]:
    """Rank CV variants by title/role keyword overlap (deterministic).

    Returns (variant_id, basis). No overlap means no suggestion rather
    than a guess — flagging uncertainty beats a confident miss.
    """
    title_words = {word.strip(".,()/").casefold() for word in vacancy.title.split()}
    title_words = {word for word in title_words if len(word) > 2}
    scored: list[tuple[int, str]] = []
    for variant_id, variant in profile.cv_variants.items():
        haystack = f"{variant.target_role} {variant.description}"
        variant_words = {
            word.strip(".,()/").casefold() for word in haystack.split() if len(word) > 2
        }
        scored.append((_variant_overlap(variant_words, title_words), variant_id))
    scored.sort(reverse=True)
    if not scored or scored[0][0] == 0:
        return None, "no title/role keyword overlap with any CV variant"
    best, runner_up = scored[0], (scored[1] if len(scored) > 1 else (0, ""))
    if best[0] == runner_up[0]:
        return None, f"tie at {best[0]} keyword hits between {best[1]} and {runner_up[1]}"
    return best[1], f"{best[0]} title/role keyword hits"


def _suggestion_for(verdict: RequirementVerdict) -> MatchSuggestion:
    refs = tuple(f"{verdict.requirement}:{kind}" for kind in verdict.source_kinds)
    if verdict.status is EvidenceStatus.DEMONSTRATED:
        text = f"Lead with {verdict.requirement}: demonstrated, cite the evidence."
    elif verdict.status is EvidenceStatus.ADJACENT:
        text = (
            f"Frame {verdict.requirement} as adjacent experience, not expertise; "
            "cite the backing evidence."
        )
    elif verdict.status is EvidenceStatus.LEARNING:
        text = (
            f"Mention {verdict.requirement} only as in-progress learning with "
            "evidence; do not present as a qualification."
        )
    else:
        text = (
            f"No evidence for {verdict.requirement}: document it first or do "
            "not claim it anywhere in the application."
        )
    return MatchSuggestion(requirement=verdict.requirement, suggestion=text, evidence_refs=refs)


def build_match_report(vacancy: JobVacancy, profile: CandidateProfile) -> MatchReport:
    """Build the deterministic match/tailor report for one vacancy."""
    analysis = analyze_vacancy_fit(vacancy, profile)
    variant_id, basis = pick_cv_variant(vacancy, profile)
    warnings: list[str] = list(analysis.uncertainty_flags)
    if analysis.has_critical_gaps:
        warnings.append("critical_gaps: over half of required skills missing")
    if (vacancy.experience_requirement or "").strip():
        warnings.append("check seniority fit manually against the offer")
    return MatchReport(
        vacancy_id=vacancy.id,
        match_score=analysis.match_score,
        verdicts=analysis.verdicts,
        suggested_cv_variant=variant_id,
        variant_basis=basis,
        suggestions=tuple(_suggestion_for(verdict) for verdict in analysis.verdicts),
        warnings=tuple(warnings),
    )
