"""ID lookup: exact, prefix, ambiguous, and missing tokens."""

from __future__ import annotations

import pytest
from dashboard_stores import DashboardStores
from dashboard_test_http import get_json


@pytest.fixture
def stores(tmp_path):
    return DashboardStores(tmp_path / "data")


def test_resolve_exact_id_wins(stores) -> None:
    record = stores.create_inbox_task(
        title="Q?", body="b", task_type="decision", options=["A"], assignee="owner"
    )
    matches = stores.resolve_id(record["id"])
    assert [(m["kind"], m["id"]) for m in matches] == [("inbox", record["id"])]
    assert matches[0]["url"] == f"#/inbox/{record['id']}"
    assert matches[0]["title"] == "Q?"


def test_resolve_unique_prefix_and_case(stores) -> None:
    record = stores.create_inbox_task(
        title="Q?", body="b", task_type="decision", options=["A"], assignee="owner"
    )
    prefix = record["id"][:12]
    assert [m["id"] for m in stores.resolve_id(prefix)] == [record["id"]]
    assert [m["id"] for m in stores.resolve_id(prefix.upper())] == [record["id"]]
    assert stores.resolve_id(prefix[:7]) == []
    assert stores.resolve_id("not hex!") == []


def test_resolve_lists_ambiguous_prefixes(stores) -> None:
    first = stores.create_inbox_task(title="a", body="b", task_type="task")
    stores.inbox.put("abc0000111", {**first, "id": "abc0000111"})
    stores.inbox.put("abc0000122", {**first, "id": "abc0000122"})
    matches = stores.resolve_id("abc00001")
    assert sorted(m["id"] for m in matches) == ["abc0000111", "abc0000122"]


def test_resolve_searches_runs_ideas_and_plans(stores) -> None:
    stores.runs.put("run-1", {"id": "run-1", "title": "r", "status": "queued"})
    idea = stores.create_idea(title="i", body="b", source="owner")
    assert stores.resolve_id("run-1") == []
    stores.runs.put("abcdef1234567890", {"id": "abcdef1234567890", "title": "r"})
    (match,) = stores.resolve_id("abcdef1234567890")
    assert (match["kind"], match["url"]) == ("run", "#/runs/abcdef1234567890")
    (imatch,) = stores.resolve_id(idea["id"])
    assert (imatch["kind"], imatch["url"]) == ("idea", f"#/ideas/{idea['id']}")


def test_resolve_endpoint_roundtrip(dashboard_server) -> None:
    payload = get_json(dashboard_server, "/api/resolve/deadbeef")
    assert payload["ok"] is True
    assert payload["matches"] == []
