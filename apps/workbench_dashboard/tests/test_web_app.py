from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from dashboard_test_http import get_json
from dashboard_web_app import (
    FLEET_TASKS,
    DashboardRequestHandler,
    fleet_ollama,
    fleet_sleep,
    fleet_tasks,
    run_failure,
    with_run_failure,
)


def post_json(base: str, path: str, payload: dict, headers: dict | None = None) -> dict:
    request = Request(
        f"{base}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


@pytest.fixture
def dashboard_server(tmp_path, monkeypatch):
    config_path = tmp_path / "dashboard.json"
    config_path.write_text(
        json.dumps({"provider": "ollama", "model": "fake", "title": "Test Board"}),
        encoding="utf-8",
    )
    data_dir = tmp_path / "data"

    class TestHandler(DashboardRequestHandler):
        def log_message(self, format, *args):
            return

    TestHandler.config_path = config_path
    TestHandler.data_dir = data_dir
    TestHandler.repo_root = tmp_path
    server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def fake_execute(self, request):
        from ai_agent.coding_chat import CodingTurnResult

        return CodingTurnResult(0, "Fake answer.", "completed", provider="ollama")

    monkeypatch.setattr("dashboard_chat.DashboardChat._execute", fake_execute)

    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


def test_status_reports_empty_state(dashboard_server) -> None:
    payload = get_json(dashboard_server, "/api/status")
    assert payload["ok"] is True
    assert payload["title"] == "Test Board"
    assert payload["open_inbox"] == 0
    assert payload["current_plan"] is None
    assert payload["evidence"]["available"] is False


def test_evidence_merges_snapshots(dashboard_server, tmp_path) -> None:
    probes = tmp_path / "artifacts" / "route-probes"
    evals = tmp_path / "artifacts" / "route-evals"
    probes.mkdir(parents=True)
    evals.mkdir(parents=True)
    (probes / "route-probe-20261101T000000Z.json").write_text(
        json.dumps([{"route": "meta", "reachable": True}]), encoding="utf-8"
    )
    (evals / "route-eval-20261101T000000Z.json").write_text(
        json.dumps([{"route": "meta", "passed": True}]), encoding="utf-8"
    )
    payload = get_json(dashboard_server, "/api/evidence")
    assert payload["ok"] is True
    assert payload["available"] is True
    assert payload["routes"] == [{"route": "meta", "reachable": True, "passed_eval": True}]


def test_chat_round_trip(dashboard_server) -> None:
    created = post_json(dashboard_server, "/api/chat/sessions", {"title": "Hello"})
    assert created["ok"] is True
    session_id = created["id"]

    answer = post_json(
        dashboard_server, f"/api/chat/sessions/{session_id}/messages", {"text": "Hi there"}
    )
    assert answer["ok"] is True
    assert answer["response_text"] == "Fake answer."

    messages = get_json(dashboard_server, f"/api/chat/sessions/{session_id}/messages")
    assert [message["role"] for message in messages["messages"]] == ["user", "assistant"]

    sessions = get_json(dashboard_server, "/api/chat/sessions")
    assert [session["id"] for session in sessions["sessions"]] == [session_id]


def test_chat_rejects_empty_message(dashboard_server) -> None:
    created = post_json(dashboard_server, "/api/chat/sessions", {})
    with pytest.raises(HTTPError) as raised:
        post_json(dashboard_server, f"/api/chat/sessions/{created['id']}/messages", {"text": "  "})
    assert raised.value.code == 400
    raised.value.close()


def test_inbox_flow_and_token_gate(dashboard_server, tmp_path) -> None:
    created = post_json(
        dashboard_server,
        "/api/inbox",
        {"title": "Pick one", "body": "A or B?", "type": "decision", "options": ["A", "B"]},
    )
    assert created["ok"] is True
    item_id = created["id"]

    status = get_json(dashboard_server, "/api/status")
    assert status["open_inbox"] == 1

    answered = post_json(
        dashboard_server, f"/api/inbox/{item_id}/answer", {"answer": "", "option_index": 0}
    )
    assert answered["status"] == "answered"

    closed = post_json(dashboard_server, f"/api/inbox/{item_id}/close", {"resolution": "Picked A."})
    assert closed["status"] == "closed"
    item = get_json(dashboard_server, f"/api/inbox/{item_id}")
    assert item["item"]["resolution"] == "Picked A."
    reopened = post_json(dashboard_server, f"/api/inbox/{item_id}/reopen", {})
    assert reopened["status"] == "open"

    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "supervisor.token").write_text("s3cret", encoding="utf-8")
    with pytest.raises(HTTPError) as raised:
        post_json(dashboard_server, "/api/inbox", {"title": "t", "body": "b", "type": "decision"})
    assert raised.value.code == 403
    raised.value.close()

    gated = post_json(
        dashboard_server,
        "/api/inbox",
        {"title": "t", "body": "b", "type": "decision"},
        headers={"X-Supervisor-Token": "s3cret"},
    )
    assert gated["ok"] is True


