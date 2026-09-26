from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_orchestrator import (
    AccessMethod,
    AuthMethod,
    BillingSource,
    CostPolicyTier,
    ExecutionTarget,
    OrchestrationResult,
    OrchestrationStatus,
    PrivacyClass,
    TaskProfile,
    load_model_catalog,
    prepare_execution,
)


@dataclass(frozen=True, slots=True)
class CodexCliConfig:
    """Runtime configuration for a Codex CLI execution route."""

    command: str
    model: str
    cwd: Path
    sandbox: str = "workspace-write"
    timeout_seconds: float = 600.0
    ephemeral: bool = True
    json_output: bool = False
    resume: str | None = None


@dataclass(frozen=True, slots=True)
class CodexCliResult:
    """Completed Codex CLI process result."""

    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    events: CodexJsonlSummary | None = None

    @property
    def ok(self) -> bool:
        """Return whether the Codex CLI process exited successfully."""

        return self.returncode == 0 and (self.events is None or self.events.failure_reason is None)


@dataclass(frozen=True, slots=True)
class CodexJsonlSummary:
    """Structured summary parsed from `codex exec --json` JSONL events."""

    final_answer: str | None
    command_events: tuple[dict[str, Any], ...]
    tool_events: tuple[dict[str, Any], ...]
    file_change_events: tuple[dict[str, Any], ...]
    usage: dict[str, Any] | None
    failure_reason: str | None
    parse_errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CodexCliExecutionResult:
    """Prepared or executed Codex CLI request."""

    orchestration: OrchestrationResult
    config: CodexCliConfig | None = None
    result: CodexCliResult | None = None


def default_codex_command() -> str | None:
    """Return the Codex executable from PATH or the local PyCharm bundle."""

    command = shutil.which("codex")
    if command:
        return command

    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None

    bundled = (
        Path(local_app_data)
        / "JetBrains"
        / "PyCharm2025.3"
        / "aia"
        / "codex"
        / "bin"
        / "codex-x86_64-pc-windows-msvc.exe"
    )
    if bundled.exists():
        return str(bundled)
    return None


def codex_cli_config_from_execution_target(
    target: ExecutionTarget,
    *,
    cwd: Path,
    command: str | None = None,
    timeout_seconds: float | None = None,
    ephemeral: bool = True,
    resume: str | None = None,
) -> CodexCliConfig:
    """Adapt an orchestrator target to Codex CLI runtime config."""

    if target.access_method is not AccessMethod.CODEX_CLI:
        raise ValueError(
            f"Execution target access method {target.access_method.value!r} is not codex_cli."
        )
    if target.auth_method is not AuthMethod.CHATGPT_SIGN_IN:
        raise ValueError("Codex CLI execution requires ChatGPT sign-in authentication.")
    if target.billing_source not in {
        BillingSource.CHATGPT_SUBSCRIPTION_ALLOWANCE,
        BillingSource.CHATGPT_WORKSPACE_CREDITS,
    }:
        raise ValueError("Codex CLI execution must use a ChatGPT billing source.")

    resolved_command = command or default_codex_command()
    if resolved_command is None:
        raise FileNotFoundError(
            "Could not find Codex CLI. Provide --codex-command or install/configure Codex CLI."
        )

    return CodexCliConfig(
        command=resolved_command,
        model=target.model,
        cwd=cwd,
        timeout_seconds=timeout_seconds or target.timeout_seconds,
        ephemeral=ephemeral,
        resume=resume,
    )


def build_codex_exec_command(config: CodexCliConfig) -> tuple[str, ...]:
    """Build a non-interactive `codex exec` command that reads the prompt from stdin."""

    if config.resume is not None:
        command = [
            config.command,
            "exec",
            "resume",
            "--model",
            config.model,
        ]
        if config.json_output:
            command.append("--json")
        if config.resume == "last":
            command.append("--last")
        else:
            command.append(config.resume)
        command.append("-")
        return tuple(command)

    command = [
        config.command,
        "exec",
        "--cd",
        str(config.cwd),
        "--model",
        config.model,
        "--sandbox",
        config.sandbox,
    ]
    if config.ephemeral:
        command.append("--ephemeral")
    if config.json_output:
        command.append("--json")
    command.append("-")
    return tuple(command)


