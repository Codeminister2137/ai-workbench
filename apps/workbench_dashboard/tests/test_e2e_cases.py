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
    assert "E2E tab (#/e2e)" in actions
    assert "/api/e2e/tasks" not in actions
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


def test_mapped_routes_name_the_tab() -> None:
    evidence = {
        "x.js": {
            "symbols": ["renderRuns"],
            "routes": ["/api/runs", "/api/e2e/tasks"],
            "views": [],
        }
    }
    steps = e2e_cases.draft_steps("dashboard", evidence, ["s"])
    assert [s["action"] for s in steps] == [
        "Open the Runs tab (#/runs) and exercise the changed control end to end"
        " (touched: renderRuns)",
        "Open the E2E tab (#/e2e) and exercise the changed control end to end"
        " (touched: renderRuns)",
    ]
    assert all(s["grounded"] for s in steps)
    assert e2e_cases.needs_pointers(steps) is False


def test_mapped_status_route_grounds_home_step() -> None:
    evidence = {
        "x.js": {"symbols": [], "routes": ["/api/status"], "views": []},
    }
    (step,) = e2e_cases.draft_steps("dashboard", evidence, ["s"])
    assert step["grounded"] is True
    assert "#/" in step["action"]
    assert e2e_cases.needs_pointers([step]) is False


def test_agent_cli_steps_do_not_claim_help_flags() -> None:
    evidence = {
        "packages/ai_agent/src/ai_agent/repo_coding_assistant.py": {
            "symbols": ["_external_execution_completed"],
            "routes": [],
            "views": [],
        }
    }
    (suite, step) = e2e_cases.draft_steps("agent-cli", evidence, ["s"])
    assert suite["agent_runnable"] is True
    assert "run-tests.py agent" in suite["action"]
    assert "--help" not in step["action"]
    assert "_external_execution_completed" in step["action"]
    assert "pytest" not in step["action"]  # suites are AI work, never human steps


def test_command_steps_give_exact_pytest_for_test_files() -> None:
    evidence = {
        "tests/repo_assistant/test_external_execution_completed.py": {
            "symbols": ["test_x"],
            "routes": [],
            "views": [],
        }
    }
    (step,) = e2e_cases.draft_steps("agent-cli", evidence, ["s"])
    assert step["action"].startswith(
        "Run `.venv/Scripts/python.exe -m pytest "
        "tests/repo_assistant/test_external_execution_completed.py -q`"
    )
    assert "never by executing the file directly" in step["action"]


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
        [{"item_id": "behavior:dashboard", "verdict": "pass", "steps": ["pass"]}],
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


def test_report_derives_item_verdict_from_step_verdicts() -> None:
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
    with pytest.raises(ValueError, match="every step decided"):
        build_report(task, {"behavior:dashboard": {"verdict": "pass", "steps": ["pass", ""]}})
    report = build_report(
        task, {"behavior:dashboard": {"verdict": "pass", "steps": ["pass", "pass"]}}
    )
    assert report["overall"] == "pass"
    assert report["items"][0]["verdict"] == "pass"
    assert report["items"][0]["step_results"] == [
        {"action": "Open x", "expected": "Renders", "verdict": "pass"},
        {"action": "Click y", "expected": "Confirms", "verdict": "pass"},
    ]
    mixed = build_report(
        task, {"behavior:dashboard": {"verdict": "pass", "steps": ["pass", "fail"]}}
    )
    assert mixed["items"][0]["verdict"] == "fail"
    assert mixed["overall"] == "fail"


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
        {"action": "Click x", "expected": "Y", "grounded": True, "agent_runnable": False}
    ]
    for bad in ([], [{"action": "", "expected": "y"}], [{"action": "x"}], "nope"):
        try:
            e2e_cases.validate_steps(bad)  # type: ignore[arg-type]
        except ValueError:
            continue
        raise AssertionError(f"accepted bad steps: {bad!r}")


def test_validate_steps_derives_agent_runnable() -> None:
    (runnable,) = e2e_cases.validate_steps(
        [
            {
                "action": "Run `.venv/Scripts/python.exe -m pytest apps/x/tests/test_y.py -q` now",
                "expected": "green",
            }
        ]
    )
    assert runnable["agent_runnable"] is True
    (prose,) = e2e_cases.validate_steps([{"action": "Look at the view", "expected": "seen"}])
    assert prose["agent_runnable"] is False


SITE_DIFF = """diff --git a/company-site/style.css b/company-site/style.css
index 111..222 100644
--- a/company-site/style.css
+++ b/company-site/style.css
@@ -1,4 +1,8 @@ body {
+@media (prefers-color-scheme: dark) {
+  body { background: #111; }
+}
"""


def test_evidence_keeps_company_site_files_without_symbols() -> None:
    evidence = e2e_cases.extract_diff_evidence(
        "repo", "base", "head", ["company-site/style.css"], runner=_runner(SITE_DIFF)
    )
    assert "company-site/style.css" in evidence


