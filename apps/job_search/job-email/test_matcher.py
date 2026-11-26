from __future__ import annotations

import json

from matcher import build_match_report, pick_cv_variant
from models import (
    CandidateProfile,
    CVVariant,
    EmploymentType,
    EvidenceStatus,
    JobVacancy,
    SkillEvidence,
    WorkMode,
)


def _profile() -> CandidateProfile:
    return CandidateProfile(
        applicant_name="Jan Kowalski",
        applicant_location="Skoczow",
        applicant_summary="Python backend developer.",
        portfolio_url="",
        linkedin_url="",
        skills={
            "Python": SkillEvidence(
                skill_name="Python", status=EvidenceStatus.DEMONSTRATED, source_kinds=("cv",)
            ),
            "Docker": SkillEvidence(
                skill_name="Docker", status=EvidenceStatus.ADJACENT, source_kinds=("cv",)
            ),
            "Kubernetes": SkillEvidence(
                skill_name="Kubernetes", status=EvidenceStatus.LEARNING, source_kinds=("manual",)
            ),
        },
        cv_variants={
            "backend": CVVariant(
                variant_id="backend",
                file_path="cv-backend.pdf",
                target_role="Python Backend Developer",
            ),
            "data": CVVariant(
                variant_id="data",
                file_path="cv-data.pdf",
                target_role="Data Engineer",
            ),
        },
    )


def _vacancy(**overrides) -> JobVacancy:
    payload = {
        "id": "v1",
        "company": "Acme",
        "title": "Python Backend Developer",
        "location": "Remote",
        "work_mode": WorkMode.REMOTE,
        "employment_type": EmploymentType.B2B,
        "required_skills": ("Python", "Docker", "Kubernetes", "Go"),
        "preferred_skills": (),
    }
    payload.update(overrides)
    return JobVacancy(**payload)


def test_report_carries_score_and_verdicts() -> None:
    report = build_match_report(_vacancy(), _profile())
    assert report.vacancy_id == "v1"
    assert report.match_score == round((1.0 + 0.5 + 0.25 + 0.0) / 4, 3)
    assert [v.verdict for v in report.verdicts] == ["strong", "partial", "uncertain", "missing"]
    assert len(report.suggestions) == 4


def test_variant_pick_reports_basis() -> None:
    variant_id, basis = pick_cv_variant(_vacancy(), _profile())
    assert variant_id == "backend"
    assert "keyword hits" in basis


def test_variant_tie_means_no_suggestion() -> None:
    vacancy = _vacancy(title="Developer Engineer")
    variant_id, basis = pick_cv_variant(vacancy, _profile())
    assert variant_id is None
    assert "tie" in basis


def test_variant_without_overlap_means_no_suggestion() -> None:
    vacancy = _vacancy(title="Chef")
    variant_id, basis = pick_cv_variant(vacancy, _profile())
    assert variant_id is None
    assert "no title" in basis


def test_suggestions_never_invent() -> None:
    report = build_match_report(_vacancy(), _profile())
    by_requirement = {s.requirement: s.suggestion for s in report.suggestions}
    assert "do not claim it" in by_requirement["Go"]
    assert "adjacent" in by_requirement["Docker"].lower()
    assert "in-progress" in by_requirement["Kubernetes"]
    assert "Lead with Python" in by_requirement["Python"]


def test_warnings_flag_gaps_and_seniority() -> None:
    report = build_match_report(
        _vacancy(required_skills=("Go", "Rust", "Erlang"), experience_requirement="5 years"),
        _profile(),
    )
    assert "critical_gaps: over half of required skills missing" in report.warnings
    assert any("seniority" in warning for warning in report.warnings)


def test_warnings_surface_offer_pay_and_seniority_verbatim() -> None:
    """Q6/Q7: judge sees the offer's words; matcher filters on neither."""
    report = build_match_report(
        _vacancy(experience_requirement="5+ years", compensation="12000-16000 PLN net"),
        _profile(),
    )
    assert "seniority: offer states '5+ years' — judge fit manually" in report.warnings
    assert "pay: offer states '12000-16000 PLN net' — judge with the offer" in report.warnings


def test_warnings_skip_missing_pay_and_seniority() -> None:
    report = build_match_report(_vacancy(), _profile())
    assert not [w for w in report.warnings if w.startswith(("pay:", "seniority:"))]


def test_report_json_round_trip() -> None:
    report = build_match_report(_vacancy(), _profile())
    payload = json.loads(json.dumps(report.to_dict()))
    assert payload["vacancy_id"] == "v1"
    assert payload["suggested_cv_variant"] == "backend"
    assert payload["verdicts"][0]["verdict"] == "strong"


def test_preparation_prefers_suggested_variant() -> None:
    from preparation import prepare_application

    profile = _profile()
    vacancy = _vacancy(title="Data Engineer", contact_email="h@example.invalid")
    report = build_match_report(vacancy, profile)
    assert report.suggested_cv_variant == "data"
    package = prepare_application(profile, vacancy, match_report=report)
    assert package.cv_variant_id == "data"
    assert package.cv_attachment_path == "cv-data.pdf"
    explicit = prepare_application(profile, vacancy, cv_variant_id="backend", match_report=report)
    assert explicit.cv_variant_id == "backend"