def parse_codex_jsonl_events(text: str) -> CodexJsonlSummary:
    """Parse Codex JSONL events into stable fields used by this repository."""

    final_answer = None
    command_events: list[dict[str, Any]] = []
    tool_events: list[dict[str, Any]] = []
    file_change_events: list[dict[str, Any]] = []
    usage = None
    failure_reason = None
    parse_errors: list[str] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError as exc:
            parse_errors.append(f"line {line_number}: {exc.msg}")
            continue
        if not isinstance(event, dict):
            parse_errors.append(f"line {line_number}: expected JSON object")
            continue
        event_type = _event_type(event)
        haystack = _event_haystack(event, event_type)
        if any(token in haystack for token in ("command", "shell", "exec", "terminal")):
            command_events.append(event)
        if "tool" in haystack or "function_call" in haystack:
            tool_events.append(event)
        if any(token in haystack for token in ("file_change", "patch", "diff", "edit", "write")):
            file_change_events.append(event)
        event_usage = _find_usage(event)
        if event_usage is not None:
            usage = event_usage
        event_failure = _find_failure_reason(event, event_type)
        if event_failure is not None and (failure_reason is None or event_failure != event_type):
            failure_reason = event_failure
        event_answer = _find_final_answer(event, event_type)
        if event_answer:
            final_answer = event_answer
    return CodexJsonlSummary(
        final_answer=final_answer,
        command_events=tuple(command_events),
        tool_events=tuple(tool_events),
        file_change_events=tuple(file_change_events),
        usage=usage,
        failure_reason=failure_reason,
        parse_errors=tuple(parse_errors),
    )


def _event_type(event: dict[str, Any]) -> str:
    for key in ("type", "event", "kind", "name"):
        value = event.get(key)
        if isinstance(value, str):
            return value.lower()
    nested = event.get("item")
    if isinstance(nested, dict):
        return _event_type(nested)
    return ""


def _event_haystack(event: dict[str, Any], event_type: str) -> str:
    labels = [event_type]
    for key in ("type", "event", "kind", "name", "subtype", "status"):
        value = event.get(key)
        if isinstance(value, str):
            labels.append(value.lower())
    nested = event.get("item")
    if isinstance(nested, dict):
        labels.append(_event_haystack(nested, _event_type(nested)))
    return " ".join(labels)


