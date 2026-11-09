"""Synthetic eval tasks for S3 suggestion quality (Q3).

Deterministic builder: N (profile, vacancy) pairs covering the verdict
matrix (demonstrated / partial / missing skills). Mechanical graders
score canned or model-produced suggestion text without inference.
"""

from __future__ import annotations

from dataclasses import dataclass

from evidence import analyze_vacancy_fit
from models import CandidateProfile, EvidenceStatus, JobVacancy, SkillEvidence
from suggest import build_suggestion_prompt, parse_suggestions

SKILLS = (
    "Python",
    "asyncio",
    "PostgreSQL",
    "Docker",
    "React",
    "AWS",
    "pytest",
    "Rust",
)

VACANCY_TITLES = (
    ("Backend Developer", ("Python", "asyncio", "PostgreSQL")),
    ("DevOps Engineer", ("Docker", "AWS", "Python")),
    ("Frontend Developer", ("React", "Python", "pytest")),
    ("Backend Developer", ("Rust", "PostgreSQL", "Docker")),
    ("QA Automation", ("pytest", "Python", "Docker")),
    ("Fullstack Developer", ("React", "Python", "AWS")),
)


@dataclass(frozen=True, slots=True)
class EvalTask:
    """One synthetic suggestion task with known verdicts."""

    task_id: str
    profile: CandidateProfile
    vacancy: JobVacancy
    missing_skills: tuple[str, ...]
    strong_skills: tuple[str, ...]


def _profile(tag: str, demonstrated: tuple[str, ...], partial: tuple[str, ...]) -> CandidateProfile:
    skills = {}
    for skill in demonstrated:
        skills[skill] = SkillEvidence(
            skill,
            EvidenceStatus.DEMONSTRATED,
            notes=f"Three years of {skill}.",
            source_kinds=("cv",),
        )
    for skill in partial:
        skills[skill] = SkillEvidence(
            skill,
            EvidenceStatus.ADJACENT,
            notes=f"Some {skill} exposure.",
            source_kinds=("github",),
        )
    return CandidateProfile(
        applicant_name=f"Synthetic {tag}",
        applicant_location="Nowhere",
        applicant_summary="Synthetic.",
        portfolio_url="https://example.invalid",
        linkedin_url="https://example.invalid",
        skills=skills,
    )


def build_eval_tasks() -> list[EvalTask]:
    """Build 24 deterministic tasks (4 profiles x 6 vacancies)."""
    profiles = {
        "be": _profile("BE", ("Python", "asyncio", "PostgreSQL"), ("Docker",)),
        "ops": _profile("OPS", ("Docker", "AWS", "Python"), ("pytest",)),
        "fe": _profile("FE", ("React", "pytest"), ("Python",)),
        "junior": _profile("JR", ("Python",), ("pytest", "Docker")),
    }
    tasks = []
    for ptag, profile in profiles.items():
        for i, (title, required) in enumerate(VACANCY_TITLES):
            vacancy = JobVacancy(
                id=f"vac-{ptag}-{i}",
                company="Example Corp",
                title=title,
                location="Remote",
                description=f"{title} needing {', '.join(required)}.",
                required_skills=required,
            )
            verdicts = analyze_vacancy_fit(vacancy, profile).verdicts
            by_skill = {v.requirement: v.status for v in verdicts}
            tasks.append(
                EvalTask(
                    task_id=f"{ptag}-{i}",
                    profile=profile,
                    vacancy=vacancy,
                    missing_skills=tuple(
                        s for s in required if by_skill.get(s) == EvidenceStatus.ABSENT
                    ),
                    strong_skills=tuple(
                        s for s in required if by_skill.get(s) == EvidenceStatus.DEMONSTRATED
                    ),
                )
            )
    return tasks


@dataclass(frozen=True, slots=True)
class SuggestionGrade:
    """Mechanical grade for one suggestion output."""

    parses: bool
    no_missing_in_suggestions: bool
    missing_listed_prohibited: bool

    @property
    def passed(self) -> bool:
        return self.parses and self.no_missing_in_suggestions and self.missing_listed_prohibited


def grade_suggestions(task: EvalTask, raw_output: str) -> SuggestionGrade:
    """Grade raw suggestion text against known missing skills.

    Contract: numbered suggestion lines, then a PROHIBITED section.
    Missing skills must appear only in the prohibited part.
    """
    parts = parse_suggestions(raw_output)
    marker = next(
        (i for i, line in enumerate(parts) if line.upper().startswith("PROHIBITED")),
        None,
    )
    if marker is None or marker == 0:
        return SuggestionGrade(False, False, False)
    head_text = "\n".join(parts[:marker]).lower()
    tail_text = "\n".join(parts[marker:]).lower()
    leak = any(skill.lower() in head_text for skill in task.missing_skills)
    listed = all(skill.lower() in tail_text for skill in task.missing_skills)
    return SuggestionGrade(True, not leak, listed)


def task_prompt(task: EvalTask) -> str:
    """Build the exact model prompt for one task."""
    verdicts = analyze_vacancy_fit(task.vacancy, task.profile).verdicts
    return build_suggestion_prompt(task.vacancy, verdicts, task.profile)
