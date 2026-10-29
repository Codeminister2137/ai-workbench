"""Run a fresh bounded scripted loopback rehearsal, with no live activation path.

This uses the real Responses adapter, delegation executor and file/process tools.
All model replies are scripted; no provider key or hosted inference is needed.
Consumed evidence directories cannot be overwritten or resumed by this command.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

from ai_provider.acceptance_processes import OwnedChild
from ai_provider.acceptance_runtime import worker_environment

ROOT = Path(__file__).resolve().parents[1]
TESTS = (
    "tests/test_hosted_delegation_acceptance.py",
    "tests/repo_assistant/test_protocol_continuity.py",
)
REQUIRED_CLASSES = {
    f"test_nested_delegation_over_real_transport[{mode}-{provider}]": (
        "tests.test_hosted_delegation_acceptance"
    )
    for mode in ("complete", "read_only", "outside_scope", "budget_exhausted")
    for provider in ("meta", "baseten")
}
REQUIRED_CLASSES["test_two_turn_chat_preserves_process_and_history_across_protocol_fallback"] = (
    "tests.repo_assistant.test_protocol_continuity"
)
REQUIRED_CASES = frozenset(REQUIRED_CLASSES)
SOURCES = (
    "scripts/hosted-delegation-acceptance.py",
    *TESTS,
    "packages/ai_agent/src/ai_agent/loop.py",
    "packages/ai_agent/src/ai_agent/mcp_server.py",
    "packages/ai_agent/src/ai_agent/delegation_scope.py",
    "packages/ai_agent/src/ai_agent/tools/delegation.py",
    "packages/ai_agent/src/ai_agent/processes.py",
    "packages/ai_provider/src/ai_provider/adapters/meta.py",
    "packages/ai_provider/src/ai_provider/adapters/openai_responses.py",
    "packages/ai_provider/src/ai_provider/adapters/baseten.py",
    "packages/ai_provider/src/ai_provider/adapters/openai_compatible.py",
    "packages/ai_orchestrator/src/ai_orchestrator/catalog.py",
    "packages/ai_orchestrator/src/ai_orchestrator/models.py",
    "packages/ai_provider/src/ai_provider/acceptance_processes.py",
    "packages/ai_agent/src/ai_agent/repo_coding_assistant.py",
    "packages/ai_agent/src/ai_agent/coding_chat_cli.py",
    "packages/ai_provider/src/ai_provider/foreground_tools.py",
    "packages/ai_provider/src/ai_provider/coding_sessions.py",
    "packages/ai_provider/src/ai_provider/execution_fallback.py",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output_dir.resolve()
    if not output.is_relative_to((ROOT / "artifacts").resolve()):
        parser.error("Output must be a fresh directory under repository artifacts")
    output.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for name in SOURCES:
        content = (ROOT / name).read_bytes()
        hashes[name] = hashlib.sha256(content).hexdigest()
        snapshot = output / "source-snapshot" / name
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        with snapshot.open("xb") as archived:
            archived.write(content)
    receipt = {
        "status": "running",
        "mode": "scripted_loopback_only",
        "live_inference_calls": 0,
        "started_utc": datetime.now(UTC).isoformat(),
        "source_sha256": hashes,
        "work_seconds": 90,
        "cleanup_seconds": 5,
        "maximum_scripted_http_calls": 80,
        "required_cases": sorted(REQUIRED_CASES),
        "cleanup_verified": False,
        "hosted_model_acceptance": "unestablished",
    }
    receipt_path = output / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    def record_identity(identity):
        receipt.update(identity)
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    child = None
    deadline = time.monotonic() + 90
    try:
        child = OwnedChild(
            [
                sys.executable,
                "-m",
                "pytest",
                *TESTS,
                "-q",
                "--tb=short",
                "-p",
                "no:cacheprovider",
                "--junitxml=" + str(output / "junit.xml"),
            ],
            cwd=ROOT,
            env=worker_environment(),
            log=output / "run.log",
            role="offline_delegation_rehearsal",
            receipt=record_identity,
        )
        receipt["exit_code"] = child.wait(deadline)
        report = ET.parse(output / "junit.xml").getroot()
        cases = report.findall(".//testcase")
        receipt["checks"] = len(cases)
        receipt["observed_cases"] = [case.get("name") for case in cases]
        receipt["required_checks_passed"] = (
            len(cases) == len(REQUIRED_CASES)
            and {case.get("name") for case in cases} == REQUIRED_CASES
            and all(
                case.get("classname") == REQUIRED_CLASSES.get(case.get("name", ""))
                for case in cases
            )
            and not any(
                case.find(tag) is not None
                for case in cases
                for tag in ("failure", "error", "skipped")
            )
        )
        receipt["declared_sources_unchanged"] = all(
            hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
            for name, expected in hashes.items()
        )
        receipt["status"] = (
            "passed"
            if (
                receipt["exit_code"] == 0
                and receipt["required_checks_passed"]
                and receipt["declared_sources_unchanged"]
            )
            else "failed"
        )
    except (OSError, ValueError, ET.ParseError, subprocess.TimeoutExpired) as error:
        receipt["status"] = "failed"
        receipt["error_type"] = type(error).__name__
    finally:
        if child is not None:
            receipt["cleanup_verified"] = child.stop(5)
            receipt["child_exited"] = child.process.poll() is not None
        if not receipt["cleanup_verified"]:
            receipt["status"] = "failed"
        receipt["stage"] = "finished"
        receipt["stopped_utc"] = datetime.now(UTC).isoformat()
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
