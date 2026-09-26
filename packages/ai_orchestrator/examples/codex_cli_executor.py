from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

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


@dataclass(frozen=True, slots=True)
class CodexCliResult:
    """Completed Codex CLI process result."""

    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        """Return whether the Codex CLI process exited successfully."""

        return self.returncode == 0


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
    )


def build_codex_exec_command(config: CodexCliConfig) -> tuple[str, ...]:
    """Build a non-interactive `codex exec` command that reads the prompt from stdin."""

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
        capture_output=True,
        timeout=config.timeout_seconds,
        cwd=config.cwd,
    )
    return CodexCliResult(
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
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
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)

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
