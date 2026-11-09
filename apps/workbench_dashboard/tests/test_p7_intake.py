"""P7 intake: brief validation, listing, approve-into-plan, endpoints."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from urllib.error import HTTPError

import pytest
from dashboard_stores import DashboardStores
from dashboard_test_http import get_json, post_json
from p7_intake import approve_intake, list_intake, validate_p7


def _brief(**overrides):
    now = datetime.now(UTC)
    payload = {
        "format_version": "1.0.0",
        "project_id": "acme-landing-20261101-a3f9",
        "created_at": (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "capture_method": "chatbot",
        "parent_id": None,
        "goal_summary": "Marketing site for B2B consultancy to capture leads and book calls",
        "problem_statement": "Current site is slow with no clear CTA",
        "target_users": ["SMB founders", "Ops managers"],
        "success_criteria": ["Contact form delivers and shows confirmation"],
        "deliverable_type": "website",
        "features_in": ["5-page responsive site", "Contact form with spam protection"],
        "features_out": ["No user logins"],
        "integrations": [{"name": "Calendly", "purpose": "booking widget"}],
        "timeline": {
            "deadline": (now + timedelta(days=30)).strftime("%Y-%m-%d"),
            "urgency": "dated",
        },
        "tech_constraints": [],
        "non_functional": [],
        "budget_range": "5-15k",
        "billing_model": "fixed",
        "client_contact": {
            "name": "Jane Doe",
            "email": "jane@acme.co",
            "company": "Acme",
            "phone": "",
        },
        "preferred_language": "en",
    }
    payload.update(overrides)
    return payload


def test_valid_brief_passes() -> None:
    verdict = validate_p7(_brief())
    assert verdict == {"valid": True, "errors": [], "warnings": []}


def test_structural_rejections() -> None:
    assert validate_p7([])["valid"] is False
    assert validate_p7(_brief(), raw_bytes=40 * 1024)["valid"] is False
    missing = _brief()
    del missing["goal_summary"]
    assert any("Missing" in err for err in validate_p7(missing)["errors"])
    assert any("Unknown" in err for err in validate_p7(_brief(surprise=1))["errors"])
    assert validate_p7(_brief(format_version="2.0.0"))["valid"] is False
    assert validate_p7(_brief(project_id="BAD!"))["valid"] is False
    assert validate_p7(_brief(created_at="yesterday"))["valid"] is False
    assert validate_p7(_brief(capture_method="pigeon"))["valid"] is False
    assert validate_p7(_brief(deliverable_type="rocket"))["valid"] is False
    assert validate_p7(_brief(budget_range="1M"))["valid"] is False
    assert validate_p7(_brief(preferred_language="xx"))["valid"] is False


def test_actionability_rejections() -> None:
    assert validate_p7(_brief(features_in=[]))["valid"] is False
    assert validate_p7(_brief(features_out=["5-page responsive site"]))["valid"] is False
    assert validate_p7(_brief(goal_summary="I want a website"))["valid"] is False
    assert validate_p7(_brief(success_criteria=["x" * 9]))["valid"] is False
    bad_contact = _brief()
    bad_contact["client_contact"] = {"name": "J", "email": "nope", "company": "", "phone": "123"}
    assert validate_p7(bad_contact)["valid"] is False
    soon = _brief()
    soon["timeline"] = {"deadline": datetime.now(UTC).strftime("%Y-%m-%d"), "urgency": "dated"}
    assert validate_p7(soon)["valid"] is False
    leaky = _brief(goal_summary="Marketing site, api_key: sk-1234567890abcdef for the demo")
    assert any("secret" in err for err in validate_p7(leaky)["errors"])
    old = _brief(created_at="2020-01-01T00:00:00Z")
    assert any("expired" in err for err in validate_p7(old)["errors"])


def test_q4_q7_language_and_marketing_goals() -> None:
    """Q4: PL+EN v1 (hu/de rejected, pl default). Q7: marketing_goals field."""
    assert validate_p7(_brief(preferred_language="pl"))["valid"] is True
    assert validate_p7(_brief(preferred_language="hu"))["valid"] is False
    assert validate_p7(_brief(preferred_language="de"))["valid"] is False
    no_lang = _brief()
    del no_lang["preferred_language"]
    assert validate_p7(no_lang)["valid"] is True
    goals = _brief(marketing_goals=["Rank for automation Gdansk", "10 demo calls/mo"])
    assert validate_p7(goals)["valid"] is True
    assert validate_p7(_brief(marketing_goals=["ok"] * 6))["valid"] is False
    assert validate_p7(_brief(marketing_goals="rank"))["valid"] is False


def test_warnings_not_rejections() -> None:
    vague = _brief(success_criteria=["Everything feels nice and smooth"])
    verdict = validate_p7(vague)
    assert verdict["valid"] is True
    assert any("untestable" in warn for warn in verdict["warnings"])
    pii = _brief(problem_statement="Call me at jane@acme.co about it")
    verdict = validate_p7(pii)
    assert verdict["valid"] is True
    assert any("email/phone" in warn for warn in verdict["warnings"])


def test_list_and_approve_round_trip(tmp_path) -> None:
    intake = tmp_path / "p7-projects"
    intake.mkdir()
    (intake / "good-20261105-x1.json").write_text(json.dumps(_brief()), encoding="utf-8")
    (intake / "bad.json").write_text(json.dumps({"format_version": "9"}), encoding="utf-8")
    (intake / "broken.json").write_text("{nope", encoding="utf-8")
    entries = {entry["name"]: entry for entry in list_intake(tmp_path)}
    assert entries["good-20261105-x1.json"]["valid"] is True
    assert entries["bad.json"]["valid"] is False
    assert entries["broken.json"]["valid"] is False
    plan = approve_intake(tmp_path, tmp_path / "data", "good-20261105-x1.json")
    assert plan["status"] == "proposed"
    assert plan["id"] == "acme-landing-20261101-a3f9"
    assert "Calendly" in plan["body"]
    stored = DashboardStores(tmp_path / "data").plans.get(plan["id"])
    assert stored is not None and stored["status"] == "proposed"
    assert not (intake / "good-20261105-x1.json").exists()
    assert (intake / "approved" / "good-20261105-x1.json").exists()
    with pytest.raises(ValueError, match="not valid"):
        approve_intake(tmp_path, tmp_path / "data", "bad.json")
    with pytest.raises(ValueError, match="Unknown"):
        approve_intake(tmp_path, tmp_path / "data", "missing.json")
    with pytest.raises(ValueError, match="Unknown"):
        approve_intake(tmp_path, tmp_path / "data", "../dashboard.json")


def test_intake_endpoints(dashboard_server, tmp_path) -> None:
    assert get_json(dashboard_server, "/api/intake") == {"ok": True, "files": []}
    intake = tmp_path / "p7-projects"
    intake.mkdir(exist_ok=True)
    (intake / "good.json").write_text(json.dumps(_brief()), encoding="utf-8")
    listed = get_json(dashboard_server, "/api/intake")
    assert [entry["name"] for entry in listed["files"]] == ["good.json"]
    assert listed["files"][0]["valid"] is True
    approved = post_json(dashboard_server, "/api/intake/good.json/approve", {})
    assert approved["ok"] is True
    assert approved["plan"]["status"] == "proposed"
    assert get_json(dashboard_server, "/api/intake")["files"] == []
    with pytest.raises(HTTPError) as exc:
        post_json(dashboard_server, "/api/intake/good.json/approve", {})
    assert exc.value.code == 400
