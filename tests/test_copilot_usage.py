"""Native Copilot quota observations retain billing units and bounded ownership."""

import json
import os
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest
from ai_provider import copilot_usage as usage
from ai_provider.acceptance_processes import process_identity

SNAPSHOT = {
    "entitlementRequests": 300,
    "usedRequests": 75.5,
    "remainingPercentage": 74.8,
    "resetDate": "2026-11-01T00:00:00Z",
}


def test_quota_types_units_and_unlimited_are_retained_without_account_identity():
    windows = usage.normalize_quota(
        {
            "quotaSnapshots": {
                "premium_interactions": SNAPSHOT,
                "chat": {"entitlementRequests": -1, "usedRequests": 1000},
            },
            "login": "private-owner",
            "plan": "private-plan",
        }
    )
    assert windows == [
        {
            "bucket_id": "premium_interactions",
            "window": "entitlement",
            "entitlement_requests": 300,
            "used_requests": 75.5,
            "remaining_percent": 74.8,
            "reset_date": "2026-11-01T00:00:00Z",
        },
        {
            "bucket_id": "chat",
            "window": "entitlement",
            "entitlement_requests": -1,
            "used_requests": 1000,
            "remaining_percent": None,
            "reset_date": None,
        },
    ]
    assert "private" not in json.dumps(windows)


@pytest.mark.parametrize("response", [{}, {"quotaSnapshots": {}}, {"quotaSnapshots": None}])
def test_missing_quota_does_not_invent_zero_balance(response):
    assert usage.normalize_quota(response) == []


def test_partial_snapshot_and_unzoned_reset_preserve_unknowns():
    window = usage.normalize_quota({"quotaSnapshots": {"chat": {"resetDate": "2026-11-01"}}})[0]
    assert window["entitlement_requests"] is None and window["used_requests"] is None
    assert window["remaining_percent"] is None and window["reset_date"] == "2026-11-01"


@pytest.mark.parametrize(
    "field,value",
    [
        ("entitlementRequests", -2),
        ("entitlementRequests", -0.5),
        ("entitlementRequests", True),
        ("usedRequests", -1),
        ("usedRequests", False),
        ("remainingPercentage", 101),
        ("remainingPercentage", -1),
        ("remainingPercentage", float("nan")),
        ("usedRequests", float("inf")),
        ("resetDate", "private-owner"),
        ("resetDate", False),
        ("resetDate", "2026-02-30"),
        ("resetDate", "2026-11-01\n00:00:00"),
    ],
)
def test_invalid_measurements_are_not_admitted(field, value):
    with pytest.raises(ValueError):
        usage.normalize_quota(
            {"quotaSnapshots": {"premium_interactions": {**SNAPSHOT, field: value}}}
        )


@pytest.fixture
def synthetic_client(tmp_path, monkeypatch):
    script = tmp_path / "quota_client.py"
    script.write_text(
        """
import json, sys, time, subprocess
from pathlib import Path
mode, directory = sys.argv[1:]
directory = Path(directory)
header = sys.stdin.buffer.readline()
length = int(header.split(b":", 1)[1])
sys.stdin.buffer.readline()
request = json.loads(sys.stdin.buffer.read(length))
(directory / "request.json").write_text(json.dumps(request))
def send(value):
    body = json.dumps(value).encode()
    sys.stdout.buffer.write(f"Content-Length: {len(body)}\\r\\n\\r\\n".encode() + body)
    sys.stdout.buffer.flush()
if mode == "hang":
    time.sleep(30)
if mode == "child":
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    (directory / "child.pid").write_text(str(child.pid))
if mode == "oversized":
    sys.stdout.buffer.write(b"Content-Length: 1048577\\r\\n\\r\\n")
    sys.stdout.buffer.flush()
    time.sleep(30)
if mode == "bad_header":
    sys.stdout.buffer.write(b"Content-Length: " + b"9" * 1025)
    sys.stdout.buffer.flush()
    time.sleep(30)
if mode == "server_request":
    send({"jsonrpc": "2.0", "id": 9, "method": "auth.request", "params": {}})
elif mode == "error":
    send({"jsonrpc": "2.0", "id": 1, "error": {"message": "private-secret"}})
elif mode == "wrong_id":
    send({"jsonrpc": "2.0", "id": True, "result": {}})
elif mode == "float_id":
    send({"jsonrpc": "2.0", "id": 1.0, "result": {}})
elif mode == "error_with_result":
    send({"jsonrpc": "2.0", "id": 1, "result": {"quotaSnapshots": {"chat": {}}},
          "error": {"message": "private-secret"}})
elif mode == "invalid_json":
    sys.stdout.buffer.write(b"Content-Length: 14\\r\\n\\r\\nprivate-secret")
    sys.stdout.buffer.flush()
elif mode == "wrong_version":
    send({"jsonrpc": "1.0", "id": 1, "result": {}})
elif mode == "no_version":
    send({"id": 1, "result": {}})
elif mode == "too_many_notifications":
    for _ in range(65):
        send({"jsonrpc": "2.0", "method": "notification"})
elif mode == "missing":
    send({"jsonrpc": "2.0", "id": 1, "result": {}})
else:
    send({"jsonrpc": "2.0", "method": "notification", "params": {"private": "discard"}})
    send({"jsonrpc": "2.0", "id": 1, "result": {"quotaSnapshots": {
        "premium_interactions": {"entitlementRequests": 300, "usedRequests": 75,
        "remainingPercentage": 75, "resetDate": "2026-11-01"}}, "login": "private-owner"}})
time.sleep(30)
""",
        encoding="utf-8",
    )
    native_popen = subprocess.Popen
    processes = []
    commands = []
    monkeypatch.setattr(usage, "external_agent_command", lambda method: sys.executable)
    monkeypatch.delenv("COPILOT_PROVIDER_BASE_URL", raising=False)
    monkeypatch.delenv("COPILOT_PROVIDER_API_KEY", raising=False)

    def run(mode):
        def start(command, **kwargs):
            commands.append(command)
            process = native_popen(
                [sys.executable, "-u", str(script), mode, str(tmp_path)], **kwargs
            )
            processes.append(process)
            return process

        monkeypatch.setattr(usage.subprocess, "Popen", start)
        return usage.read_copilot_allowance(timeout_seconds=0.2 if mode == "hang" else 3)

    yield run, processes, commands
    for process in processes:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=2)


