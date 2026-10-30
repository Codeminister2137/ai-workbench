"""Unattended supervised development driver with a fixed deadline.

Developer tooling only. Runs a prepared queue of bounded objectives:

- ``implement``: public Operator work through the Baseten supervisor/implementer
  launcher, gated by the existing isolated Modal full-suite validator and
  committed on one review branch. Nothing is pushed.
- ``propose``: private Workbench work sent only to Baseten, written as
  review-ready proposals under the artifact directory. No repository writes and
  no execution of model-authored code.

The host owns the queue, deadlines, budgets and commits. Models cannot add
targets, change checks or extend bounds. A missing or failing phase is recorded
and skipped; nothing is retried blindly.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts/baseten-supervised-develop.py"
PYTHON = ROOT / ".venv/Scripts/python.exe"
VALIDATOR_TEMPLATE = ROOT / "artifacts/meta-loop-final-candidate-validation-20261030/modal-exec.py"
CANCEL = ROOT / "cancel-sleep.cmd"
CLOSE = ROOT / "scripts/workstation-sleep.ps1"

# Sensible defaults: Baseten event model.
try:
    sys.path.insert(0, str(ROOT / "packages/ai_provider/src"))
    from ai_provider.adapters.baseten import BASETEN_HACKATHON_MODEL as _DEFAULT_MODEL

    DEFAULT_SUPERVISOR_MODEL = _DEFAULT_MODEL
    DEFAULT_IMPLEMENTER_MODEL = _DEFAULT_MODEL
except Exception:
    DEFAULT_SUPERVISOR_MODEL = "baseten-event-model"
    DEFAULT_IMPLEMENTER_MODEL = "baseten-event-model"


def now() -> str:
    return datetime.now(UTC).isoformat()


def record(path: Path, entry: dict) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(entry, ensure_ascii=False) + "\n")


def run(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 600,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def prepare_phase(phase: Path, worktree: Path, deadline_epoch: float, name: str) -> None:
    phase.mkdir(parents=True, exist_ok=False)
    shutil.copy2(
        ROOT / "artifacts/meta-loop-final-candidate-validation-20261030/run-modal.cjs", phase
    )
    text = VALIDATOR_TEMPLATE.read_text(encoding="utf-8")
    text = text.replace(
        "PHASE = Path("
        "'C:/Users/Jakub/PycharmProjects/AI-projects/artifacts/meta-loop-final-candidate-validation-20261030'"
        ")",
        f"PHASE = Path({str(phase).replace(chr(92), '/')!r})",
    )
    text = text.replace(
        "WORKTREE = Path("
        "'C:/Users/Jakub/PycharmProjects/AI-projects/artifacts/meta-loop-controller-20261030/worktree'"
        ")",
        f"WORKTREE = Path({str(worktree).replace(chr(92), '/')!r})",
    )
    (phase / "modal-exec.py").write_text(text, encoding="utf-8")
    (phase / "checks.txt").write_text(
        "import os\n"
        "os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'\n"
        "os.environ['PYTHONDONTWRITEBYTECODE'] = '1'\n"
        "import pytest\n"
        "raise SystemExit(pytest.main(['/workspace/tests', '-q', '-p', 'no:cacheprovider']))\n",
        encoding="utf-8",
    )
    (phase / "modal-allowance.json").write_text(
        json.dumps(
            {
                "name": name,
                "max_attempts": 1,
                "attempts": 0,
                "reserved_usd": 0.33,
                "expires_epoch": deadline_epoch,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def admission(worktree: Path, task: Path, allowlist: list[str], phase: Path, calls: int) -> str:
    result = run(
        [
            str(PYTHON),
            str(LAUNCHER),
            "--repo-root",
            str(worktree),
            "--task-file",
            str(task),
            *sum((["--file", name] for name in allowlist), []),
            "--phase",
            str(phase),
            "--max-calls",
            str(calls),
            "--check",
        ]
    )
    if result.returncode != 0:
        raise RuntimeError(f"admission refused: {result.stderr[-400:]}")
    return json.loads(result.stdout)["admission_sha256"]


def execute(
    worktree: Path,
    task: Path,
    allowlist: list[str],
    phase: Path,
    calls: int,
    timeout: int = 900,
) -> dict:
    digest = admission(worktree, task, allowlist, phase, calls)
    (phase / "AUTHORIZED").write_text(digest, encoding="utf-8")
    result = run(
        [
            str(PYTHON),
            str(LAUNCHER),
            "--repo-root",
            str(worktree),
            "--task-file",
            str(task),
            *sum((["--file", name] for name in allowlist), []),
            "--phase",
            str(phase),
            "--max-calls",
            str(calls),
        ],
        timeout=max(60, timeout),
    )
    receipt = json.loads((phase / "receipt.json").read_text(encoding="utf-8"))
    return {
        "exit_code": result.returncode,
        "stdout": result.stdout[-800:],
        "stderr": result.stderr[-800:],
        "final": receipt.get("final", {}).get("status"),
        "host_error": receipt.get("host_error"),
        "requests": len(receipt.get("requests", [])),
        "usage": [item.get("usage") for item in receipt.get("requests", [])],
    }


def verify_and_commit(worktree: Path, objective_id: str, branch: str, log: Path) -> dict:
    venv = Path("C:/Users/Jakub/PycharmProjects/remote-ai-operator/.venv/Scripts/python.exe")
    env = os.environ.copy()
    env.update({"PYTHONPATH": str(worktree / "src"), "PYTHONHASHSEED": "0"})
    suite = run(
        [str(venv), "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"],
        cwd=worktree,
        env=env,
        timeout=900,
    )
    suite_tail = (suite.stdout or "").strip().splitlines()[-1:] or ["no output"]
    if suite.returncode != 0:
        run(["git", "-C", str(worktree), "checkout", "--", "."], timeout=120)
        run(["git", "-C", str(worktree), "clean", "-fdq"], timeout=120)
        outcome = {
            "status": "reverted",
            "suite": suite_tail[-1],
        }
    else:
        run(["git", "-C", str(worktree), "add", "-A"], timeout=120)
        commit = run(
            [
                "git",
                "-C",
                str(worktree),
                "commit",
                "-m",
                f"{objective_id}: supervised Baseten slice",
            ],
            timeout=180,
        )
        outcome = {
            "status": "committed" if commit.returncode == 0 else "commit-failed",
            "commit": commit.stdout.strip().splitlines()[:1],
            "suite": suite_tail[-1],
        }
    record(log, {"at": now(), "objective": objective_id, "branch": branch, **outcome})
    return outcome


def propose(
    task: str, files: dict[str, str], out: Path, deadline_epoch: float, mode: str = "rewrite"
) -> dict:
    sys.path.insert(0, str(ROOT / "packages/ai_provider/src"))
    sys.path.insert(0, str(ROOT / "packages/ai_orchestrator/src"))
    from ai_provider.adapters.baseten import (
        BASETEN_BASE_URL,
        BASETEN_HACKATHON_MODEL,
        BasetenChatClient,
    )
    from ai_provider.config import BackendConfig, ProviderKind
    from ai_provider.contracts import AIMessage, AIRequest, MessageRole, PrivacyClass

    class LowReasoningClient(BasetenChatClient):
        def _chat_payload(self, request, *, stream):
            payload = super()._chat_payload(request, stream=stream)
            payload["reasoning_effort"] = "low"
            return payload

    values = [
        line.partition("=")[2].strip().strip("\"'")
        for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines()
        if line.partition("=")[0].strip() == "BASETEN_HACKATHON_API_KEY"
    ]
    if len(values) != 1 or not values[0]:
        raise ValueError("Exactly one Baseten event credential required")
    if time.time() >= deadline_epoch:
        raise ValueError("Deadline reached before proposal request")
    if mode == "append":
        contract = '{"append":{"path":"text to append at the end"}} or {"stop":"reason"}'
    else:
        contract = '{"changes":{"path":"complete UTF-8 file"}} or {"stop":"reason"}'
    prompt = (
        "You are a bounded implementation assistant for a private development repository. "
        f"Return only one JSON object {contract}. "
        "Preserve all existing code and behavior; make the smallest possible change "
        "that satisfies the task. Do not rewrite files from scratch unless the file "
        "does not yet exist. No explanations, no markdown, no shell.\n\nTASK:\n"
        + task
        + "\n\nFILES:\n"
        + "\n".join(f"--- {name} ---\n{text}\n--- end {name} ---" for name, text in files.items())
    )
    client = LowReasoningClient(
        BackendConfig(
            provider=ProviderKind.BASETEN,
            model=BASETEN_HACKATHON_MODEL,
            base_url=BASETEN_BASE_URL,
            api_key=values[0],
            timeout_seconds=240.0,
        )
    )
    request = AIRequest(
        messages=(AIMessage(role=MessageRole.USER, content=prompt),),
        model=BASETEN_HACKATHON_MODEL,
        max_output_tokens=16384,
        privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK,
        metadata={"purpose": "bounded-private-proposal"},
    )
    started = time.perf_counter()
    response = client.complete(request)
    content = response.message.content or ""
    out.mkdir(parents=True, exist_ok=False)
    (out / "raw-response.txt").write_text(content, encoding="utf-8")
    receipt = {
        "at": now(),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "finish_reason": response.finish_reason.value,
        "usage": None
        if response.usage is None
        else {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "total_tokens": response.usage.total_tokens,
        },
        "files": sorted(files),
    }
    start, end = content.find("{"), content.rfind("}")
    proposal = None
    if response.finish_reason.value == "stop" and start >= 0 and end > start:
        try:
            parsed = json.loads(content[start : end + 1])
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            if mode == "append":
                if set(parsed) == {"append"} and isinstance(parsed["append"], dict):
                    if set(parsed["append"]) <= set(files) and all(
                        isinstance(value, str) for value in parsed["append"].values()
                    ):
                        proposal = parsed
            else:
                if set(parsed) == {"changes"} and isinstance(parsed["changes"], dict):
                    if set(parsed["changes"]) <= set(files) and all(
                        isinstance(value, str) for value in parsed["changes"].values()
                    ):
                        proposal = parsed
            if set(parsed) == {"stop"}:
                proposal = parsed
    receipt["valid"] = proposal is not None
    receipt["mode"] = mode
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    if proposal is not None:
        (out / "proposal.json").write_text(json.dumps(proposal, indent=2), encoding="utf-8")
    return receipt


def workbench_implement(
    task: str,
    files: dict[str, str],
    out: Path,
    deadline_epoch: float,
    worktree: Path,
    branch: str,
) -> dict:
    """Single-shot Baseten implementer for private Workbench files.

    Sends the allowlisted files with the task, applies returned changes,
    validates changed Python files with py_compile, and commits on success.
    This is a lightweight partial implementation of remote loop support;
    it does not use a supervisor/implementer loop or Modal validation.
    """
    receipt = propose(task, files, out, deadline_epoch, mode="rewrite")
    if not receipt["valid"]:
        return receipt
    proposal_path = out / "proposal.json"
    if not proposal_path.exists():
        return receipt
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    if set(proposal) != {"changes"}:
        receipt["applied"] = False
        return receipt
    # Apply changes under the Workbench worktree.
    for rel_path, content in proposal["changes"].items():
        target = worktree / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    # Validate changed Python files.
    changed = list(proposal["changes"].keys())
    validation_ok = True
    validation_errors: list[str] = []
    for rel_path in changed:
        if rel_path.endswith(".py"):
            target = worktree / rel_path
            result = run(
                [sys.executable, "-m", "py_compile", str(target)],
                timeout=60,
            )
            if result.returncode != 0:
                validation_ok = False
                validation_errors.append(f"{rel_path}: {result.stderr[-200:]}")
    receipt["applied"] = validation_ok
    receipt["changed"] = changed
    if validation_ok:
        run(["git", "-C", str(worktree), "add", "-A"], timeout=120)
        commit = run(
            ["git", "-C", str(worktree), "commit", "-m", f"{out.name}: supervised Workbench slice"],
            timeout=180,
        )
        receipt["commit"] = commit.stdout.strip().splitlines()[:1]
    else:
        receipt["validation_errors"] = validation_errors
        run(["git", "-C", str(worktree), "checkout", "--", "."], timeout=120)
        run(["git", "-C", str(worktree), "clean", "-fdq"], timeout=120)
    return receipt


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--deadline-utc", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--rolling-sleep", action="store_true", default=False)
    parser.add_argument("--supervisor-model", default=DEFAULT_SUPERVISOR_MODEL)
    parser.add_argument("--implementer-model", default=DEFAULT_IMPLEMENTER_MODEL)
    args = parser.parse_args(argv)

    deadline = datetime.fromisoformat(args.deadline_utc.replace("Z", "+00:00")).astimezone(UTC)
    deadline_epoch = deadline.timestamp()
    queue = json.loads(args.queue.read_text(encoding="utf-8"))
    run_dir = args.run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    log = run_dir / "ledger.jsonl"
    report = run_dir / "report.md"
    stop_file = run_dir / "STOP"
    totals = {"requests": 0, "input_tokens": 0, "output_tokens": 0}
    lines = [f"# Unattended development report - {args.deadline_utc}", ""]
    started = now()
    record(
        log,
        {
            "at": started,
            "kind": "start",
            "deadline_utc": deadline.isoformat(),
            "supervisor_model": args.supervisor_model,
            "implementer_model": args.implementer_model,
        },
    )

    rolling_sleep_started = False
    rolling_receipt = run_dir / "sleep-rolling-receipt.json"
    rolling_cancel = run_dir / "sleep-rolling.cancel"
    if args.rolling_sleep:
        rolling_sleep_started = True
        deadline_str = deadline.isoformat()

        def _rolling_sleep_loop() -> None:
            run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(CLOSE),
                    "-Rolling",
                    "-Sleep",
                    "-SleepAtUtc",
                    deadline_str,
                    "-ProtectedUntilUtc",
                    deadline_str,
                    "-ReceiptPath",
                    str(rolling_receipt),
                    "-CancelPath",
                    str(rolling_cancel),
                ],
                timeout=180,
            )
            while True:
                time.sleep(8 * 60)
                run(
                    [
                        "powershell.exe",
                        "-NoProfile",
                        "-NonInteractive",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-File",
                        str(CLOSE),
                        "-Renew",
                        "-ReceiptPath",
                        str(rolling_receipt),
                    ],
                    timeout=180,
                )

        threading.Thread(target=_rolling_sleep_loop, daemon=True).start()

    def watch() -> None:
        while time.time() < deadline_epoch - 300:
            time.sleep(10)
        stop_file.write_text("deadline", encoding="utf-8")
        record(log, {"at": now(), "kind": "deadline-stop-written"})

    threading.Thread(target=watch, daemon=True).start()

    def expired() -> bool:
        return time.time() >= deadline_epoch - 300 or stop_file.exists()

    try:
        for item in queue:
            if expired():
                lines.append(f"- `{item['id']}`: skipped, deadline or stop reached")
                record(log, {"at": now(), "kind": "skipped", "objective": item["id"]})
                continue
            record(log, {"at": now(), "kind": "objective-start", "objective": item["id"]})
            try:
                if item["kind"] == "implement":
                    worktree = Path(item["worktree"]).resolve()
                    # Always start from a clean public worktree so stale model edits do not
                    # leak between objectives or into the next admission snapshot.
                    run(["git", "-C", str(worktree), "checkout", "--", "."], timeout=120)
                    run(["git", "-C", str(worktree), "clean", "-fdq"], timeout=120)
                    phase = (run_dir / "phases" / item["id"]).resolve()
                    prepare_phase(phase, worktree, deadline_epoch, item["id"])
                    task = phase / "task.txt"
                    task.write_text(item["objective"], encoding="utf-8")
                    result = execute(
                        worktree,
                        task,
                        item["allowlist"],
                        phase,
                        item["max_calls"],
                        timeout=int(max(60, min(900, deadline_epoch - time.time() - 300))),
                    )
                    totals["requests"] += result["requests"]
                    for usage in result["usage"]:
                        if usage:
                            totals["input_tokens"] += usage.get("input_tokens", 0) or 0
                            totals["output_tokens"] += usage.get("output_tokens", 0) or 0
                    detail = f"status={result['final']} requests={result['requests']}"
                    if result["final"] == "accepted":
                        commit = verify_and_commit(worktree, item["id"], args.branch, log)
                        detail += f" local={commit['status']} {commit.get('suite', '')}"
                    else:
                        # Revert any partial edits so the next objective starts clean.
                        run(["git", "-C", str(worktree), "checkout", "--", "."], timeout=120)
                        run(["git", "-C", str(worktree), "clean", "-fdq"], timeout=120)
                    if result.get("host_error"):
                        detail += f" host_error={result['host_error'][:120]}"
                    lines.append(f"- `{item['id']}`: {detail}")
                elif item["kind"] == "workbench-implement":
                    files = {}
                    wt = Path(item["worktree"]).resolve()
                    for name in item["files"]:
                        path = wt / name
                        files[name] = path.read_text(encoding="utf-8") if path.exists() else ""
                    out = run_dir / "workbench" / item["id"]
                    receipt = workbench_implement(
                        item["objective"], files, out, deadline_epoch, wt, args.branch
                    )
                    if receipt.get("usage"):
                        totals["input_tokens"] += receipt["usage"]["input_tokens"]
                        totals["output_tokens"] += receipt["usage"]["output_tokens"]
                    totals["requests"] += 1
                    detail = (
                        f"proposal_valid={receipt['valid']} applied={receipt.get('applied')} "
                        f"changed={len(receipt.get('changed', []))}"
                    )
                    if receipt.get("commit"):
                        detail += f" commit={receipt['commit'][0]}"
                    if receipt.get("validation_errors"):
                        detail += f" errors={receipt['validation_errors'][:1]}"
                    lines.append(f"- `{item['id']}`: {detail}")
                elif item["kind"] == "propose":
                    files = {}
                    for name in item["files"]:
                        path = ROOT / name
                        if path.stat().st_size > 200000:
                            raise ValueError(f"Propose file too large: {name}")
                        files[name] = path.read_text(encoding="utf-8")
                    out = run_dir / "proposals" / item["id"]
                    receipt = propose(
                        item["objective"],
                        files,
                        out,
                        deadline_epoch,
                        mode=item.get("mode", "rewrite"),
                    )
                    if receipt["usage"]:
                        totals["input_tokens"] += receipt["usage"]["input_tokens"]
                        totals["output_tokens"] += receipt["usage"]["output_tokens"]
                    totals["requests"] += 1
                    lines.append(
                        f"- `{item['id']}`: proposal valid={receipt['valid']} "
                        f"finish={receipt['finish_reason']} files={len(files)}"
                    )
                else:
                    raise ValueError(f"Unknown kind {item['kind']!r}")
                record(log, {"at": now(), "kind": "objective-end", "objective": item["id"]})
            except BaseException as error:
                lines.append(f"- `{item['id']}`: ERROR {type(error).__name__}: {str(error)[:200]}")
                record(
                    log,
                    {
                        "at": now(),
                        "kind": "objective-error",
                        "objective": item["id"],
                        "error": type(error).__name__,
                    },
                )
    finally:
        total_tokens = totals["input_tokens"] + totals["output_tokens"]
        lines += [
            "",
            f"- Requests: {totals['requests']}",
            (
                f"- Tokens: {totals['input_tokens']} in / {totals['output_tokens']} out "
                f"({total_tokens} total)"
            ),
            f"- Started: {started}",
            f"- Finished: {now()}",
            f"- Deadline: {deadline.isoformat()}",
            f"- Supervisor model: {args.supervisor_model}",
            f"- Implementer model: {args.implementer_model}",
        ]
        report.write_text("\n".join(lines) + "\n", encoding="utf-8")
        record(
            log,
            {
                "at": now(),
                "kind": "finish",
                **totals,
                "supervisor_model": args.supervisor_model,
                "implementer_model": args.implementer_model,
            },
        )
        if rolling_sleep_started:
            run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(CLOSE),
                    "-Sleep",
                ],
                timeout=180,
            )
        else:
            # Closeout sleep: cancel the deadline guard, then schedule ten minutes.
            run([str(CANCEL)], timeout=120)
            receipt = run_dir / "sleep-closeout.json"
            cancel = run_dir / "sleep-closeout.cancel"
            run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(CLOSE),
                    "-Sleep",
                    "-DelaySeconds",
                    "600",
                    "-ReceiptPath",
                    str(receipt),
                    "-CancelPath",
                    str(cancel),
                ],
                timeout=180,
            )
    print(
        json.dumps(
            {
                "report": str(report),
                **totals,
                "supervisor_model": args.supervisor_model,
                "implementer_model": args.implementer_model,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
