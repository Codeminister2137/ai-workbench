"""Foreground ownership, deadlines and receipts for the fixed local worker."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ai_provider.acceptance_harness import check_plain_path, check_protected
from ai_provider.acceptance_jobs import (
    CLEANUP_SECONDS,
    AcceptanceJob,
    AcceptanceJobStore,
    artifact_directory,
    validate_route,
)
from ai_provider.acceptance_processes import (
    OwnedChild,
    listener_owned,
    port_unused,
    remaining,
    verify_runtime_owner,
)
from ai_provider.config import BackendConfig, ProviderKind
from ai_provider.native_admission import installed_native_identity


def worker_environment() -> dict[str, str]:
    """Pass OS necessities and trusted package locations, never provider secrets."""
    import ai_agent
    import ai_orchestrator

    import ai_provider

    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper()
        in {
            "PATH",
            "SYSTEMROOT",
            "WINDIR",
            "USERPROFILE",
            "HOME",
            "LOCALAPPDATA",
            "APPDATA",
            "TEMP",
            "TMP",
        }
    }
    environment["PYTHONPATH"] = os.pathsep.join(
        str(Path(str(module.__file__)).resolve().parents[1])
        for module in (ai_provider, ai_agent, ai_orchestrator)
    )
    environment["PYTHONUNBUFFERED"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    return environment


def write_json(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8") as output:
        json.dump(value, output, sort_keys=True, allow_nan=False)


def run_acceptance_job(
    job: AcceptanceJob,
    store: AcceptanceJobStore,
    deadline: float,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Called only after explicit window admission and a durable running claim."""
    active_deadline = deadline - CLEANUP_SECONDS
    result: dict[str, Any] = {
        "schema_version": 1,
        "task_id": job.task_id,
        "passed": False,
        "cleanup_verified": False,
        "next_action": "Inspect preserved fixture/process receipts before planning a new job",
    }
    children: list[OwnedChild] = []
    artifact = artifact_directory(job, store.path)
    artifact_created = False
    started_runtime = False
    launch_in_progress = False
    cleanup: list[dict[str, Any]] = []
    interrupted: BaseException | None = None
    try:
        if os.name != "nt":
            raise ValueError("Harness v1 requires Windows retained process-tree ownership")
        validate_route(job)
        remaining(active_deadline, clock)
        check_plain_path(artifact)
        if not port_unused(job.runtime_base_url):
            raise ValueError("Selected runtime endpoint is occupied; existing server is untouched")
        executable = shutil.which("ollama")
        if not executable:
            raise ValueError(
                "Existing Ollama executable is unavailable; no install/download performed"
            )
        artifact.mkdir(parents=True, exist_ok=False)
        artifact_created = True
        write_json(artifact / "definition.json", json.loads(job.to_json()))
        environment = worker_environment()
        environment.update(
            {
                "OLLAMA_HOST": job.runtime_base_url.rstrip("/"),
                "OLLAMA_CONTEXT_LENGTH": str(job.context_tokens),
                "OLLAMA_MAX_LOADED_MODELS": "1",
                "OLLAMA_NUM_PARALLEL": "1",
            }
        )

        def record(value: dict[str, Any]) -> None:
            store.receipt(job.task_id, value)

        launch_in_progress = True
        runtime = OwnedChild(
            [executable, "serve"],
            cwd=artifact,
            env=environment,
            log=artifact / "runtime.log",
            role="runtime",
            receipt=record,
        )
        children.append(runtime)
        launch_in_progress = False
        started_runtime = True
        write_json(artifact / "runtime-receipt.json", runtime.identity)
        while not listener_owned(
            job.runtime_base_url,
            runtime.process.pid,
            timeout=min(2, remaining(active_deadline, clock)),
        ):
            if runtime.process.poll() is not None:
                raise ValueError("Owned runtime exited during startup")
            # Binding can precede listening. Wait within the admitted budget;
            # no HTTP is allowed until exact listener ownership is established.
            time.sleep(min(0.05, remaining(active_deadline, clock)))
        verify_runtime_owner(
            job.runtime_base_url,
            runtime.identity,
            timeout=min(2, remaining(active_deadline, clock)),
        )
        identity = installed_native_identity(
            BackendConfig(
                ProviderKind.OLLAMA,
                job.model,
                job.runtime_base_url,
                timeout_seconds=min(2, remaining(active_deadline, clock)),
            )
        )
        if identity != (job.model_digest, job.runtime_version):
            raise ValueError("Planned runtime/model fingerprint changed; no inference performed")
        launch_in_progress = True
        worker = OwnedChild(
            [
                sys.executable,
                "-m",
                "ai_provider.acceptance_worker",
                "--definition",
                str(artifact / "definition.json"),
                "--runtime-receipt",
                str(artifact / "runtime-receipt.json"),
                "--start-receipt",
                str(artifact / "worker-receipt.json"),
                "--deadline",
                str(active_deadline),
            ],
            cwd=artifact,
            env=worker_environment(),
            log=artifact / "worker.log",
            role="worker",
            receipt=record,
        )
        children.append(worker)
        launch_in_progress = False
        write_json(artifact / "worker-receipt.json", worker.identity)
        code = worker.wait(active_deadline, clock)
        result["worker_exit_code"] = code
        with (artifact / "worker-result.json").open(encoding="utf-8") as output:
            payload = output.read(262145)
        if len(payload) > 262144:
            raise ValueError("Worker result exceeded the fixed receipt bound")
        report = json.loads(payload)
        if (
            not isinstance(report, dict)
            or type(report.get("schema_version")) is not int
            or report.get("schema_version") != 1
            or report.get("task_id") != job.task_id
        ):
            raise ValueError("Worker result identity/revision mismatch")
        check_protected(artifact / "fixture")
        events = report.get("receipts")
        if not isinstance(events, list) or not all(isinstance(item, dict) for item in events):
            raise ValueError("Missing observed worker receipts")
        tools = [item for item in events if "tool" in item]
        read_index = next(
            (
                i
                for i, item in enumerate(tools)
                if item.get("tool") == "read_file"
                and item.get("path") == "source.py"
                and item.get("is_error") is False
            ),
            None,
        )
        edit_index = next(
            (
                i
                for i, item in enumerate(tools)
                if item.get("tool") == "edit_file"
                and item.get("path") == "source.py"
                and item.get("is_error") is False
            ),
            None,
        )
        if (
            read_index is None
            or edit_index is None
            or read_index >= edit_index
            or any(item.get("is_error") is not False for item in tools)
            or tools[-1].get("source_sha256")
            != hashlib.sha256((artifact / "fixture/source.py").read_bytes()).hexdigest()
        ):
            raise ValueError(
                "Required source read/edit effect receipts are missing or inconsistent"
            )
        result["worker_result"] = report
        result["passed"] = (
            code == 0
            and report.get("passed") is True
            and report.get("baseline_exit_code") == 1
            and report.get("validation_exit_code") == 0
        )
        remaining(active_deadline, clock)
    except BaseException as exc:
        result["passed"] = False
        result["reason"] = f"{type(exc).__name__}: {exc}"[:2000]
        if not isinstance(exc, Exception):
            interrupted = exc
    finally:
        for child in reversed(children):
            try:
                verified = child.stop(max(0.05, min(5, deadline - clock())))
                entry = {"stage": "process_cleanup", "verified": verified, **child.identity}
            except BaseException as exc:
                if not isinstance(exc, Exception):
                    interrupted = exc
                entry = {
                    "stage": "process_cleanup",
                    "verified": False,
                    "reason": type(exc).__name__,
                    **child.identity,
                }
            cleanup.append(entry)
            try:
                store.receipt(job.task_id, entry)
            except Exception:
                entry["verified"] = False
        port_clear = not started_runtime or port_unused(job.runtime_base_url)
        result["cleanup"] = cleanup
        result["listener_absent"] = port_clear
        result["cleanup_verified"] = (
            not launch_in_progress
            and all(item["verified"] for item in cleanup)
            and port_clear
            and clock() <= deadline
        )
        result["passed"] = result["passed"] and result["cleanup_verified"]
        if artifact_created:
            journal = artifact / "worker-receipts.jsonl"
            if journal.exists():
                try:
                    with journal.open(encoding="utf-8") as source:
                        payload = source.read(262145)
                    if len(payload) > 262144:
                        raise ValueError("Worker receipt journal exceeded its fixed bound")
                    for line in payload.splitlines():
                        store.receipt(job.task_id, json.loads(line))
                except (OSError, ValueError, sqlite3.Error):
                    result["passed"] = False
                    result["receipt_import_verified"] = False
            write_json(artifact / "result.json", result)
    if interrupted is not None:
        raise interrupted
    return result
