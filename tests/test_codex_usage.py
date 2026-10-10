"""Quota collection uses a bounded native protocol, never model turns or raw exports."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from ai_provider import codex_usage as usage
from ai_provider import native_account_usage as native_usage
from ai_provider.acceptance_processes import process_identity

WINDOW = {"usedPercent": 25, "windowDurationMins": 300, "resetsAt": 1791626400}


def test_multibucket_view_is_authoritative_and_private_fields_are_omitted():
    windows = usage.normalize_rate_limits(
        {
            "rateLimits": {"limitId": "legacy", "primary": {**WINDOW, "usedPercent": 90}},
            "rateLimitsByLimitId": {
                "codex": {"limitId": "codex", "primary": WINDOW, "secondary": None},
                "codex_other": {"limitId": "codex_other", "primary": {**WINDOW, "usedPercent": 0}},
            },
            "credits": {"private": "must not be exported"},
            "email": "private@example.invalid",
        }
    )
    assert [w["used_percent"] for w in windows] == [25, 0]
    assert [w["bucket_id"] for w in windows] == ["codex", "codex_other"]
    assert "private" not in json.dumps(windows)


def test_legacy_nullable_fields_and_absent_buckets_do_not_invent_allowance():
    assert usage.normalize_rate_limits({}) == []
    assert usage.normalize_rate_limits({"rateLimitsByLimitId": {}}) == []
    assert usage.normalize_rate_limits({"rateLimits": {"primary": {"usedPercent": 100}}}) == [
        {
            "bucket_id": "legacy",
            "window": "primary",
            "used_percent": 100,
            "window_duration_minutes": None,
            "resets_at_unix_seconds": None,
        }
    ]


@pytest.mark.parametrize(
    "field,value",
    [
        ("usedPercent", True),
        ("usedPercent", -1),
        ("usedPercent", 101),
        ("usedPercent", float("nan")),
        ("usedPercent", float("inf")),
        ("usedPercent", "25"),
        ("windowDurationMins", True),
        ("windowDurationMins", 0),
        ("resetsAt", -1),
        ("resetsAt", True),
    ],
)
def test_malformed_window_refuses_before_becoming_a_measurement(field, value):
    with pytest.raises(ValueError):
        usage.normalize_rate_limits({"rateLimits": {"primary": {**WINDOW, field: value}}})


@pytest.fixture
def synthetic_client(tmp_path, monkeypatch):
    script = tmp_path / "client.py"
    script.write_text(
        """
import json, sys, time, subprocess
from pathlib import Path
mode, directory = sys.argv[1:]
directory = Path(directory)
def send(value):
    print(json.dumps(value), flush=True)
first = json.loads(sys.stdin.readline())
if mode == "hang":
    time.sleep(30)
if mode == "child":
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    (directory / "child.pid").write_text(str(child.pid))
if mode == "oversized":
    print("x" * 1048577, flush=True)
    time.sleep(30)
if mode == "wrong_id":
    send({"id": True, "result": {}})
elif mode == "invalid_json":
    print("private-secret-not-json", flush=True)
else:
    send({"method": "account/updated", "params": {"private": "discard"}})
    send({"id": 1, "result": {}})
ack = json.loads(sys.stdin.readline())
quota = json.loads(sys.stdin.readline())
(directory / "methods.json").write_text(json.dumps([first, ack, quota]))
if mode == "error":
    send({"id": 2, "error": {"code": -32601, "message": "private-secret"}})
elif mode == "server_request":
    send({"id": 9, "method": "account/chatgptAuthTokens/refresh", "params": {}})
elif mode == "missing":
    send({"id": 2, "result": {}})
else:
    send({"id": 2, "result": {"rateLimits": {
        "limitId": "codex", "limitName": "private label",
        "primary": {"usedPercent": 25, "windowDurationMins": 300, "resetsAt": 1791626400}
    }, "email": "private@example.invalid"}})