def test_actual_stdio_request_is_account_only_and_cleans_owned_process(synthetic_client, tmp_path):
    run, processes, commands = synthetic_client
    report = run("success")
    assert report["status"] == "available" and report["cleanup_verified"]
    assert report["source"] == "copilot_account_quota" and report["observed_at_utc"]
    assert report["windows"][0]["remaining_percent"] == 75
    assert report["windows"][0]["reset_date"] == "2026-11-01"
    assert "private" not in json.dumps(report)
    assert json.loads((tmp_path / "request.json").read_text()) == {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "account.getQuota",
        "params": {},
    }
    assert commands[0][1:] == ("--headless", "--no-auto-update", "--log-level", "none", "--stdio")
    assert processes[0].poll() is not None
    assert processes[0].stdin.closed and processes[0].stdout.closed


@pytest.mark.parametrize(
    "mode",
    [
        "hang",
        "oversized",
        "bad_header",
        "server_request",
        "error",
        "wrong_id",
        "float_id",
        "error_with_result",
        "invalid_json",
        "wrong_version",
        "no_version",
        "too_many_notifications",
        "missing",
    ],
)
def test_failures_are_unknown_redacted_and_cleaned(synthetic_client, mode):
    run, processes, _ = synthetic_client
    started = time.monotonic()
    report = run(mode)
    assert time.monotonic() - started < 5
    assert report["status"] == "unknown" and report["windows"] == []
    assert report["observed_at_utc"] is None and report["cleanup_verified"]
    assert "private" not in json.dumps(report)
    assert processes[0].poll() is not None


def test_owned_cleanup_terminates_descendant(synthetic_client, tmp_path):
    run, _, _ = synthetic_client
    report = run("child")
    assert report["status"] == "available" and report["cleanup_verified"]
    pid = int((tmp_path / "child.pid").read_text())
    identity = process_identity(pid)
    if os.name != "nt" and identity is not None:
        assert Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] == "Z"
    else:
        assert identity is None


@pytest.mark.parametrize("key", ["COPILOT_PROVIDER_BASE_URL", "COPILOT_PROVIDER_API_KEY"])
def test_byok_does_not_query_subscription_account(monkeypatch, key):
    monkeypatch.setenv(key, "private-configured-value")
    monkeypatch.setattr(usage.subprocess, "Popen", lambda *a, **k: pytest.fail("process started"))
    report = usage.read_copilot_allowance()
    assert report["status"] == "unknown" and report["reason"] == "subscription_billing_overridden"
    assert "private" not in json.dumps(report)


def test_dispatch_only_supported_subscription_billing(monkeypatch):
    from ai_orchestrator import (
        AccessMethod,
        BillingSource,
        CostPolicyTier,
        PrivacyClass,
        load_model_catalog,
        prepare_execution,
    )
    from ai_provider import account_usage
    from ai_provider.coding_assist import coding_task_profile

    catalog = load_model_catalog("packages/ai_orchestrator/examples/model_catalog.toml")
    profile = coding_task_profile(
        route_id_override="github-copilot-cli-default",
        privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
        cost_policy_tier=CostPolicyTier.ALLOWANCES_ALLOWED,
    )
    plan = prepare_execution("Test", profile, catalog, review_prompt=False).execution_plan
    assert plan is not None
    calls = []

    def read(**kwargs):
        calls.append(kwargs)
        return {"status": "unknown"}

    monkeypatch.setattr(usage, "read_copilot_allowance", read)
    target = replace(plan.target, timeout_seconds=2)
    assert account_usage.read_execution_allowance(target) == {"status": "unknown"}
    assert calls == [{"timeout_seconds": 2}]
    for method, billing in (
        (AccessMethod.COPILOT_CLI, BillingSource.OPENAI_API_BILLING),
        (AccessMethod.KIRO_CLI, BillingSource.OPENAI_API_BILLING),
    ):
        assert (
            account_usage.read_execution_allowance(
                replace(target, access_method=method, billing_source=billing)
            )
            is None
        )
    assert len(calls) == 1
