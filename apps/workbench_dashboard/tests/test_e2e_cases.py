"""Case-specific E2E steps grounded in diff evidence."""

from __future__ import annotations

import e2e_cases
import pytest
from dashboard_stores import DashboardStores, StoreError
from e2e_promotion import build_report, generate_checklist

DIFF = """diff --git a/apps/workbench_dashboard/dashboard_web_app.py b/apps/workbench_dashboard/dashboard_web_app.py
index 111..222 100644
--- a/apps/workbench_dashboard/dashboard_web_app.py
+++ b/apps/workbench_dashboard/dashboard_web_app.py
@@ -10,6 +10,8 @@ class DashboardRequestHandler:
+    def _send_e2e_tasks(self, query):
+        return self._send_json({"ok": True})
diff --git a/apps/workbench_dashboard/web/app.js b/apps/workbench_dashboard/web/app.js
index 333..444 100644
--- a/apps/workbench_dashboard/web/app.js
+++ b/apps/workbench_dashboard/web/app.js
@@ -20,6 +20,8 @@ async function renderE2E(id) {
+      const payload = await api("/api/e2e/tasks/" + id + "/finalize");
+      view.innerHTML = `<a href="#/e2e">back</a>`;
"""


def _runner(diff_text: str):
    def run(repo_root: str, *args: str) -> bytes:
        assert args[0] == "diff"
        return diff_text.encode("utf-8")

    return run


def test_evidence_extracts_symbols_routes_and_views() -> None:
    evidence = e2e_cases.extract_diff_evidence(
        "repo", "base", "head", ["a.py"], runner=_runner(DIFF)
    )
    web_app = evidence["apps/workbench_dashboard/dashboard_web_app.py"]
    assert web_app["symbols"] == ["_send_e2e_tasks"]
    js = evidence["apps/workbench_dashboard/web/app.js"]
    assert js["routes"] == ["/api/e2e/tasks"]
    assert js["views"] == ["#/e2e"]


def test_dashboard_steps_cite_views_and_routes() -> None:
    evidence = e2e_cases.extract_diff_evidence(
        "repo", "base", "head", ["a.py"], runner=_runner(DIFF)
    )
    steps = e2e_cases.draft_steps("dashboard", evidence, ["some change"])
    assert steps
    assert all(step["grounded"] for step in steps)
    actions = " ".join(step["action"] for step in steps)
    assert "#/e2e" in actions
    assert "/api/e2e/tasks" in actions
    assert all(step["action"].strip() and step["expected"].strip() for step in steps)


def test_handler_symbols_do_not_fake_views() -> None:
    evidence = {
        "apps/workbench_dashboard/dashboard_web_app.py": {
            "symbols": ["_send_e2e_by_view"],
            "routes": [],
            "views": [],
        }
    }
    steps = e2e_cases.draft_steps("dashboard", evidence, ["s"])
    assert e2e_cases.needs_pointers(steps)
    assert "_send_e2e_by_view" in steps[0]["action"]


def test_template_braces_are_not_routes() -> None:
    diff = (
        "+++ b/x.js\n"
        '+  const u = api("/api/e2e/tasks/" + id + "/finalize");\n'
        "+  const t = `{created} ok`;\n"
    )
    evidence = e2e_cases.extract_diff_evidence("r", "b", "h", ["x.js"], runner=_runner(diff))
    assert evidence["x.js"]["routes"] == ["/api/e2e/tasks"]


def test_fixture_routes_in_tests_ground_nothing() -> None:
    diff = (
        "+++ b/apps/workbench_dashboard/tests/test_x.py\n"
        '+  api("/api/e2e/tasks/" + i)\n'
        '+  link("#/e2e")\n'
        "+  def helper_thing():\n"
    )
    evidence = e2e_cases.extract_diff_evidence("r", "b", "h", ["t"], runner=_runner(diff))
    assert evidence == {}


def test_nested_view_prefixes_ground_no_steps() -> None:
    evidence = {"x.js": {"symbols": [], "routes": [], "views": ["#/e2e", "#/e2e/report/"]}}
    steps = e2e_cases.draft_steps("dashboard", evidence, ["s"])
    assert [s["action"] for s in steps] == ["Open the e2e view (#/e2e)"]


def test_agent_cli_steps_do_not_claim_help_flags() -> None:
    evidence = {
        "packages/ai_agent/src/ai_agent/repo_coding_assistant.py": {
            "symbols": ["_external_execution_completed"],
            "routes": [],
            "views": [],
        }
    }
    (step,) = e2e_cases.draft_steps("agent-cli", evidence, ["s"])
    assert "--help" not in step["action"]
    assert "_external_execution_completed" in step["action"]


def test_reauthor_replaces_checklist_on_verdict_less_task(tmp_path) -> None:
    stores = DashboardStores(tmp_path)
    task = stores.create_e2e_task(
        merge_commit="abc123",
        title="t",
        items=[
            {
                "id": "behavior:dashboard",
                "kind": "behavior",
                "area": "dashboard",
                "status": "pending",
            }
        ],
    )
    items = [
        {
            "id": "behavior:dashboard",
            "kind": "behavior",
            "area": "dashboard",
            "behavior": "dashboard views and actions",
            "files": [],
            "status": "pending",
            "steps": [{"action": "Open x", "expected": "Renders", "grounded": True}],
            "needs_pointers": False,
        }
    ]
    redone = stores.reauthor_e2e_items(task["id"], items, reauthored_by="agent")
    assert redone["id"] == task["id"]
    assert redone["items"] == items
    assert redone["reauthored_by"] == "agent"
    assert redone["reauthored_at"]
    stores.submit_e2e_task(
        task["id"],
        [{"item_id": "behavior:dashboard", "verdict": "pass", "steps": [True]}],
    )
    with pytest.raises(StoreError, match="Only open"):
        stores.reauthor_e2e_items(task["id"], items)