def test_ideas_capture_filter_and_triage(dashboard_server) -> None:
    mine = post_json(
        dashboard_server,
        "/api/ideas",
        {"title": "Owner thought", "body": "Faster loop.", "source": "owner"},
    )
    assert mine["ok"] is True
    theirs = post_json(
        dashboard_server,
        "/api/ideas",
        {
            "title": "Friend wish",
            "body": "Plant app.",
            "source": "third-party",
            "contact": "Friend",
        },
    )
    assert theirs["ok"] is True

    status = get_json(dashboard_server, "/api/status")
    assert status["new_ideas"] == 2

    third_party = get_json(dashboard_server, "/api/ideas?source=third-party")
    assert [item["id"] for item in third_party["items"]] == [theirs["id"]]

    detail = get_json(dashboard_server, f"/api/ideas/{theirs['id']}")
    assert detail["item"]["contact"] == "Friend"

    reviewed = post_json(
        dashboard_server,
        f"/api/ideas/{theirs['id']}/review",
        {"status": "adopted", "decision": "Prototype"},
    )
    assert reviewed["status"] == "adopted"

    remaining = get_json(dashboard_server, "/api/ideas?status=new")
    assert [item["id"] for item in remaining["items"]] == [mine["id"]]


def test_trusted_host_allowlist_accepts_tailnet_origin(dashboard_server, tmp_path) -> None:
    config_path = tmp_path / "dashboard.json"
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    payload["trusted_hosts"] = ["example.tailc59785.ts.net"]
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    host = "example.tailc59785.ts.net"
    allowed = Request(
        f"{dashboard_server}/api/status",
        headers={"Host": host, "Origin": f"https://{host}"},
        method="GET",
    )
    with urlopen(allowed, timeout=5) as response:
        assert json.loads(response.read().decode("utf-8"))["ok"] is True
    downgraded = Request(
        f"{dashboard_server}/api/status",
        headers={"Host": host, "Origin": f"http://{host}"},
        method="GET",
    )
    with pytest.raises(HTTPError) as raised:
        urlopen(downgraded, timeout=5)
    assert raised.value.code == 403
    raised.value.close()
    stranger = Request(
        f"{dashboard_server}/api/status", headers={"Host": "evil.invalid"}, method="GET"
    )
    with pytest.raises(HTTPError) as raised:
        urlopen(stranger, timeout=5)
    assert raised.value.code == 403
    raised.value.close()


def test_trusted_hosts_config_validation(tmp_path) -> None:
    from dashboard_config import load_config

    config_path = tmp_path / "dashboard.json"
    config_path.write_text(json.dumps({"trusted_hosts": ["a.ts.net"]}), encoding="utf-8")
    assert load_config(config_path).trusted_hosts == ("a.ts.net",)
    for bad in ([""], ["a b"], [1], "a.ts.net"):
        config_path.write_text(json.dumps({"trusted_hosts": bad}), encoding="utf-8")
        with pytest.raises(ValueError):
            load_config(config_path)