def _site_evidence(*paths: str) -> dict:
    return {path: {"symbols": [], "routes": [], "views": []} for path in paths}


def test_site_steps_ground_pages_and_assets() -> None:
    evidence = _site_evidence("company-site/kontakt.html", "company-site/style.css")
    steps = e2e_cases.draft_steps("company-site", evidence, ["dark mode"])
    assert steps
    assert all(step["grounded"] for step in steps)
    actions = " ".join(step["action"] for step in steps)
    assert "company-site/kontakt.html" in actions
    assert "company-site/style.css" in actions
    assert "dark mode" in actions
    assert not e2e_cases.needs_pointers(steps)


def test_route_table_covers_app_routes_or_known() -> None:
    import re
    from pathlib import Path

    from e2e_cases import KNOWN_UNMAPPED, ROUTE_UI

    src = (Path(__file__).resolve().parent.parent / "dashboard_web_app.py").read_text(
        encoding="utf-8"
    )
    routes = sorted(set(re.findall(r'"/api/[a-z0-9/_-]+"', src)))
    assert routes, "audit found no routes to check"
    for quoted in routes:
        path = quoted.strip('"')
        mapped = any(path == p.rstrip("/") or path.startswith(p) for p, _, _ in ROUTE_UI)
        assert mapped or path in KNOWN_UNMAPPED, f"unmapped route: {path}"


def test_symbol_registry_replaces_generic_step() -> None:
    steps = e2e_cases.draft_steps(
        "dashboard",
        {
            "apps/workbench_dashboard/web/app.js": {
                "symbols": ["spendPolicyRuleRow"],
                "routes": ["/api/spend/policy"],
                "views": [],
            }
        },
        ["dashboard surface"],
    )
    assert len(steps) == 2
    assert "add a policy rule" in steps[0]["action"]
    assert "remove the rule" in steps[1]["action"]
    assert all(step["grounded"] for step in steps)


def test_symbol_registry_entries_valid_and_routed() -> None:
    import re
    from pathlib import Path

    from e2e_cases import SYMBOL_STEPS, validate_steps

    router = (Path(__file__).resolve().parent.parent / "web" / "app.js").read_text(encoding="utf-8")
    names = set(re.findall(r'name === "([a-z0-9_-]+)"', router)) | {"home"}
    assert SYMBOL_STEPS, "registry must not be empty"
    for symbol, entry in SYMBOL_STEPS.items():
        assert entry["label"] and entry["view_hash"].startswith("#/")
        view = entry["view_hash"].removeprefix("#/").split("/")[0] or "home"
        assert view in names, f"{symbol} points at missing view {view}"
        validate_steps([{"action": entry["action"], "expected": entry["expected"]}])


def test_unmapped_route_gets_probe_step() -> None:
    steps = e2e_cases.draft_steps(
        "dashboard",
        {
            "apps/workbench_dashboard/dashboard_web_app.py": {
                "symbols": [],
                "routes": ["/api/settings"],
                "views": [],
            }
        },
        ["dashboard surface"],
    )
    assert len(steps) == 1
    assert "e2e-http-get.py /api/settings 200" in steps[0]["action"]
    assert steps[0]["grounded"] is True
    assert steps[0]["agent_runnable"] is True


def test_site_schema_only_needs_pointers() -> None:
    evidence = _site_evidence("company-site/intake/schema.json")
    steps = e2e_cases.draft_steps("company-site", evidence, ["intake schema"])
    assert steps
    assert e2e_cases.needs_pointers(steps)


def test_orchestrator_splits_suite_from_trigger() -> None:
    evidence = {
        "packages/ai_orchestrator/src/ai_orchestrator/deliberation.py": {
            "symbols": ["request_verdict"],
            "routes": [],
            "views": [],
        }
    }
    (suite, trigger) = e2e_cases.draft_steps("orchestrator", evidence, ["s"])
    assert suite["agent_runnable"] is True
    assert "run-tests.py orchestrator" in suite["action"]
    assert "scoped pytest" not in trigger["action"]
    assert "request_verdict" in trigger["action"]


def test_provider_splits_suite_from_trigger() -> None:
    evidence = {
        "packages/ai_provider/src/ai_provider/source_claims.py": {
            "symbols": ["extract_claims"],
            "routes": [],
            "views": [],
        }
    }
    (suite, trigger) = e2e_cases.draft_steps("provider", evidence, ["s"])
    assert suite["agent_runnable"] is True
    assert "run-tests.py provider" in suite["action"]
    assert "scoped pytest" not in trigger["action"]


def test_test_only_evidence_gets_no_extra_suite_step() -> None:
    evidence = {
        "tests/test_source_claims.py": {
            "symbols": ["test_x"],
            "routes": [],
            "views": [],
        }
    }
    (step,) = e2e_cases.draft_steps("provider", evidence, ["s"])
    assert "pytest tests/test_source_claims.py -q" in step["action"]
