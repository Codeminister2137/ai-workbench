"""Fixed synthetic coding fixture with target-only tools and safe host validation."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

from ai_agent import AgentLoop, PermissionManager, PermissionPolicy
from ai_agent.contracts import ToolCall, ToolDefinition, ToolResult
from ai_agent.tools import EditFileTool, ReadFileTool, ToolContext, ToolRegistry
from ai_agent.tools.base import BaseTool

from ai_provider.acceptance_jobs import AcceptanceJob
from ai_provider.acceptance_processes import OwnedChild, remaining
from ai_provider.config import BackendConfig, ProviderKind
from ai_provider.contracts import AIRequest, AIResponse, AIStreamEvent, BackendInfo, ChatClient
from ai_provider.factory import create_chat_client
from ai_provider.native_admission import NativeCodingClient
from ai_provider.orchestrated_runs import _utc_now

INSTRUCTIONS = (
    "Synthetic acceptance workspace. Read source.py before editing it. "
    "Edit only source.py to fix add(a, b). Preserve all other files. "
    "Use actual tools; shell, networking, delegation and process tools are unavailable. "
    "Keep a single pure arithmetic function; no imports, calls or other statements.\n"
)
SOURCE = "def add(a, b):\n    return a - b\n"
# Run under isolated Python, with no import of model-controlled modules. Only a
# tiny pure expression is compiled; even malicious edits cannot execute calls.
VALIDATOR = """import ast
from pathlib import Path

