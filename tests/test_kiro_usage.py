"""Kiro quota collection preserves isolation, native units and unknown results."""

import json
import os
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest
from ai_provider import kiro_usage as usage
from ai_provider.acceptance_processes import process_identity

OUTPUT = (
    "Estimated Usage | resets on 2026-11-01 | KIRO FREE\n"
    "Credits (50.00 of 50 covered in plan), 100.0%\n"
    "Manage your plan at https://app.kiro.dev/account/usage\n"
)


def test_native_credit_measurements_do_not_infer_remaining_or_percent_semantics():
    windows = usage.normalize_usage(OUTPUT)
    assert windows == [
        {
            "bucket_id": "plan_credits",
            "window": "subscription",
            "measurement_kind": "native_estimate",
            "covered_credits": 50,
            "plan_credits": 50,
            "reported_percent": 100,
            "reset_date": "2026-11-01",
        }
    ]
    assert "FREE" not in json.dumps(windows)
    assert "remaining" not in json.dumps(windows)
    assert usage.normalize_usage("\x1b[32m" + OUTPUT + "\x1b[0m") == windows


@pytest.mark.parametrize(
    "text",
    [
        "",
        "private account error",
        OUTPUT + "Bonus Credits: 10\n",
        OUTPUT.replace("50.00", "nan"),
        OUTPUT.replace("50.00", "51"),
        OUTPUT.replace("100.0%", "101%"),
        OUTPUT.replace("100.0%", "-1%"),
        OUTPUT.replace("2026-11-01", "2026-02-30"),
        OUTPUT.replace("covered in plan", "remaining in plan"),
        OUTPUT.replace("Credits", "USD"),
        OUTPUT.replace("50.00", "9" * 400),
        OUTPUT + "session/update private tool call\n",
    ],
)
def test_changed_malformed_or_non_quota_output_is_not_a_measurement(text):
    with pytest.raises(ValueError):
        usage.normalize_usage(text)


@pytest.fixture
def synthetic_client(tmp_path, monkeypatch):
    script = tmp_path / "client.py"
    script.write_text(
        """
import json, os, subprocess, sys, time
from pathlib import Path
mode, evidence, *arguments = sys.argv[1:]
evidence = Path(evidence)
if arguments == ['--version']:
    (evidence / 'version-read').touch()
    print('kiro-cli-chat 2.24.0' if mode != 'version' else 'kiro-cli-chat 3.0.0')
    sys.exit(0)
name = arguments[arguments.index('--agent') + 1]
profile = json.loads((Path('.kiro/agents') / (name + '.json')).read_text())
(evidence / 'request.json').write_text(json.dumps({
    'arguments': arguments, 'cwd': str(Path.cwd()), 'profile': profile,
    'no_auto_update': os.getenv('KIRO_NO_AUTO_UPDATE'), 'stdin': sys.stdin.read(),
}))
if mode in ('hang', 'child'):
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
    (evidence / 'child.pid').write_text(str(child.pid))
if mode == 'hang':
    time.sleep(30)
if mode == 'oversized':
    print('x' * 65537, flush=True)
elif mode == 'invalid':
    print('private-native-error')
else:
    text = ('Estimated Usage | resets on 2026-11-01 | KIRO FREE\\n'
            'Credits (50.00 of 50 covered in plan), 100.0%\\n'
            'Manage your plan at https://app.kiro.dev/account/usage\\n')
    sys.stdout.buffer.write(text.encode())
if mode == 'failed':
    sys.exit(1)
""",
        encoding="utf-8",
    )
    original = subprocess.Popen
    processes = []
    monkeypatch.setattr(usage, "external_agent_command", lambda method: "synthetic-kiro")

    def run(mode="success", timeout=3):
        def start(command, **kwargs):
            process = original(
                [sys.executable, "-u", str(script), mode, str(tmp_path), *command[1:]],
                **kwargs,
            )
            processes.append(process)
            return process

        monkeypatch.setattr(usage.subprocess, "Popen", start)
        return usage.read_kiro_allowance(timeout_seconds=timeout)

    yield run, processes
    for process in processes:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=2)


def test_verified_profile_engine_working_directory_and_stdin_isolate_quota(
    synthetic_client, tmp_path
):
    run, processes = synthetic_client
    report = run()
    assert report["status"] == "available" and report["observed_at_utc"]
    assert report["cleanup_verified"]
    request = json.loads((tmp_path / "request.json").read_text())
    profile = request["profile"]
    assert profile["tools"] == profile["allowedTools"] == profile["resources"] == []
    assert profile["hooks"] == profile["mcpServers"] == {}
    assert profile["includeMcpJson"] is False and profile["prompt"] == ""
    assert request["arguments"] == [
        "chat",
        "--v2",
        "--agent",
        profile["name"],
        "--no-interactive",
        "--trust-tools=",
        "/usage",
    ]
    assert request["stdin"] == "" and request["no_auto_update"] == "1"
    assert not Path(request["cwd"]).exists()
    assert all(p.poll() is not None and p.stdin.closed and p.stdout.closed for p in processes)


