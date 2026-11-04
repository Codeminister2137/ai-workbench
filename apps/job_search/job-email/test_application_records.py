"""Round-trip and validation tests for the local application-record ledger.

Covers append-only JSONL persistence of prepared, approved, sent, and failed
packages, plus strict reader rejection of malformed lines. All fixtures are
obviously synthetic and confined to temporary directories.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest
from approval import approve_package
from models import (
    ApplicationStatus,
    CandidateProfile,
    CVVariant,
    EvidenceStatus,
    JobVacancy,
    MessageVariant,
    SendReceipt,
    SkillEvidence,
    utc_now_iso,
)
from preparation import prepare_application
from records import (
    append_application_record,
    application_record_from_dict,
    application_record_to_dict,
    read_application_records,
)
from sender import DryRunEmailTransport, deliver_application


@pytest.fixture
def synthetic_profile(tmp_path) -> CandidateProfile:
    attachment = tmp_path / "cv_synthetic.pdf"
    attachment.write_bytes(b"synthetic reviewed CV bytes")
    return CandidateProfile(
        applicant_name="Alex Example",
        applicant_location="Nowhereville",
        applicant_summary="Fictional applicant used only for offline tests.",
        portfolio_url="https://example.invalid/portfolio/alex",
        linkedin_url="https://example.invalid/in/alex-example",
        skills={"Python": SkillEvidence("Python", EvidenceStatus.DEMONSTRATED)},
        cv_variants={"default": CVVariant("default", str(attachment), "Fictional Role")},
        message_variants={
            "concise": MessageVariant(
                "concise",
                subject_template="{role} application from {applicant_name}",
                body_template="Hello {company} team, I am {applicant_name}.",
            ),
        },
    )


@pytest.fixture
def synthetic_vacancy() -> JobVacancy:
    return JobVacancy(
        id="vac-synthetic-9",
        company="Example Corp",
        title="Python Developer",
        location="Remote",
        required_skills=("Python",),
        contact_email="hiring@example.invalid",
    )


def test_prepared_package_round_trip(
    synthetic_profile: CandidateProfile, synthetic_vacancy: JobVacancy, tmp_path
) -> None:
    package = prepare_application(
        synthetic_profile, synthetic_vacancy, message_variant_id="concise"
    )
    ledger = tmp_path / "records.jsonl"
    append_application_record(ledger, package)
    (read_back,) = read_application_records(ledger)
    assert read_back == package
    assert read_back.send_receipt is None
    assert read_back.message_variant_id == "concise"


def test_sent_package_preserves_approval_and_receipt(
    synthetic_profile: CandidateProfile, synthetic_vacancy: JobVacancy, tmp_path
) -> None:
    package = prepare_application(
        synthetic_profile, synthetic_vacancy, message_variant_id="concise"
    )
    approved = approve_package(package, approved_by="reviewer", notes="Synthetic review")
    sent = deliver_application(approved, DryRunEmailTransport())
    assert sent.status is ApplicationStatus.SENT
    assert sent.send_receipt is not None

    ledger = tmp_path / "records.jsonl"
    append_application_record(ledger, sent)
    (read_back,) = read_application_records(ledger)
    assert read_back == sent
    assert read_back.status is ApplicationStatus.SENT
    receipt = read_back.send_receipt
    assert receipt is not None
    assert receipt.success is True
    assert receipt.recipient == "hiring@example.invalid"
    assert receipt.transport_name == "dry_run"
    assert receipt.timestamp_utc == sent.send_receipt.timestamp_utc
    assert read_back.approved_by == "reviewer"
    assert read_back.approval_notes == "Synthetic review"
    assert read_back.approved_materials_sha256 == sent.approved_materials_sha256


def test_failed_package_preserves_error_receipt(
    synthetic_profile: CandidateProfile, synthetic_vacancy: JobVacancy, tmp_path
) -> None:
    package = prepare_application(synthetic_profile, synthetic_vacancy)
    failed = replace(
        package,
        status=ApplicationStatus.FAILED,
        send_receipt=SendReceipt(
            success=False,
            recipient="hiring@example.invalid",
            timestamp_utc=utc_now_iso(),
            error_message="Synthetic transport failure",
            transport_name="dry_run",
        ),
    )
    ledger = tmp_path / "records.jsonl"
    append_application_record(ledger, failed)
    (read_back,) = read_application_records(ledger)
    assert read_back == failed
    assert read_back.status is ApplicationStatus.FAILED
    assert read_back.send_receipt is not None
    assert read_back.send_receipt.success is False
    assert read_back.send_receipt.error_message == "Synthetic transport failure"


def test_append_preserves_existing_lines_and_order(
    synthetic_profile: CandidateProfile, synthetic_vacancy: JobVacancy, tmp_path
) -> None:
    first = prepare_application(synthetic_profile, synthetic_vacancy)
    second = prepare_application(
        synthetic_profile, replace(synthetic_vacancy, id="vac-synthetic-10")
    )
    ledger = tmp_path / "records.jsonl"
    append_application_record(ledger, first)
    raw_before = ledger.read_text(encoding="utf-8")
    append_application_record(ledger, second)
    raw_after = ledger.read_text(encoding="utf-8")
    assert raw_after.startswith(raw_before)
    assert raw_after.count("\n") == 2
    assert [json.loads(line) for line in raw_after.splitlines()]
    assert read_application_records(ledger) == [first, second]


def test_append_creates_missing_parent_directories(
    synthetic_profile: CandidateProfile, synthetic_vacancy: JobVacancy, tmp_path
) -> None:
    package = prepare_application(synthetic_profile, synthetic_vacancy)
    ledger = tmp_path / "nested" / "runtime" / "records.jsonl"
    append_application_record(ledger, package)
    assert read_application_records(ledger) == [package]


def test_unicode_fields_survive_round_trip(synthetic_vacancy: JobVacancy, tmp_path) -> None:
    package = prepare_application(
        CandidateProfile(
            applicant_name="Zoë Exämple-Łódź",
            applicant_location="Nowhereville",
            applicant_summary="Fictional résumé summary with diacritics: zażółć.",
            portfolio_url="https://example.invalid/portfolio/zoe",
            linkedin_url="https://example.invalid/in/zoe",
        ),
        synthetic_vacancy,
    )
    ledger = tmp_path / "records.jsonl"
    append_application_record(ledger, package)
    (read_back,) = read_application_records(ledger)
    assert read_back == package
    assert "Łódź" in read_back.body or "Exämple" in read_back.body


@pytest.mark.parametrize("content", [None, "", "\n  \n"])
def test_missing_empty_or_blank_ledger_reads_as_no_records(tmp_path, content) -> None:
    ledger = tmp_path / "records.jsonl"
    if content is not None:
        ledger.write_text(content, encoding="utf-8")
    assert read_application_records(ledger) == []


def test_blank_lines_are_skipped(
    synthetic_profile: CandidateProfile, synthetic_vacancy: JobVacancy, tmp_path
) -> None:
    package = prepare_application(synthetic_profile, synthetic_vacancy)
    ledger = tmp_path / "records.jsonl"
    ledger.write_text("\n", encoding="utf-8")
    append_application_record(ledger, package)
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write("   \n")
    assert read_application_records(ledger) == [package]


def test_malformed_json_reports_line_number(
    synthetic_profile: CandidateProfile, synthetic_vacancy: JobVacancy, tmp_path
) -> None:
    package = prepare_application(synthetic_profile, synthetic_vacancy)
    ledger = tmp_path / "records.jsonl"
    append_application_record(ledger, package)
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write("{not valid json\n")
    append_application_record(ledger, package)
    with pytest.raises(ValueError, match=r"line 2.*invalid JSON"):
        read_application_records(ledger)


def test_non_object_line_is_rejected(tmp_path) -> None:
    ledger = tmp_path / "records.jsonl"
    ledger.write_text('["not", "a", "record"]\n', encoding="utf-8")
    with pytest.raises(ValueError, match=r"line 1.*must be a JSON object"):
        read_application_records(ledger)


@pytest.mark.parametrize(
    "mutate,match",
    [
        (lambda record: record.pop("vacancy_ref"), "field 'vacancy_ref' must be a string"),
        (
            lambda record: record.update({"contact_email": 42}),
            "field 'contact_email' must be a string",
        ),
        (lambda record: record.update({"status": "teleported"}), "unknown application status"),
        (
            lambda record: record.update({"send_receipt": {"success": "yes"}}),
            "field 'send_receipt.success' must be a boolean",
        ),
        (
            lambda record: record.update({"send_receipt": "sent"}),
            "field 'send_receipt' must be an object or null",
        ),
        (
            lambda record: record.update({"approved_by": 7}),
            "field 'approved_by' must be a string or null",
        ),
    ],
)
def test_malformed_record_is_rejected_with_line_number(
    synthetic_profile: CandidateProfile, synthetic_vacancy: JobVacancy, tmp_path, mutate, match
) -> None:
    package = prepare_application(synthetic_profile, synthetic_vacancy)
    record = application_record_to_dict(package)
    mutate(record)
    ledger = tmp_path / "records.jsonl"
    ledger.write_text(json.dumps(record) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match=rf"line 1.*{match}"):
        read_application_records(ledger)


def test_from_dict_rejects_non_dict() -> None:
    with pytest.raises(ValueError, match="must be a JSON object"):
        application_record_from_dict(["not-a-dict"])  # type: ignore[arg-type]


def test_extra_fields_are_ignored_for_forward_compatibility(
    synthetic_profile: CandidateProfile, synthetic_vacancy: JobVacancy
) -> None:
    package = prepare_application(synthetic_profile, synthetic_vacancy)
    record = application_record_to_dict(package)
    record["future_field"] = {"nested": [1, 2, 3]}
    assert application_record_from_dict(record) == package
