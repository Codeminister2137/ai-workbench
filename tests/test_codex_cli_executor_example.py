from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from ai_orchestrator import (
    AccessMethod,
    AuthMethod,
    BillingSource,
    CostPolicyTier,
    ExecutionTarget,
    PrivacyClass,
    TaskProfile,
)

_EXAMPLE_PATH = (
    Path(__file__).resolve().parents[1]
    / "packages"
    / "ai_orchestrator"
    / "examples"
    / "codex_cli_executor.py"
)
_SPEC = importlib.util.spec_from_file_location("codex_cli_executor_example", _EXAMPLE_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
_EXAMPLE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _EXAMPLE
_SPEC.loader.exec_module(_EXAMPLE)

CodexCliConfig = _EXAMPLE.CodexCliConfig
build_codex_exec_command = _EXAMPLE.build_codex_exec_command
codex_cli_config_from_execution_target = _EXAMPLE.codex_cli_config_from_execution_target
prepare_codex_cli_execution = _EXAMPLE.prepare_codex_cli_execution
run_codex_exec = _EXAMPLE.run_codex_exec


def test_codex_cli_config_requires_codex_cli_access_method(tmp_path: Path) -> None:
    target = ExecutionTarget(
        route_id="openai-api-gpt-5.1",
        provider="openai",
        product="openai_api",
        model="gpt-5.1",
        access_method=AccessMethod.PROVIDER_API,
        auth_method=AuthMethod.API_KEY,
        billing_source=BillingSource.OPENAI_API_BILLING,
        cost_policy_tier=CostPolicyTier.BILLING_ALLOWED,
    )

    with pytest.raises(ValueError, match="not codex_cli"):
        codex_cli_config_from_execution_target(
            target,
            cwd=tmp_path,
            command="codex",
        )


def test_codex_cli_config_accepts_chatgpt_signed_in_target(tmp_path: Path) -> None:
    target = ExecutionTarget(
        route_id="openai-codex-gpt-5.1",
        provider="openai",
        product="codex",
        model="gpt-5.1",
        access_method=AccessMethod.CODEX_CLI,
        auth_method=AuthMethod.CHATGPT_SIGN_IN,
        billing_source=BillingSource.CHATGPT_SUBSCRIPTION_ALLOWANCE,
        cost_policy_tier=CostPolicyTier.ALLOWANCES_ALLOWED,
        timeout_seconds=30,
    )

    config = codex_cli_config_from_execution_target(
        target,
        cwd=tmp_path,
        command="codex",
    )

    assert config.command == "codex"
    assert config.model == "gpt-5.1"
    assert config.cwd == tmp_path
    assert config.timeout_seconds == 30


def test_build_codex_exec_command_reads_prompt_from_stdin(tmp_path: Path) -> None:
    config = CodexCliConfig(command="codex", model="gpt-5.1", cwd=tmp_path)

    command = build_codex_exec_command(config)

    assert command == (
        "codex",
        "exec",
        "--cd",
        str(tmp_path),
        "--model",
        "gpt-5.1",
        "--sandbox",
        "workspace-write",
        "--ephemeral",
        "-",
    )


def test_run_codex_exec_uses_injected_runner(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []

    def fake_runner(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append({"args": args, "kwargs": kwargs})
        return subprocess.CompletedProcess(args[0], 0, stdout="done", stderr="")

    config = CodexCliConfig(command="codex", model="gpt-5.1", cwd=tmp_path)

    result = run_codex_exec("Do the task.", config, runner=fake_runner)

    assert result.ok is True
    assert result.stdout == "done"
    assert calls[0]["kwargs"]["input"] == "Do the task."
    assert calls[0]["kwargs"]["cwd"] == tmp_path


def test_prepare_codex_cli_execution_rejects_local_only_privacy(tmp_path: Path) -> None:
    catalog_path = tmp_path / "models.toml"
    catalog_path.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="requires non-local privacy"):
        prepare_codex_cli_execution(
            "Do the task.",
            TaskProfile(privacy_class=PrivacyClass.LOCAL_ONLY),
            catalog_path,
            cwd=tmp_path,
            codex_command="codex",
        )


def test_prepare_codex_cli_execution_dry_run_uses_catalog_target(tmp_path: Path) -> None:
    catalog_path = tmp_path / "models.toml"
    catalog_path.write_text(
        """
[[models]]
provider = "openai"
model = "gpt-5.1"
location = "external"
access_method = "codex_cli"
quality = "standard"
latency = "interactive"
""",
        encoding="utf-8",
    )

    result = prepare_codex_cli_execution(
        "Explain the repo test command.",
        TaskProfile(
            privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
            user_backend_override="openai",
            user_model_override="gpt-5.1",
        ),
        catalog_path,
        cwd=tmp_path,
        codex_command="codex",
        execute=False,
        review_prompt=False,
    )

    assert result.config is not None
    assert result.result is None
    assert result.config.command == "codex"
    assert result.config.model == "gpt-5.1"