def test_untrusted_origin_refused(dashboard_server) -> None:
    request = Request(
        f"{dashboard_server}/api/status", headers={"Origin": "https://evil.invalid"}, method="GET"
    )
    with pytest.raises(HTTPError) as raised:
        urlopen(request, timeout=5)
    assert raised.value.code == 403
    raised.value.close()


def test_filtered_totals_count_matches(dashboard_server) -> None:
    first = post_json(
        dashboard_server,
        "/api/inbox",
        {"title": "One", "body": "1", "type": "decision", "options": ["A"]},
    )
    post_json(
        dashboard_server,
        "/api/inbox",
        {"title": "Two", "body": "2", "type": "decision"},
    )
    post_json(dashboard_server, f"/api/inbox/{first['id']}/answer", {"answer": "done"})
    answered = get_json(dashboard_server, "/api/inbox?status=answered")
    assert answered["total"] == 1
    assert len(answered["items"]) == 1
    still_open = get_json(dashboard_server, "/api/inbox?status=open")
    assert still_open["total"] == 1


def test_run_report_request_creates_order_task(dashboard_server, tmp_path) -> None:
    runs_dir = tmp_path / "data" / "runs"
    runs_dir.mkdir(parents=True)
    (runs_dir / "w4.json").write_text(
        json.dumps({"id": "w4", "title": "W4 fix", "status": "merged"}), encoding="utf-8"
    )
    first = post_json(dashboard_server, "/api/runs/w4/report-request", {})
    assert first["ok"] is True
    task = get_json(dashboard_server, f"/api/inbox/{first['id']}")
    assert task["item"]["type"] == "order"
    assert task["item"]["task_id"] == "w4"
    assert "W4 fix" in task["item"]["title"]
    run = get_json(dashboard_server, "/api/runs/w4")
    assert run["item"]["report_request_id"] == first["id"]
    second = post_json(dashboard_server, "/api/runs/w4/report-request", {})
    assert second.get("deduped") is True
    assert second["id"] == first["id"]


def test_run_report_request_unknown_run_is_404(dashboard_server) -> None:
    with pytest.raises(HTTPError) as raised:
        post_json(dashboard_server, "/api/runs/nope/report-request", {})
    assert raised.value.code == 404
    raised.value.close()


def test_chat_rename_and_delete_endpoints(dashboard_server) -> None:
    created = post_json(dashboard_server, "/api/chat/sessions", {"title": "Typo"})
    session_id = created["id"]
    renamed = post_json(
        dashboard_server,
        f"/api/chat/sessions/{session_id}/rename",
        {"title": "Fixed"},
    )
    assert renamed["ok"] is True
    assert renamed["title"] == "Fixed"
    sessions = get_json(dashboard_server, "/api/chat/sessions")
    assert [s["title"] for s in sessions["sessions"]] == ["Fixed"]
    deleted = post_json(dashboard_server, f"/api/chat/sessions/{session_id}/delete", {})
    assert deleted["ok"] is True
    sessions = get_json(dashboard_server, "/api/chat/sessions")
    assert sessions["sessions"] == []
    with pytest.raises(HTTPError) as raised:
        post_json(dashboard_server, f"/api/chat/sessions/{session_id}/delete", {})
    assert raised.value.code == 404
    raised.value.close()


def test_chat_rename_rejects_empty_title(dashboard_server) -> None:
    created = post_json(dashboard_server, "/api/chat/sessions", {"title": "Keep"})
    with pytest.raises(HTTPError) as raised:
        post_json(
            dashboard_server,
            f"/api/chat/sessions/{created['id']}/rename",
            {"title": "  "},
        )
    assert raised.value.code == 400
    raised.value.close()


def _write_run(tmp_path, run_id: str, record: dict) -> None:
    runs_dir = tmp_path / "data" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / f"{run_id}.json").write_text(json.dumps(record), encoding="utf-8")


def test_runs_detail_reports_effective_fanout(dashboard_server, tmp_path) -> None:
    _write_run(
        tmp_path,
        "w4",
        {
            "id": "w4",
            "title": "W4 fix",
            "status": "merged",
            "fanout_effective": "restricted",
            "fanout_policy": "allowed",
        },
    )
    run = get_json(dashboard_server, "/api/runs/w4")
    assert run["item"]["fanout_effective"] == "restricted"


