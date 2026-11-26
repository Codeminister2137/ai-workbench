"""Intake core: validation mirrors form.js, forward-then-log, rate gate."""

from __future__ import annotations

import pytest
from intake_server import (
    LeadError,
    check_rate_limit,
    submit_lead,
    validate_lead,
)


def _lead(**overrides):
    payload = {
        "title": "CRM followup",
        "name": "Jan Testowy",
        "email": "jan@example.pl",
        "company": "Test",
        "phone": "+48600111222",
        "goal": "Follow up quotes in 24h.",
        "problem": "",
        "budget": "10–30k",
        "language": "pl",
    }
    payload.update(overrides)
    return payload


def test_valid_pl_and_en_leads_pass() -> None:
    assert validate_lead(_lead())["budget"] == "10–30k"
    assert validate_lead(_lead(budget="2-5k", language="en"))["language"] == "en"


@pytest.mark.parametrize(
    "override,field",
    [
        ({"title": ""}, "title"),
        ({"name": "  "}, "name"),
        ({"email": "not-an-email"}, "email"),
        ({"goal": ""}, "goal"),
        ({"budget": "1M"}, "budget"),
        ({"phone": "123"}, "phone"),
        ({"language": "de"}, "language"),
    ],
)
def test_invalid_fields_name_themselves(override, field) -> None:
    with pytest.raises(LeadError, match=field):
        validate_lead(_lead(**override))


def test_honeypot_fails_generic() -> None:
    with pytest.raises(LeadError, match="^request rejected$"):
        validate_lead(_lead(website="http://spam.example"))


def test_non_object_rejected() -> None:
    with pytest.raises(LeadError):
        validate_lead(["nope"])


def test_rate_gate_five_per_hour() -> None:
    counters: dict = {}
    assert all(check_rate_limit(counters, "ip", 1000.0 + i) for i in range(5))
    assert check_rate_limit(counters, "ip", 1005.0) is False
    assert check_rate_limit(counters, "ip", 1000.0 + 3601.0) is True


def test_submit_forwards_then_logs_with_reference() -> None:
    calls: list = []
    receipt = submit_lead(
        _lead(),
        forward=lambda record, subject, body: calls.append(("fwd", record["lead_id"])),
        log=lambda record: calls.append(("log", record["lead_id"])),
    )
    assert receipt["lead_id"].startswith("BL-")
    assert calls[0][0] == "fwd" and calls[1][0] == "log"
    assert "email" not in receipt  # no PII echo


def test_submit_transport_failure_raises_before_log() -> None:
    def boom(record, subject, body):
        raise RuntimeError("smtp down")

    logged: list = []
    with pytest.raises(RuntimeError):
        submit_lead(_lead(), forward=boom, log=logged.append)
    assert logged == []
