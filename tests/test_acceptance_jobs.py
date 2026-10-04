"""Offline contract, refusal, effect and retained ownership tests for D3."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pytest
from ai_agent.contracts import ToolCall
from ai_agent.tools import EditFileTool, ReadFileTool, ToolContext
from ai_orchestrator.scheduling import ScheduledTaskStatus as Status
from ai_provider import acceptance_runtime as runtime
from ai_provider import native_admission
from ai_provider.acceptance_harness import (
    PROTECTED,
    SOURCE,
    FixtureTool,
    run_fixture,
    validate_fixture,
)
from ai_provider.acceptance_jobs import (
    AcceptanceJob,
    AcceptanceJobStore,
    artifact_directory,
    endpoint,
    execute_sequence,
    main,
    validate_route,
)
from ai_provider.acceptance_processes import OwnedChild, process_identity, verify_runtime_owner
from ai_provider.config import BackendConfig
from ai_provider.contracts import (
    AIMessage,
    AIRequest,
    AIResponse,
    AIToolCall,
    BackendInfo,
    BackendLocation,
    MessageRole,
)


@pytest.fixture
def job(tmp_path: Path) -> AcceptanceJob:
    root = Path(__file__).resolve().parents[1]
    catalog = tmp_path / "packages/ai_orchestrator/examples"
    catalog.mkdir(parents=True)
    (catalog / "model_catalog.toml").write_bytes(
        (root / "packages/ai_orchestrator/examples/model_catalog.toml").read_bytes()
    )
    evidence = native_admission.NATIVE_TOOL_EVIDENCE[0]
    return AcceptanceJob(
        1,
        "fixture-job",
        "native_coding_tools_v1",
        1,
        str(tmp_path),
        "ollama-gpt-oss-20b",
        evidence.model,
        evidence.runtime_version,
        evidence.model_digest,
        1,
        "http://127.0.0.1:19473",
        60,
        10,
        8192,
        512,
        4,
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", True),
        ("harness_revision", 2),
        ("native_contract_version", 2),
        ("context_tokens", True),
        ("output_tokens", 0),
        ("max_iterations", 5),
        ("required_seconds", float("nan")),
        ("request_timeout_seconds", float("inf")),
        ("required_seconds", -1),
        ("model", "unknown"),
        ("runtime_version", "changed"),
        ("model_digest", "changed"),
        ("repo_root", "."),
        ("job_kind", "shell"),
    ],
)
def test_strict_payload(job: AcceptanceJob, field: str, value: Any) -> None:
    with pytest.raises(ValueError):
        replace(job, **{field: value})


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:1234",
        "https://127.0.0.1:1234",
        "http://192.0.2.1:1234",
        "http://user:secret@127.0.0.1:1234",
        "http://127.0.0.1",
        "http://127.0.0.1:0",
        "http://127.0.0.1:1234/path",
        "http://127.0.0.1:1234?x=y",
    ],
)
def test_endpoint_refusals(url: str) -> None:
    with pytest.raises(ValueError):
        endpoint(url)


def test_definition_unknown_missing_fields_and_roundtrip(job: AcceptanceJob) -> None:
    assert AcceptanceJob.from_json(job.to_json()) == job
    for payload in ({**asdict(job), "command": "anything"}, {}, []):
        with pytest.raises(ValueError):
            AcceptanceJob.from_json(json.dumps(payload))


def test_route_and_active_contract_invalidation(job: AcceptanceJob, monkeypatch) -> None:
    for changed in (replace(job, route_id="unknown"), replace(job, context_tokens=999999)):
        with pytest.raises(ValueError):
            validate_route(changed)
    monkeypatch.setattr(native_admission, "NATIVE_CONTRACT_VERSION", 2)
    with pytest.raises(ValueError, match="stale"):
        validate_route(job)


def test_additive_storage_immutable_definition_and_restart(
    job: AcceptanceJob, tmp_path: Path
) -> None:
    store = AcceptanceJobStore(tmp_path / "jobs.sqlite")
    store.initialize()
    with store._connect() as connection:
        before = dict(connection.execute("SELECT name,sql FROM sqlite_master WHERE type='table'"))
        connection.execute("CREATE TABLE unrelated_owner_data (value TEXT)")
        connection.execute("INSERT INTO unrelated_owner_data VALUES ('preserve')")
    store.plan(job)
    with pytest.raises(sqlite3.IntegrityError):
        store.plan(job)
    store.transition(job.task_id, Status.PLANNED, Status.RUNNING)
    restarted = AcceptanceJobStore(store.path)
    assert restarted.get(job.task_id).status is Status.RUNNING
    with pytest.raises(ValueError):
        restarted.transition(job.task_id, Status.PLANNED, Status.RUNNING)
    with store._connect() as connection:
        after = dict(connection.execute("SELECT name,sql FROM sqlite_master WHERE type='table'"))
        assert all(after[name] == sql for name, sql in before.items())
        assert (
            connection.execute("SELECT value FROM unrelated_owner_data").fetchone()[0] == "preserve"
        )
        connection.execute("UPDATE scheduled_acceptance_tasks SET definition_sha256='tampered'")
    with pytest.raises(ValueError, match="changed"):
        restarted.list_jobs()


def test_plan_and_list_never_start_runtime(job: AcceptanceJob, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(runtime, "run_acceptance_job", lambda *_: pytest.fail("runtime started"))
    definition = tmp_path / "definition.json"
    definition.write_text(job.to_json())
    args = ["--database", str(tmp_path / "jobs.sqlite")]
    assert main([*args, "plan", "--definition", str(definition)]) == 0
    assert main([*args, "list"]) == 0
    assert not (tmp_path / "artifacts").exists()
    with pytest.raises(SystemExit):
        main([*args, "run", job.task_id, "--available-minutes", "2"])


@pytest.mark.parametrize(
    "start,compute,window", [(False, True, 120), (True, False, 120), (True, True, 30)]
)
def test_window_refusal_leaves_planned(
    job: AcceptanceJob, tmp_path: Path, start, compute, window
) -> None:
    store = AcceptanceJobStore(tmp_path / "jobs.sqlite")
    store.plan(job)
    with pytest.raises(ValueError):
        execute_sequence(
            store,
            [job.task_id],
            explicitly_started=start,
            local_compute_available=compute,
            available_seconds=window,
            runner=lambda *a, **k: pytest.fail("refused runner called"),
        )
    assert store.get(job.task_id).status is Status.PLANNED


@pytest.mark.parametrize("passed,cleanup", [(False, True), (True, False), (False, False)])
def test_failure_or_cleanup_uncertainty_stops_sequence(
    job: AcceptanceJob, tmp_path: Path, passed, cleanup
) -> None:
    store = AcceptanceJobStore(tmp_path / "jobs.sqlite")
    second = replace(job, task_id="second")
    store.plan(job)
    store.plan(second)
    calls = []

    def runner(selected, *args, **kwargs):
        calls.append(selected.task_id)
        return {"passed": passed, "cleanup_verified": cleanup}

    with pytest.raises(ValueError, match="sequence stopped"):
        execute_sequence(
            store,
            [job.task_id, second.task_id],
            explicitly_started=True,
            local_compute_available=True,
            available_seconds=120,
            runner=runner,
        )
    assert calls == [job.task_id]
    assert store.get(job.task_id).status is Status.FAILED
    assert store.get(second.task_id).status is Status.PLANNED


def test_exception_keeps_effect_receipts_and_marks_failed(
    job: AcceptanceJob, tmp_path: Path
) -> None:
    store = AcceptanceJobStore(tmp_path / "jobs.sqlite")
    store.plan(job)

    def runner(selected, storage, *args, **kwargs):
        storage.receipt(selected.task_id, {"stage": "effect_observed"})
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        execute_sequence(
            store,
            [job.task_id],
            explicitly_started=True,
            local_compute_available=True,
            available_seconds=120,
            runner=runner,
        )
    assert store.get(job.task_id).status is Status.FAILED
    with store._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM acceptance_receipts").fetchone()[0] == 1


def make_fixture(path: Path) -> None:
    path.mkdir()
    for name, content in {**PROTECTED, "source.py": SOURCE}.items():
        (path / name).write_text(content, encoding="utf-8")


@pytest.mark.parametrize(
    "target", ["../outside.py", "test_source.py", "sentinel.txt", "AGENTS.md", "C:/outside.py"]
)
def test_fixture_refuses_edits_outside_source(tmp_path: Path, target: str) -> None:
    fixture = tmp_path / "fixture"
    make_fixture(fixture)
    receipts = []
    result = FixtureTool(EditFileTool(), fixture, receipts).run(
        ToolCall("edit_file", {"path": target, "new_text": "bad"}, call_id="denied"),
        ToolContext(fixture),
    )
    assert result.is_error and receipts[0]["is_error"]
    assert (fixture / "source.py").read_text() == SOURCE


def test_hardlink_refusal_retains_error_receipt(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture"
    make_fixture(fixture)
    os.link(fixture / "source.py", tmp_path / "outside.py")
    receipts = []
    result = FixtureTool(ReadFileTool(), fixture, receipts).run(
        ToolCall("read_file", {"path": "source.py"}, call_id="read"), ToolContext(fixture)
    )
    assert result.is_error and receipts[0]["source_sha256"] is None


@pytest.mark.skipif(os.name != "nt", reason="v1 retained process ownership requires Windows")
def test_fixed_validator_baseline_success_and_malicious_refusal(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture"
    make_fixture(fixture)
    receipts = []
    assert (
        validate_fixture(fixture, tmp_path, "baseline", time.monotonic() + 10, receipts.append) == 1
    )
    (fixture / "source.py").write_text("def add(a, b):\n    return a + b\n")
    assert (
        validate_fixture(fixture, tmp_path, "correct", time.monotonic() + 10, receipts.append) == 0
    )
    marker = tmp_path / "escaped.txt"
    (fixture / "source.py").write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\n")
    assert (
        validate_fixture(fixture, tmp_path, "malicious", time.monotonic() + 10, receipts.append)
        != 0
    )
    assert not marker.exists()
    assert all(item["verified"] for item in receipts if item.get("stage") == "validator_cleanup")


class FakeClient:
    def __init__(
        self,
        config: BackendConfig,
        actions: list[tuple[AIToolCall, ...]],
        requests: list[AIRequest],
    ):
        self.backend = BackendInfo("ollama", config.model, BackendLocation.LOCAL)
        self.actions, self.requests = actions, requests

    def complete(self, request: AIRequest) -> AIResponse:
        self.requests.append(request)
        calls = self.actions.pop(0)
        return AIResponse(
            AIMessage(MessageRole.ASSISTANT, "", tool_calls=calls), self.backend, tool_calls=calls
        )

    def stream(self, request: AIRequest):
        raise NotImplementedError


@pytest.mark.parametrize("actual", [True, False])
def test_fixture_requires_real_tools_preserves_instructions_and_durable_receipts(
    job: AcceptanceJob, tmp_path: Path, monkeypatch, actual
) -> None:
    monkeypatch.setattr(
        native_admission,
        "installed_native_identity",
        lambda config: (job.model_digest, job.runtime_version),
    )
    actions = (
        [
            (AIToolCall("read", "read_file", {"path": "source.py"}),),
            (
                AIToolCall(
                    "edit",
                    "edit_file",
                    {"path": "source.py", "old_text": "a - b", "new_text": "a + b"},
                ),
            ),
            (),
        ]
        if actual
        else [()]
    )
    requests = []
    checks = []

    def validator(fixture, artifact, label, deadline, receipt, **kwargs):
        return 1 if label == "baseline" else 0

    result = run_fixture(
        job,
        tmp_path,
        time.monotonic() + 30,
        checks.append,
        client_factory=lambda config: FakeClient(config, actions, requests),
        validator=validator,
    )
    assert result["passed"] is actual
    assert requests and all(
        request.model == job.model and request.max_output_tokens == 512 for request in requests
    )
    assert all(request.messages[0].content == PROTECTED["AGENTS.md"] for request in requests)
    assert checks and result["admission"]
    assert all("estimate" in text for text in result["admission"])
    journal = [
        json.loads(line) for line in (tmp_path / "worker-receipts.jsonl").read_text().splitlines()
    ]
    assert journal == result["receipts"]
    if actual:
        tools = [item for item in journal if "tool" in item]
        assert len(tools) == 2 and tools[0]["source_sha256"] != tools[1]["source_sha256"]


def test_occupied_endpoint_never_starts_or_stops_children(
    job: AcceptanceJob, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(runtime, "port_unused", lambda url: False)
    monkeypatch.setattr(runtime, "OwnedChild", lambda *a, **k: pytest.fail("child started"))
    store = AcceptanceJobStore(tmp_path / "jobs.sqlite")
    store.plan(job)
    result = runtime.run_acceptance_job(job, store, time.monotonic() + 60)
    assert not result["passed"] and result["cleanup_verified"]
    assert "occupied" in result["reason"]
    assert not artifact_directory(job, store.path).exists()


def test_runtime_stale_identity_cleans_only_owned_root(
    job: AcceptanceJob, tmp_path: Path, monkeypatch
) -> None:
    store = AcceptanceJobStore(tmp_path / "jobs.sqlite")
    store.plan(job)
    stopped = []

    class Child:
        def __init__(self, *args, role, receipt, **kwargs):
            assert role == "runtime"
            self.identity = {"role": role, "pid": 123, "birth": "owned"}
            self.process = self
            self.pid = 123
            receipt({"stage": "process_started", **self.identity})

        def stop(self, timeout):
            stopped.append(self.identity)
            return True

    monkeypatch.setattr(runtime, "OwnedChild", Child)
    monkeypatch.setattr(runtime.shutil, "which", lambda _: "existing-ollama")
    monkeypatch.setattr(runtime, "port_unused", lambda _: True)
    monkeypatch.setattr(runtime, "listener_owned", lambda *a, **k: True)
    monkeypatch.setattr(runtime, "verify_runtime_owner", lambda *a, **k: None)
    monkeypatch.setattr(
        runtime, "installed_native_identity", lambda _: ("changed", job.runtime_version)
    )
    result = runtime.run_acceptance_job(job, store, time.monotonic() + 60)
    assert not result["passed"] and result["cleanup_verified"]
    assert "fingerprint changed" in result["reason"]
    assert len(stopped) == 1
    assert (artifact_directory(job, store.path) / "result.json").exists()


def test_pid_reuse_refuses_before_listener_or_request(monkeypatch) -> None:
    from ai_provider import acceptance_processes as processes

    monkeypatch.setattr(processes, "process_identity", lambda pid: "different-birth")
    monkeypatch.setattr(
        processes, "listener_owned", lambda *a, **k: pytest.fail("listener inspected")
    )
    with pytest.raises(ValueError, match="ownership"):
        verify_runtime_owner(
            "http://127.0.0.1:19473", {"role": "runtime", "pid": 123, "birth": "original"}
        )


@pytest.mark.skipif(os.name != "nt", reason="Windows retained-job cleanup contract")
def test_owned_job_cleans_descendant_after_root_exits(tmp_path: Path) -> None:
    pid_file = tmp_path / "child.pid"
    gate = tmp_path / "gate"
    script = tmp_path / "owned_dummy.py"
    script.write_text(
        "import subprocess, sys, time\nfrom pathlib import Path\n"
        f"while not Path({str(gate)!r}).exists(): time.sleep(.01)\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"Path({str(pid_file)!r}).write_text(str(child.pid))\n"
    )
    receipts = []
    owned = OwnedChild(
        [sys.executable, str(script)],
        cwd=tmp_path,
        env=dict(os.environ),
        log=tmp_path / "dummy.log",
        role="worker",
        receipt=receipts.append,
    )
    try:
        gate.touch()
        assert owned.wait(time.monotonic() + 10) == 0
        child_pid = int(pid_file.read_text())
        assert process_identity(child_pid) is not None
    finally:
        assert owned.stop(5)
    assert process_identity(child_pid) is None


def test_worker_environment_excludes_provider_credentials(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "do-not-forward")
    monkeypatch.setenv("OLLAMA_HOST", "http://remote.invalid")
    env = runtime.worker_environment()
    assert "OPENAI_API_KEY" not in env and "OLLAMA_HOST" not in env
    assert "PYTHONPATH" in env


@pytest.mark.skipif(os.name != "nt", reason="Windows supervisor startup contract")
def test_startup_exception_cannot_claim_verified_cleanup(
    job: AcceptanceJob, tmp_path: Path, monkeypatch
) -> None:
    store = AcceptanceJobStore(tmp_path / "jobs.sqlite")
    store.plan(job)
    monkeypatch.setattr(runtime, "port_unused", lambda _: True)
    monkeypatch.setattr(runtime.shutil, "which", lambda _: "existing-ollama")

    def failed_child(*args, **kwargs):
        raise OSError("ownership setup failed")

    monkeypatch.setattr(runtime, "OwnedChild", failed_child)
    result = runtime.run_acceptance_job(job, store, time.monotonic() + 60)
    assert not result["passed"] and not result["cleanup_verified"]


@pytest.mark.parametrize(
    "mode", ["success", "missing_receipts", "timeout", "interrupt", "cleanup_uncertain"]
)
def test_supervisor_result_and_interrupted_journal(
    job: AcceptanceJob, tmp_path: Path, monkeypatch, mode
) -> None:
    import hashlib

    store = AcceptanceJobStore(tmp_path / "jobs.sqlite")
    store.plan(job)
    stopped = []

    class Child:
        def __init__(self, *args, role, receipt, cwd, **kwargs):
            self.role, self.cwd = role, cwd
            self.identity = {"role": role, "pid": 123, "birth": "owned"}
            self.process = self
            self.pid = 123
            receipt({"stage": "process_started", **self.identity})

        def wait(self, deadline, clock):
            assert (self.cwd / "worker-receipt.json").exists()
            make_fixture(self.cwd / "fixture")
            source = self.cwd / "fixture/source.py"
            read = {
                "tool": "read_file",
                "path": "source.py",
                "is_error": False,
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            }
            source.write_text("def add(a, b):\n    return a + b\n")
            edit = {
                "tool": "edit_file",
                "path": "source.py",
                "is_error": False,
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            }
            (self.cwd / "worker-receipts.jsonl").write_text(
                json.dumps(read) + "\n" + json.dumps(edit) + "\n"
            )
            if mode == "timeout":
                raise TimeoutError("worker budget")
            if mode == "interrupt":
                raise KeyboardInterrupt
            runtime.write_json(
                self.cwd / "worker-result.json",
                {
                    "schema_version": 1,
                    "task_id": job.task_id,
                    "passed": True,
                    "baseline_exit_code": 1,
                    "validation_exit_code": 0,
                    "receipts": [] if mode == "missing_receipts" else [read, edit],
                },
            )
            return 0

        def stop(self, timeout):
            stopped.append(self.role)
            return mode != "cleanup_uncertain" or self.role != "worker"

    monkeypatch.setattr(runtime, "OwnedChild", Child)
    monkeypatch.setattr(runtime.shutil, "which", lambda _: "existing-ollama")
    monkeypatch.setattr(runtime, "port_unused", lambda _: True)
    monkeypatch.setattr(runtime, "listener_owned", lambda *a, **k: True)
    monkeypatch.setattr(runtime, "verify_runtime_owner", lambda *a, **k: None)
    monkeypatch.setattr(
        runtime, "installed_native_identity", lambda _: (job.model_digest, job.runtime_version)
    )
    if mode == "interrupt":
        with pytest.raises(KeyboardInterrupt):
            runtime.run_acceptance_job(job, store, time.monotonic() + 60)
        result = json.loads((artifact_directory(job, store.path) / "result.json").read_text())
    else:
        result = runtime.run_acceptance_job(job, store, time.monotonic() + 60)
    assert result["passed"] is (mode == "success")
    assert stopped == ["worker", "runtime"]
    with store._connect() as connection:
        receipts = [
            json.loads(row[0])
            for row in connection.execute("SELECT receipt_json FROM acceptance_receipts")
        ]
    assert {item.get("tool") for item in receipts if "tool" in item} == {"read_file", "edit_file"}


def test_deadline_expiry_fails_even_successful_result(job: AcceptanceJob, tmp_path: Path) -> None:
    store = AcceptanceJobStore(tmp_path / "jobs.sqlite")
    store.plan(job)
    ticks = [0.0]

    def runner(*args, **kwargs):
        ticks[0] = 121
        return {"passed": True, "cleanup_verified": True}

    with pytest.raises(ValueError):
        execute_sequence(
            store,
            [job.task_id],
            explicitly_started=True,
            local_compute_available=True,
            available_seconds=120,
            clock=lambda: ticks[0],
            runner=runner,
        )
    assert store.get(job.task_id).status is Status.FAILED


def test_edit_before_read_is_refused(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture"
    make_fixture(fixture)
    receipts = []
    result = FixtureTool(EditFileTool(), fixture, receipts).run(
        ToolCall("edit_file", {"path": "source.py", "old_text": "a - b", "new_text": "a + b"}),
        ToolContext(fixture),
    )
    assert result.is_error and "Read source.py" in result.output