def test_runs_detail_falls_back_to_fanout_policy(dashboard_server, tmp_path) -> None:
    _write_run(tmp_path, "w4", {"id": "w4", "fanout_policy": "denied"})
    run = get_json(dashboard_server, "/api/runs/w4")
    assert run["item"]["fanout_effective"] == "denied"


def test_runs_detail_unknown_for_legacy_record(dashboard_server, tmp_path) -> None:
    _write_run(tmp_path, "w4", {"id": "w4", "title": "W4 fix", "status": "merged"})
    run = get_json(dashboard_server, "/api/runs/w4")
    assert run["item"]["fanout_effective"] == "unknown"
    stored = json.loads((tmp_path / "data" / "runs" / "w4.json").read_text(encoding="utf-8"))
    assert "fanout_effective" not in stored


def test_runs_list_resolves_fanout_per_item(dashboard_server, tmp_path) -> None:
    _write_run(tmp_path, "new", {"id": "new", "fanout_effective": "allowed"})
    _write_run(tmp_path, "old", {"id": "old", "status": "merged"})
    payload = get_json(dashboard_server, "/api/runs")
    by_id = {item["id"]: item["fanout_effective"] for item in payload["items"]}
    assert by_id == {"new": "allowed", "old": "unknown"}


def test_run_failure_derives_reason_from_failed_event() -> None:
    run = {
        "id": "f1",
        "status": "failed",
        "events": [
            {"seq": 1, "kind": "run_started", "payload": {}, "at_utc": "2026-11-07T10:00:00+00:00"},
            {
                "seq": 2,
                "kind": "run_failed",
                "payload": {"reason": "pytest red"},
                "at_utc": "2026-11-07T10:05:00+00:00",
            },
        ],
    }
    assert run_failure(run) == {
        "state": "failed",
        "reason": "pytest red",
        "at_utc": "2026-11-07T10:05:00+00:00",
    }


def test_run_failure_without_signals_has_no_reason() -> None:
    assert run_failure({"id": "f2", "status": "failed"}) == {
        "state": "failed",
        "reason": None,
        "at_utc": None,
    }


def test_run_failure_falls_back_to_failed_receipt() -> None:
    run = {
        "id": "f3",
        "status": "failed",
        "receipts": [
            {"status": "failed", "detail": "drain crashed", "at_utc": "2026-11-07T11:00:00+00:00"}
        ],
    }
    assert run_failure(run) == {
        "state": "failed",
        "reason": "drain crashed",
        "at_utc": "2026-11-07T11:00:00+00:00",
    }


def test_run_failure_ignores_recovered_receipt() -> None:
    run = {
        "id": "ok",
        "status": "completed",
        "receipts": [{"status": "failed", "detail": "first try"}],
    }
    assert run_failure(run) is None


def test_run_failure_ignores_cancelled_and_empty() -> None:
    assert run_failure({"id": "c", "status": "cancelled"}) is None
    assert run_failure({}) is None
    assert run_failure({"id": "x"}) is None


def test_with_run_failure_attaches_without_mutating() -> None:
    run = {"id": "f1", "status": "failed"}
    enriched = with_run_failure(run)
    assert enriched["failure"] == {"state": "failed", "reason": None, "at_utc": None}
    assert "failure" not in run


def test_runs_detail_includes_failure_summary(dashboard_server, tmp_path) -> None:
    _write_run(
        tmp_path,
        "f9",
        {
            "id": "f9",
            "status": "failed",
            "events": [
                {"seq": 1, "kind": "run_failed", "payload": {"reason": "boom"}, "at_utc": "t"}
            ],
        },
    )
    run = get_json(dashboard_server, "/api/runs/f9")
    assert run["item"]["failure"] == {"state": "failed", "reason": "boom", "at_utc": "t"}