def _find_usage(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        for key, nested in value.items():
            key_lower = key.lower()
            if key_lower == "usage" and isinstance(nested, dict):
                return nested
            if "token" in key_lower and isinstance(nested, dict):
                return nested
            found = _find_usage(nested)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_usage(item)
            if found is not None:
                return found
    return None


def _find_failure_reason(event: dict[str, Any], event_type: str) -> str | None:
    haystack = _event_haystack(event, event_type)
    if not any(token in haystack for token in ("error", "failed", "failure")):
        return None
    for key in ("error", "failure", "details"):
        value = event.get(key)
        if isinstance(value, dict):
            for nested_key in ("message", "error", "failure_reason", "reason", "detail"):
                nested_value = value.get(nested_key)
                if isinstance(nested_value, str) and nested_value.strip():
                    return nested_value.strip()
            nested = _find_failure_reason(value, _event_type(value) or key)
            if nested is not None:
                return nested
    for key in ("message", "error", "failure_reason", "reason", "detail"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return event_type or "codex reported failure"


def _find_final_answer(event: dict[str, Any], event_type: str) -> str | None:
    explicit = event.get("final_answer")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    if "final" in event_type or event.get("role") == "assistant":
        text = _find_text_payload(event)
        if text:
            return text
    if event_type in {"assistant_message", "agent_message", "message", "response"}:
        text = _find_text_payload(event)
        if text:
            return text
    nested = event.get("item")
    if isinstance(nested, dict):
        return _find_final_answer(nested, _event_type(nested))
    return None


def _find_text_payload(value: Any) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        for key in ("text", "content", "message", "answer", "output"):
            nested = value.get(key)
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
        for key in ("content", "message", "delta", "item"):
            found = _find_text_payload(value.get(key))
            if found:
                return found
    if isinstance(value, list):
        parts = [_find_text_payload(item) for item in value]
        text = "\n".join(part for part in parts if part)
        return text or None
    return None


def run_codex_exec(
    prompt: str,
    config: CodexCliConfig,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> CodexCliResult:
    """Run `codex exec` with the prompt on stdin."""

    command = build_codex_exec_command(config)
    completed = runner(
        command,
        input=prompt,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=config.timeout_seconds,
        cwd=config.cwd,
    )
    stdout = completed.stdout or ""
    return CodexCliResult(
        command=command,
        returncode=completed.returncode,
        stdout=stdout,
        stderr=completed.stderr or "",
        events=parse_codex_jsonl_events(stdout) if config.json_output and stdout else None,
    )


def prepare_codex_cli_execution(
    prompt: str,
    profile: TaskProfile,
    catalog_path: Path,
    *,
    cwd: Path,
    review_prompt: bool = True,
    codex_command: str | None = None,
    timeout_seconds: float = 600.0,
    codex_persist_session: bool = False,
    codex_resume: str | None = None,
    execute: bool = False,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> CodexCliExecutionResult:
    """Prepare and optionally run a Codex CLI execution target."""

    if profile.privacy_class is PrivacyClass.LOCAL_ONLY:
        raise ValueError("Codex CLI execution is external and requires non-local privacy.")

    catalog = load_model_catalog(catalog_path)
    orchestration = prepare_execution(
        prompt,
        profile,
        catalog,
        review_prompt=review_prompt,
        timeout_seconds=timeout_seconds,
    )
    if not orchestration.is_ready or orchestration.execution_plan is None:
        return CodexCliExecutionResult(orchestration=orchestration)

    config = codex_cli_config_from_execution_target(
        orchestration.execution_plan.target,
        cwd=cwd,
        command=codex_command,
        timeout_seconds=timeout_seconds,
        ephemeral=not codex_persist_session and codex_resume is None,
        resume=codex_resume,
    )
    if not execute:
        return CodexCliExecutionResult(orchestration=orchestration, config=config)

    result = run_codex_exec(prompt, config, runner=runner)
    return CodexCliExecutionResult(
        orchestration=orchestration,
        config=config,
        result=result,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for minimal Codex CLI execution."""

    parser = argparse.ArgumentParser(description="Prepare or run a Codex CLI execution target.")
    parser.add_argument("prompt", help="Prompt to pass to codex exec.")
    parser.add_argument("--catalog", type=Path, required=True, help="Model catalog path.")
    parser.add_argument("--cwd", type=Path, default=Path.cwd(), help="Working directory for Codex.")
    parser.add_argument("--codex-command", help="Path to the Codex executable.")
    parser.add_argument("--route-id", help="Hard Codex access-route override.")
    parser.add_argument("--provider", default="openai", help="Provider override from the catalog.")
    parser.add_argument("--model", required=True, help="Model override from the catalog.")
    parser.add_argument(
        "--cost-policy",
        choices=[item.value for item in CostPolicyTier],
        default=CostPolicyTier.ALLOWANCES_ALLOWED.value,
        help="Maximum billing boundary this task may cross.",
    )
    parser.add_argument(
        "--privacy",
        choices=[
            PrivacyClass.EXTERNAL_ALLOWED.value,
            PrivacyClass.SENSITIVE_REVIEW_REQUIRED.value,
        ],
        default=PrivacyClass.EXTERNAL_ALLOWED.value,
        help="Task privacy class. Codex CLI is external, so local_only is not accepted.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    parser.add_argument("--skip-prompt-review", action="store_true")
    parser.add_argument("--codex-persist-session", action="store_true")
    parser.add_argument("--codex-resume")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)

    if args.codex_persist_session and args.codex_resume:
        parser.error("--codex-persist-session cannot be combined with --codex-resume")

    profile = TaskProfile(
        privacy_class=PrivacyClass(args.privacy),
        cost_policy_tier=CostPolicyTier(args.cost_policy),
        user_route_id_override=args.route_id,
        user_backend_override=args.provider,
        user_model_override=args.model,
    )
    result = prepare_codex_cli_execution(
        args.prompt,
        profile,
        args.catalog,
        cwd=args.cwd,
        review_prompt=not args.skip_prompt_review,
        codex_command=args.codex_command,
        timeout_seconds=args.timeout_seconds,
        codex_persist_session=args.codex_persist_session,
        codex_resume=args.codex_resume,
        execute=args.execute,
    )

    print(f"status: {result.orchestration.status.value}")
    if result.orchestration.status is OrchestrationStatus.NEEDS_PROMPT_REVIEW:
        assert result.orchestration.prompt_judge is not None
        print(f"suggested_prompt: {result.orchestration.prompt_judge.refined_prompt}")
        return 2
    if result.orchestration.status is OrchestrationStatus.MODEL_SELECTION_FAILED:
        print(f"failure_reason: {result.orchestration.failure_reason}")
        return 1
    if result.config is not None:
        assert result.orchestration.execution_plan is not None
        print(f"route_id: {result.orchestration.execution_plan.target.route_id}")
        print(f"product: {result.orchestration.execution_plan.target.product}")
        print(f"codex_command: {result.config.command}")
        print(f"model: {result.config.model}")
        print(
            f"cost_policy_tier: {result.orchestration.execution_plan.target.cost_policy_tier.value}"
        )
        print(f"cwd: {result.config.cwd}")
    if result.result is None:
        print("execution: skipped")
        return 0

    print(f"returncode: {result.result.returncode}")
    if result.result.stdout:
        print(result.result.stdout, end="")
    if result.result.stderr:
        print(result.result.stderr, end="", file=sys.stderr)
    return result.result.returncode


if __name__ == "__main__":
    sys.exit(main())