def test_empty_evidence_needs_pointers() -> None:
    steps = e2e_cases.draft_steps("dashboard", {}, ["mystery change"])
    assert steps
    assert e2e_cases.needs_pointers(steps)


def test_regression_steps_come_from_standing_guidance() -> None:
    steps = e2e_cases.regression_steps("dashboard")
    assert steps
    assert not e2e_cases.needs_pointers(steps)


def test_checklist_attaches_steps_and_pointer_flags() -> None:
    evidence = e2e_cases.extract_diff_evidence(
        "repo", "base", "head", ["a.py"], runner=_runner(DIFF)
    )
    checklist = generate_checklist(
        "abc123",
        list(evidence),
        summaries={"subjects": ["s"], "evidence": evidence},
    )
    (item,) = [i for i in checklist["items"] if i["kind"] == "behavior"]
    assert item["steps"]
    assert item["needs_pointers"] is False
    vague = generate_checklist("def456", ["apps/ai_council/x.py"], summaries={})
    (behavior,) = [i for i in vague["items"] if i["kind"] == "behavior"]
    assert behavior["needs_pointers"] is True


def test_checklist_regression_items_need_no_pointers() -> None:
    checklist = generate_checklist("abc123", ["packages/ai_provider/x.py"], summaries={})
    regressions = [i for i in checklist["items"] if i["kind"] == "regression"]
    assert regressions
    assert all(r["steps"] for r in regressions)
    assert all(r["needs_pointers"] is False for r in regressions)


def test_report_requires_every_step_performed() -> None:
    task = {
        "merge_commit": "abc123",
        "items": [
            {
                "id": "behavior:dashboard",
                "status": "pending",
                "steps": [
                    {"action": "Open x", "expected": "Renders"},
                    {"action": "Click y", "expected": "Confirms"},
                ],
            }
        ],
    }
    with pytest.raises(ValueError, match="every step performed"):
        build_report(task, {"behavior:dashboard": {"verdict": "pass", "steps": [True, False]}})
    report = build_report(task, {"behavior:dashboard": {"verdict": "pass", "steps": [True, True]}})
    assert report["overall"] == "pass"
    assert report["items"][0]["step_results"] == [
        {"action": "Open x", "expected": "Renders", "performed": True},
        {"action": "Click y", "expected": "Confirms", "performed": True},
    ]


def _draft(stores: DashboardStores) -> dict:
    checklist = generate_checklist("abc123", ["apps/ai_council/x.py"], summaries={})
    return stores.create_e2e_task(
        merge_commit="abc123", title="t", items=checklist["items"], draft=True
    )


def test_draft_finalizes_with_authored_steps(tmp_path) -> None:
    stores = DashboardStores(tmp_path)
    record = _draft(stores)
    assert record["status"] == "draft"
    assert stores.open_e2e_count() == 0
    with pytest.raises(StoreError, match="awaiting pointers"):
        stores.submit_e2e_task(record["id"], [])
    pending = [i for i in record["items"] if i.get("status") == "pending"]
    finalized = stores.finalize_e2e_task(
        record["id"],
        {i["id"]: [{"action": "Do x", "expected": "See y"}] for i in pending},
    )
    assert finalized["status"] == "open"
    assert all(not i.get("needs_pointers", False) for i in finalized["items"])
    assert stores.open_e2e_count() == 1


def test_draft_replaced_by_regeneration(tmp_path) -> None:
    stores = DashboardStores(tmp_path)
    first = _draft(stores)
    second = _draft(stores)
    assert second["id"] == first["id"]
    assert second["status"] == "draft"


def test_history_trail_names_tested_commits(tmp_path) -> None:
    stores = DashboardStores(tmp_path)
    task = stores.create_e2e_task(
        merge_commit="abc123",
        title="t",
        items=[
            {
                "id": "behavior:dashboard",
                "kind": "behavior",
                "area": "dashboard",
                "status": "pending",
            }
        ],
    )
    outcome = stores.submit_e2e_task(
        task["id"], [{"item_id": "behavior:dashboard", "verdict": "pass"}]
    )
    (entry,) = stores.history_for_area("dashboard")
    assert entry["verdict"] == "pass"
    assert entry["commit"] == "abc123"
    assert entry["report_id"] == outcome["report"]["id"]
    assert stores.history_for_area("council") == []


def test_validate_steps_rejects_blanks() -> None:
    assert e2e_cases.validate_steps([{"action": " Click x ", "expected": " Y "}]) == [
        {"action": "Click x", "expected": "Y", "grounded": True}
    ]
    for bad in ([], [{"action": "", "expected": "y"}], [{"action": "x"}], "nope"):
        try:
            e2e_cases.validate_steps(bad)  # type: ignore[arg-type]
        except ValueError:
            continue
        raise AssertionError(f"accepted bad steps: {bad!r}")