def test_runs_detail_failure_null_when_healthy(dashboard_server, tmp_path) -> None:
    _write_run(tmp_path, "ok", {"id": "ok", "status": "merged"})
    run = get_json(dashboard_server, "/api/runs/ok")
    assert run["item"]["failure"] is None


def test_status_reports_scheduler_off_by_default(dashboard_server) -> None:
    """Fresh servers report the drain scheduler as not started."""
    payload = get_json(dashboard_server, "/api/status")
    sched = payload["drain_scheduler"]
    assert sched["started"] is False
    assert sched["interval_seconds"] == 0
    assert sched["ticks"] == 0
    assert sched["errors"] == 0
    assert sched["last_error"] is None


def test_status_reports_live_scheduler_state(dashboard_server, monkeypatch) -> None:
    """An injected scheduler handle surfaces ticks/errors on /api/status."""
    from types import SimpleNamespace

    fake = SimpleNamespace(started=True, ticks=3, errors=1, last_error="boom")
    monkeypatch.setattr(DashboardRequestHandler, "drain_scheduler", fake)
    payload = get_json(dashboard_server, "/api/status")
    sched = payload["drain_scheduler"]
    assert sched["started"] is True
    assert sched["ticks"] == 3
    assert sched["errors"] == 1
    assert sched["last_error"] == "boom"


def test_inbox_close_requires_resolution(dashboard_server) -> None:
    created = post_json(
        dashboard_server,
        "/api/inbox",
        {"title": "t", "body": "b", "type": "decision"},
    )
    with pytest.raises(HTTPError) as raised:
        post_json(dashboard_server, f"/api/inbox/{created['id']}/close", {})
    assert raised.value.code == 400
    raised.value.close()


def _grant(allowance_id, provider="meta", kind="free_daily", granted_cents=500, **extra):
    payload = {
        "allowance_id": allowance_id,
        "provider": provider,
        "kind": kind,
        "granted_cents": granted_cents,
        "local_spending_limit_accepted": True,
    }
    payload.update(extra)
    return payload


def _write_grants(tmp_path, files):
    grants = tmp_path / "data" / "spend" / "grants"
    grants.mkdir(parents=True)
    for name, payload in files.items():
        (grants / name).write_text(json.dumps(payload), encoding="utf-8")
    return grants


def test_spend_unconfigured_empty(dashboard_server) -> None:
    payload = get_json(dashboard_server, "/api/spend")
    assert payload["ok"] is True
    assert payload["spend"]["configured"] is False
    assert payload["spend"]["buckets"] == []
    assert payload["spend"]["open_reservations"] == 0
    assert payload["spend"]["records"] == 0


def test_spend_lists_grant_buckets(dashboard_server, tmp_path) -> None:
    _write_grants(
        tmp_path,
        {
            "a.json": _grant("meta-free"),
            "b.json": _grant(
                "meta-exp",
                kind="allowance_expiring",
                granted_cents=100,
                expires_at=4102444800,
            ),
        },
    )
    payload = get_json(dashboard_server, "/api/spend")
    assert payload["spend"]["configured"] is True
    buckets = {item["id"]: item for item in payload["spend"]["buckets"]}
    assert set(buckets) == {"meta-free", "meta-exp"}
    assert buckets["meta-free"]["status"] == "active"
    assert buckets["meta-free"]["balance_cents"] == 500
    assert buckets["meta-free"]["granted_cents"] == 500
    assert buckets["meta-exp"]["kind"] == "allowance_expiring"
    assert buckets["meta-exp"]["status"] == "active"


def test_spend_malformed_grant_is_400(dashboard_server, tmp_path) -> None:
    _write_grants(tmp_path, {"bad.json": {"allowance_id": "x"}})
    with pytest.raises(HTTPError) as raised:
        get_json(dashboard_server, "/api/spend")
    assert raised.value.code == 400
    assert "bad.json" in raised.value.read().decode("utf-8")
    raised.value.close()


def test_spend_duplicate_grant_id_is_400(dashboard_server, tmp_path) -> None:
    _write_grants(
        tmp_path,
        {"a.json": _grant("dup"), "b.json": _grant("dup", provider="baseten")},
    )
    with pytest.raises(HTTPError) as raised:
        get_json(dashboard_server, "/api/spend")
    assert raised.value.code == 400
    raised.value.close()