tree = ast.parse(Path(__file__).with_name("source.py").read_text(encoding="utf-8"))
assert len(tree.body) == 1 and isinstance(tree.body[0], ast.FunctionDef)
function = tree.body[0]
assert function.name == "add" and not function.decorator_list
assert function.returns is None and not function.type_comment and not function.type_params
expected = ast.parse("def add(a, b): return a + b").body[0].args
assert ast.dump(function.args) == ast.dump(expected)
assert len(function.body) == 1 and isinstance(function.body[0], ast.Return)
value = function.body[0].value
assert isinstance(value, ast.BinOp) and isinstance(value.op, (ast.Add, ast.Sub, ast.Mult))
assert isinstance(value.left, ast.Name) and isinstance(value.right, ast.Name)
assert {value.left.id, value.right.id} == {"a", "b"}
namespace = {"__builtins__": {}}
exec(compile(tree, "source.py", "exec"), namespace)
add = namespace["add"]
passed = all(add(a, b) == result for a, b, result in [(2,3,5),(-2,-3,-5),(0,7,7)])
raise SystemExit(0 if passed else 1)
"""
PROTECTED = {"AGENTS.md": INSTRUCTIONS, "test_source.py": VALIDATOR, "sentinel.txt": "preserve\n"}


class DurableReceipts(list[dict[str, Any]]):
    """Flush observed events before a timeout can terminate the fixed worker."""

    def __init__(self, path: Path):
        super().__init__()
        self.path = path
        path.touch(exist_ok=False)

    def append(self, value: dict[str, Any]) -> None:
        value = {"observed_at_utc": _utc_now(), **value}
        with self.path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(value, allow_nan=False) + "\n")
            output.flush()
            os.fsync(output.fileno())
        super().append(value)


def check_plain_path(path: Path) -> None:
    """Reject symlink/junction components rather than resolving them into authority."""
    for part in (path, *path.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError("Acceptance paths must not contain symlinks or junctions")


def check_protected(fixture: Path) -> None:
    check_plain_path(fixture)
    for name, expected in PROTECTED.items():
        target = fixture / name
        check_plain_path(target)
        if target.stat().st_nlink != 1 or target.read_text(encoding="utf-8") != expected:
            raise ValueError("Protected acceptance fixture content changed")


class FixtureTool(BaseTool):
    """Reuse tool contracts while enforcing a fixed, private fixture boundary."""

    def __init__(self, tool: BaseTool, fixture: Path, receipts: list[dict[str, Any]]):
        self.tool = tool
        self.fixture = fixture
        self.receipts = receipts

    @property
    def definition(self) -> ToolDefinition:
        return self.tool.definition

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        if context.workspace_root != self.fixture:
            raise ValueError("Tool context belongs to another workspace")
        name = arguments.get("path")
        allowed = (
            {"source.py"} if self.definition.name == "edit_file" else {"source.py", *PROTECTED}
        )
        if not isinstance(name, str) or name not in allowed:
            raise ValueError("Tool path is not permitted by the fixed acceptance fixture")
        if self.definition.name == "edit_file" and not any(
            item.get("tool") == "read_file"
            and item.get("path") == "source.py"
            and item.get("is_error") is False
            for item in self.receipts
        ):
            raise ValueError("Read source.py successfully before editing it")
        check_protected(self.fixture)
        target = self.fixture / name
        check_plain_path(target)
        if target.stat().st_nlink != 1:
            raise ValueError("Hard-linked fixture files are not permitted")
        if self.definition.name == "edit_file" and (
            not isinstance(arguments.get("new_text"), str) or len(arguments["new_text"]) > 4096
        ):
            raise ValueError("Fixture edits require at most 4096 characters")
        result = self.tool.execute(arguments, context)
        return result

    def run(self, call: ToolCall, context: ToolContext) -> ToolResult:
        result = super().run(call, context)
        digest = None
        try:
            target = self.fixture / "source.py"
            check_plain_path(target)
            if target.stat().st_nlink == 1:
                digest = hashlib.sha256(target.read_bytes()).hexdigest()
        except (ValueError, OSError):
            pass
        self.receipts.append(
            {
                "tool": self.definition.name,
                "path": call.arguments.get("path")
                if call.arguments.get("path") in {"source.py", *PROTECTED}
                else None,
                "is_error": result.is_error,
                "output_sha256": hashlib.sha256(result.output.encode()).hexdigest(),
                "source_sha256": digest,
                "observed_at_utc": _utc_now(),
            }
        )
        return result


class DeadlineClient:
    """Recreate the local client with remaining time after all admission checks."""

    def __init__(
        self,
        config: BackendConfig,
        deadline: float,
        owner_check: Callable[[float], None],
        factory: Callable[[BackendConfig], ChatClient],
        usage: list[dict[str, Any]],
        clock: Callable[[], float],
    ):
        self.config, self.deadline, self.owner_check = config, deadline, owner_check
        self.factory, self.usage, self.clock = factory, usage, clock

    @property
    def backend(self) -> BackendInfo:
        return self.factory(self.config).backend

    def complete(self, request: AIRequest) -> AIResponse:
        self.owner_check(min(2, remaining(self.deadline, self.clock)))
        config = replace(
            self.config,
            timeout_seconds=min(self.config.timeout_seconds, remaining(self.deadline, self.clock)),
        )
        response = self.factory(config).complete(request)
        remaining(self.deadline, self.clock)
        self.usage.append(
            {
                "source": response.usage.source.value,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.total_tokens,
            }
        )
        return response

    def stream(self, request: AIRequest) -> Iterator[AIStreamEvent]:
        raise NotImplementedError("Fixed acceptance harness uses complete requests only")


def validate_fixture(
    fixture: Path,
    artifact: Path,
    label: str,
    deadline: float,
    receipt: Callable[[dict[str, Any]], None],
    *,
    clock: Callable[[], float] = time.monotonic,
) -> int:
    check_protected(fixture)
    source = fixture / "source.py"
    check_plain_path(source)
    if source.stat().st_nlink != 1 or source.stat().st_size > 16384:
        raise ValueError("Source must be a bounded, unlinked fixture file")
    child = OwnedChild(
        [sys.executable, "-I", "-S", str(fixture / "test_source.py")],
        cwd=fixture,
        env={
            key: value
            for key, value in os.environ.items()
            if key.upper() in {"SYSTEMROOT", "WINDIR"}
        },
        log=artifact / f"{label}.log",
        role="validator",
        receipt=receipt,
    )
    try:
        code = child.wait(deadline, clock)
    finally:
        cleanup = child.stop(min(2, max(0.01, deadline - clock())))
        receipt({"stage": "validator_cleanup", "verified": cleanup, **child.identity})
    if not cleanup:
        raise ValueError("Validator child cleanup could not be verified")
    check_protected(fixture)
    return code


def run_fixture(
    job: AcceptanceJob,
    artifact: Path,
    deadline: float,
    owner_check: Callable[[float], None],
    *,
    client_factory: Callable[[BackendConfig], ChatClient] = create_chat_client,
    clock: Callable[[], float] = time.monotonic,
    validator: Callable[..., int] = validate_fixture,
) -> dict[str, Any]:
    """Run one immutable fixture; failures retain files and observed receipts."""
    fixture = artifact / "fixture"
    check_plain_path(fixture)
    fixture.mkdir()
    for name, content in {**PROTECTED, "source.py": SOURCE}.items():
        (fixture / name).write_text(content, encoding="utf-8")
    receipts = DurableReceipts(artifact / "worker-receipts.jsonl")
    usage: list[dict[str, Any]] = []
    diagnostics: list[str] = []
    result: dict[str, Any] = {
        "schema_version": 1,
        "task_id": job.task_id,
        "passed": False,
        "receipts": receipts,
        "usage": usage,
        "admission": diagnostics,
        "next_action": "Inspect preserved fixture and receipts before planning a new job",
    }
    try:
        baseline = validator(fixture, artifact, "baseline", deadline, receipts.append, clock=clock)
        result["baseline_exit_code"] = baseline
        if baseline != 1:
            raise ValueError("Fixed baseline must fail its behavior tests")
        config = BackendConfig(
            ProviderKind.OLLAMA,
            job.model,
            job.runtime_base_url,
            timeout_seconds=min(job.request_timeout_seconds, remaining(deadline, clock)),
        )

        def record_admission(text: str) -> None:
            diagnostics.append(text)
            receipts.append({"stage": "estimated_admission", "diagnostic": text})

        client = NativeCodingClient(
            DeadlineClient(config, deadline, owner_check, client_factory, usage, clock),
            config,
            job.context_tokens,
            record_admission,
        )

        class OutputBoundClient:
            backend = client.backend

            def complete(self, request: AIRequest) -> AIResponse:
                remaining(deadline, clock)
                owner_check(min(2, remaining(deadline, clock)))
                client.config = replace(
                    config, timeout_seconds=min(config.timeout_seconds, remaining(deadline, clock))
                )
                return client.complete(replace(request, max_output_tokens=job.output_tokens))

            def stream(self, request: AIRequest) -> Iterator[AIStreamEvent]:
                raise NotImplementedError

        registry = ToolRegistry(
            tuple(FixtureTool(tool, fixture, receipts) for tool in (ReadFileTool(), EditFileTool()))
        )
        agent_result = AgentLoop(
            OutputBoundClient(),
            registry,
            ToolContext(fixture),
            permissions=PermissionManager(policy=PermissionPolicy.workspace_write()),
            max_iterations=job.max_iterations,
        ).run(
            "Fix add(a, b) using actual read/edit tools. The host runs the fixed tests.",
            system_prompt=INSTRUCTIONS,
            model=job.model,
        )
        check_protected(fixture)
        code = validator(fixture, artifact, "postchange", deadline, receipts.append, clock=clock)
        result["validation_exit_code"] = code
        actual = [item for item in receipts if "tool" in item]
        observed = {item["tool"] for item in actual if not item["is_error"]}
        result["passed"] = (
            code == 0
            and {"read_file", "edit_file"} <= observed
            and not any(item["is_error"] for item in actual)
            and not any(item.is_error for item in agent_result.tool_results)
        )
        remaining(deadline, clock)
        if result["passed"]:
            result["next_action"] = (
                "Review bounded compatibility receipts; broader parity remains pending"
            )
    except Exception as exc:
        result["passed"] = False
        result["reason"] = f"{type(exc).__name__}: {exc}"[:2000]
    return result