def test_unverified_version_does_not_start_any_session(synthetic_client, tmp_path):
    run, processes = synthetic_client
    report = run("version")
    assert report["reason"] == "client_version_unverified"
    assert report["windows"] == [] and report["observed_at_utc"] is None
    assert len(processes) == 1 and not (tmp_path / "request.json").exists()


@pytest.mark.parametrize("mode", ["invalid", "oversized", "failed", "hang"])
def test_unknown_responses_and_deadlines_are_redacted_and_cleaned(synthetic_client, mode):
    run, processes = synthetic_client
    start = time.monotonic()
    report = run(mode, timeout=0.6 if mode == "hang" else 3)
    assert time.monotonic() - start < 5
    assert report["status"] == "unknown" and report["cleanup_verified"]
    assert report["windows"] == [] and report["observed_at_utc"] is None
    assert "private" not in json.dumps(report)
    assert all(p.poll() is not None for p in processes)


def test_quota_cleanup_includes_descendants(synthetic_client, tmp_path):
    run, _ = synthetic_client
    report = run("child", timeout=1)
    # A descendant inheriting stdout can hold EOF open; timeout must still own it.
    assert report["cleanup_verified"]
    pid = int((tmp_path / "child.pid").read_text())
    identity = process_identity(pid)
    if os.name != "nt" and identity is not None:
        assert Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] == "Z"
    else:
        assert identity is None


def test_temp_override_inside_repository_refuses_before_native_launch(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    original = usage.tempfile.TemporaryDirectory
    monkeypatch.setattr(
        usage.tempfile, "TemporaryDirectory", lambda **kw: original(dir=tmp_path, **kw)
    )
    monkeypatch.setattr(usage, "external_agent_command", lambda method: "must-not-start")
    monkeypatch.setattr(usage.subprocess, "Popen", lambda *a, **kw: pytest.fail("unsafe launch"))
    report = usage.read_kiro_allowance()
    assert report["reason"] == "isolation_unverified" and report["windows"] == []


@pytest.mark.parametrize("setup_seconds", [4, 15, 16])
def test_profile_setup_consumes_the_shared_observation_deadline(monkeypatch, setup_seconds):
    clock = [100.0]
    monkeypatch.setattr(usage.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(usage, "external_agent_command", lambda method: "synthetic-kiro")
    original = usage.tempfile.TemporaryDirectory

    def prepare(**kwargs):
        clock[0] += setup_seconds
        return original(**kwargs)

    monkeypatch.setattr(usage.tempfile, "TemporaryDirectory", prepare)
    calls = []

    def observe(command, **kwargs):
        report = {
            "status": "unknown",
            "source": usage.SOURCE,
            "reason": "client_unavailable",
            "windows": [],
            "observed_at_utc": None,
            "cleanup_verified": True,
        }
        if command:
            calls.append((command, kwargs["timeout_seconds"]))
            # A bounded version read consumes its remaining budget, not a fresh one.
            clock[0] += kwargs["timeout_seconds"]
            report["reason"] = "timeout"
        return report

    monkeypatch.setattr(usage, "read_native_account_usage", observe)
    report = usage.read_kiro_allowance(timeout_seconds=15)
    assert calls == ([(("synthetic-kiro", "--version"), 11)] if setup_seconds == 4 else [])
    assert clock[0] <= 116
    assert report["status"] == "unknown" and report["windows"] == []
    assert report["reason"] == ("client_version_unverified" if setup_seconds == 4 else "timeout")


@pytest.mark.parametrize("timeout", [True, 0, -1, 121, float("nan"), float("inf")])
def test_invalid_timeout_refuses_before_process_or_directory_creation(monkeypatch, timeout):
    monkeypatch.setattr(usage.subprocess, "Popen", lambda *a, **kw: pytest.fail("must not start"))
    monkeypatch.setattr(
        usage.tempfile, "TemporaryDirectory", lambda **kw: pytest.fail("must not create")
    )
    with pytest.raises(ValueError):
        usage.read_kiro_allowance(timeout_seconds=timeout)


def test_dispatch_only_admits_kiro_subscription_billing(monkeypatch):
    from ai_orchestrator import (
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
    monkeypatch.setattr(
        usage, "read_kiro_allowance", lambda **kw: calls.append(kw) or {"status": "unknown"}
    )
    target = replace(
        plan.target,
        access_method=usage.AccessMethod.KIRO_CLI,
        billing_source=BillingSource.KIRO_SUBSCRIPTION_ALLOWANCE,
        timeout_seconds=2,
    )
    assert account_usage.read_execution_allowance(target) == {"status": "unknown"}
    assert calls == [{"timeout_seconds": 2}]
    assert (
        account_usage.read_execution_allowance(
            replace(target, billing_source=BillingSource.OPENAI_API_BILLING)
        )
        is None
    )
