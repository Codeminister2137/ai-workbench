"""Openings intake preserves identity/evidence without fetching or applying."""

import json

import pytest
from deduplication import deduplicate_vacancies
from models import WorkMode
from openings_import import import_openings_export


def export_row(**changes):
    return {
        "job_id": "synthetic-1",
        "title": "Python Backend Developer",
        "company": "Synthetic Example",
        "location": "Synthetic City",
        "source": "jobspy",
        "status": "shortlisted",
        "job_url": "https://example.invalid/jobs/1",
        "description": "Python experience desirable. Hybrid arrangements possible.",
        "is_remote": None,
        "job_type": "fulltime",
        "job_level": "mid",
        "min_amount": 100,
        "max_amount": 200,
        "currency": "PLN",
        **changes,
    }


def test_export_keeps_raw_evidence_and_does_not_invent_missing_contract_details():
    row = export_row()
    (vacancy,) = import_openings_export([row])
    assert vacancy.id == vacancy.duplicate_key == "openings:synthetic-1"
    assert vacancy.title == row["title"]
    assert vacancy.source == "jobspy"
    assert vacancy.source_url == row["job_url"]
    assert vacancy.description == row["description"]
    assert json.loads(vacancy.raw_content) == row
    assert vacancy.compensation is None  # Export has no salary interval/gross/net.
    assert vacancy.employment_type.value == "unspecified"  # Fulltime is not permanent.
    assert vacancy.required_skills == vacancy.preferred_skills == ()
    assert vacancy.contact_email is None


@pytest.mark.parametrize(
    "remote, mode",
    [(True, WorkMode.REMOTE), (False, WorkMode.UNSPECIFIED), (None, WorkMode.UNSPECIFIED)],
)
def test_remote_flag_does_not_infer_onsite_or_country_eligibility(remote, mode):
    (vacancy,) = import_openings_export([export_row(is_remote=remote)])
    assert vacancy.work_mode is mode


def test_same_named_requisitions_stay_distinct_and_identical_replays_collapse():
    first = export_row()
    second = export_row(job_id="synthetic-2", job_url="https://example.invalid/jobs/2")
    vacancies = import_openings_export([first, dict(first), second])
    assert [vacancy.id for vacancy in deduplicate_vacancies(vacancies)] == [
        "openings:synthetic-1",
        "openings:synthetic-2",
    ]


def test_conflicting_same_id_records_require_snapshot_selection():
    with pytest.raises(ValueError, match="Conflicting Openings export"):
        import_openings_export([export_row(), export_row(description="Changed description")])


def test_invalid_record_shape_is_rejected_before_field_access():
    with pytest.raises(ValueError, match="row must be an object"):
        import_openings_export(json.loads("[null]"))


@pytest.mark.parametrize(
    "field, value",
    [
        ("job_id", ""),
        ("company", None),
        ("title", 42),
        ("location", []),
        ("description", False),
        ("is_remote", "false"),
        ("is_remote", 1),
    ],
)
def test_malformed_export_fields_are_not_silently_coerced(field, value):
    with pytest.raises(ValueError, match="Openings"):
        import_openings_export([export_row(**{field: value})])


def test_null_optional_fields_remain_unknown_and_empty_export_is_valid():
    (vacancy,) = import_openings_export(
        [export_row(location=None, description=None, job_url=None, job_level=None, source=None)]
    )
    assert vacancy.location == vacancy.description == ""
    assert vacancy.source_url is vacancy.experience_requirement is None
    assert vacancy.source == "openings"
    assert import_openings_export([]) == ()