time.sleep(30)
""",
        encoding="utf-8",
    )
    native_popen = subprocess.Popen
    processes = []
    commands = []
    monkeypatch.setattr(usage, "external_agent_command", lambda method: sys.executable)

    def run(mode, *, timeout=None):
        def start(command, **kwargs):
            commands.append(command)
            process = native_popen(
                [sys.executable, "-u", str(script), mode, str(tmp_path)], **kwargs
            )
            processes.append(process)
            return process

        monkeypatch.setattr(usage.subprocess, "Popen", start)
        return usage.read_codex_allowance(
            timeout_seconds=timeout if timeout is not None else 0.3 if mode == "hang" else 3
        )

    yield run, processes, commands
    for process in processes:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=2)


def test_actual_stdio_handshake_reads_only_quota_and_closes_owned_process(
    synthetic_client, tmp_path
):
    run, processes, commands = synthetic_client
    report = run("success")
    assert report["status"] == "available" and report["observed_at_utc"]
    assert report["cleanup_verified"]
    assert report["windows"][0]["used_percent"] == 25
    assert "private" not in json.dumps(report)
    messages = json.loads((tmp_path / "methods.json").read_text())
    assert [m["method"] for m in messages] == [
        "initialize",
        "initialized",
        "account/rateLimits/read",
    ]
    assert commands[0][1:] == ("app-server", "--listen", "stdio://")
    assert processes[0].poll() is not None
    assert processes[0].stdin.closed and processes[0].stdout.closed


@pytest.mark.parametrize(
    "mode", ["hang", "wrong_id", "invalid_json", "oversized", "error", "server_request", "missing"]
)
def test_failure_and_timeout_are_unknown_redacted_and_cleaned(synthetic_client, mode):
    run, processes, _ = synthetic_client
    started = time.monotonic()
    report = run(mode)
    assert time.monotonic() - started < 5
    assert report["status"] == "unknown" and report["windows"] == []
    assert report["observed_at_utc"] is None and report["cleanup_verified"]
    assert "private" not in json.dumps(report)
    assert processes[0].poll() is not None


def test_owned_cleanup_includes_descendant_after_response(synthetic_client, tmp_path):
    run, _, _ = synthetic_client
    report = run("child")
    assert report["cleanup_verified"] and report["status"] == "available"
    pid = int((tmp_path / "child.pid").read_text())
    identity = process_identity(pid)
    if os.name != "nt" and identity is not None:
        # An orphaned POSIX zombie is terminated, even before init reaps its PID.
        assert Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] == "Z"
    else:
        assert identity is None


def test_expired_start_budget_does_not_query_quota(synthetic_client, tmp_path):
    run, processes, _ = synthetic_client
    report = run("success", timeout=0.000001)
    assert report["reason"] == "timeout" and report["cleanup_verified"]
    assert report["status"] == "unknown" and report["windows"] == []
    assert not (tmp_path / "methods.json").exists()
    assert processes[0].poll() is not None


@pytest.mark.parametrize("timeout", [True, 0, -1, 121, float("nan"), float("inf")])
def test_invalid_timeout_never_starts_a_client(monkeypatch, timeout):
    monkeypatch.setattr(usage.subprocess, "Popen", lambda *a, **k: pytest.fail("process started"))
    with pytest.raises(ValueError):
        usage.read_codex_allowance(timeout_seconds=timeout)


def test_missing_command_never_starts_a_client(monkeypatch):
    monkeypatch.setattr(usage, "external_agent_command", lambda method: None)
    monkeypatch.setattr(usage.subprocess, "Popen", lambda *a, **k: pytest.fail("process started"))
    report = usage.read_codex_allowance()
    assert report["reason"] == "client_unavailable" and report["status"] == "unknown"


def test_start_failure_is_redacted(monkeypatch):
    monkeypatch.setattr(usage, "external_agent_command", lambda method: "fixture-client")

    def fail(*args, **kwargs):
        raise OSError("private-secret-path")

    monkeypatch.setattr(usage.subprocess, "Popen", fail)
    report = usage.read_codex_allowance()
    assert report["reason"] == "client_start_failed"
    assert "private" not in json.dumps(report)


@pytest.mark.skipif(os.name != "nt", reason="Windows job ownership contract")
def test_unverified_cleanup_invalidates_measurements(monkeypatch, synthetic_client):
    original_job = native_usage.WindowsJob

    class UnverifiedJob(original_job):
        def stop(self, timeout: float) -> bool:
            super().stop(timeout)
            return False

    monkeypatch.setattr(native_usage, "WindowsJob", UnverifiedJob)
    run, _, _ = synthetic_client
    report = run("success")
    assert report["reason"] == "cleanup_unverified" and report["status"] == "unknown"
    assert report["windows"] == [] and report["observed_at_utc"] is None


@pytest.mark.skipif(os.name != "nt", reason="Windows job ownership contract")
def test_ownership_failure_stops_suspended_process_without_handshake(
    monkeypatch, synthetic_client, tmp_path
):
    def fail(*args):
        raise OSError("private-secret")

    monkeypatch.setattr(native_usage, "WindowsJob", fail)
    run, processes, _ = synthetic_client
    report = run("success")
    assert report["reason"] == "client_ownership_failed" and report["cleanup_verified"]
    assert processes[0].poll() is not None
    assert not (tmp_path / "methods.json").exists()


def test_cli_reports_only_normalized_observation(monkeypatch, capsys):
    monkeypatch.setattr(
        usage,
        "read_codex_allowance",
        lambda **k: {"status": "unknown", "reason": "timeout", "windows": []},
    )
    assert usage.main([]) == 1
    assert json.loads(capsys.readouterr().out)["reason"] == "timeout"