def test_fleet_shape_with_stubbed_probes(dashboard_server, monkeypatch) -> None:
    monkeypatch.setattr(
        "dashboard_web_app.fleet_tasks",
        lambda runner=None: [
            {
                "name": "WorkbenchDashboard",
                "present": True,
                "state": "Ready",
                "last_run": "2026-11-07T15:00:00",
                "next_run": "2026-11-07T15:05:00",
                "last_result": 0,
            }
        ],
    )
    monkeypatch.setattr(
        "dashboard_web_app.fleet_ollama", lambda urlopen=None: {"up": True, "models": 2}
    )
    monkeypatch.setattr(
        "dashboard_web_app.fleet_sleep",
        lambda repo_root: {"active": True, "status": "sleep_scheduled"},
    )
    payload = get_json(dashboard_server, "/api/fleet")
    assert payload["ok"] is True
    assert set(payload["fleet"]) == {"dashboard", "ollama", "tasks", "sleep", "runs"}
    assert payload["fleet"]["dashboard"] == {"up": True}
    assert payload["fleet"]["ollama"] == {"up": True, "models": 2}
    assert payload["fleet"]["tasks"][0]["name"] == "WorkbenchDashboard"
    assert payload["fleet"]["runs"] == []


def test_fleet_tasks_parses_probe_output(monkeypatch) -> None:
    monkeypatch.setattr("sys.platform", "win32")

    class _Done:
        stdout = json.dumps(
            [
                {
                    "name": "WorkbenchDashboard",
                    "present": True,
                    "state": "Ready",
                    "last_run": "a",
                    "next_run": "b",
                    "last_result": 0,
                },
                {"name": "MsiUdpWatchdog", "present": False},
            ]
        )

    rows = {row["name"]: row for row in fleet_tasks(runner=lambda *a, **k: _Done())}
    assert rows["WorkbenchDashboard"]["state"] == "Ready"
    assert rows["WorkbenchDashboard"]["last_result"] == 0
    assert rows["MsiUdpWatchdog"] == {
        "name": "MsiUdpWatchdog",
        "present": False,
        "detail": "not registered",
    }
    assert rows["CloneScan"]["present"] is False  # probe row missing entirely


def test_fleet_tasks_non_windows_is_gap(monkeypatch) -> None:
    monkeypatch.setattr("sys.platform", "linux")
    rows = fleet_tasks(runner=lambda *a, **k: None)
    assert [row["name"] for row in rows] == list(FLEET_TASKS)
    assert all(row["detail"] == "task probe is Windows-only" for row in rows)


def test_fleet_tasks_reports_runner_failure(monkeypatch) -> None:
    monkeypatch.setattr("sys.platform", "win32")

    def boom(*args, **kwargs):
        raise OSError("no powershell")

    rows = fleet_tasks(runner=boom)
    assert [row["name"] for row in rows] == list(FLEET_TASKS)
    assert all(row["present"] is False for row in rows)
    assert rows[0]["detail"] == "probe failed: OSError"


def test_fleet_ollama_down() -> None:
    def refused(*args, **kwargs):
        raise ConnectionRefusedError("down")

    assert fleet_ollama(urlopen=refused)["up"] is False


def test_fleet_sleep_idle_and_armed(tmp_path) -> None:
    assert fleet_sleep(tmp_path) == {"active": False}
    receipts = tmp_path / ".tmp" / "unattended-x"
    receipts.mkdir(parents=True)
    (receipts / "sleep-startup.json").write_text(
        json.dumps(
            {
                "status": "sleep_scheduled",
                "planned_sleep_utc": "due",
                "window_deadline_utc": "deadline",
                "process_id": 1234,
            }
        ),
        encoding="utf-8",
    )
    summary = fleet_sleep(tmp_path)
    assert summary["active"] is True
    assert summary["pid"] == 1234
    assert summary["receipt"] == "sleep-startup.json"
