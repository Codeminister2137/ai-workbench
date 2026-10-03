"""Opt-in synthetic Codex-limit simulation followed by a real Copilot continuation."""

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from ai_orchestrator import AccessMethod
from ai_provider import execution_fallback
from ai_provider import repo_coding_assistant as cli
from ai_provider.agent_readiness import AgentReadiness
from ai_provider.external_agents import ExternalAgentResult, parse_external_agent_jsonl


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    artifact = (
        root / "artifacts" / ("fallback-acceptance-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S"))
    )
    artifact.mkdir(parents=True)
    source = artifact / "source.py"
    source.write_text("value = 0\n", encoding="utf-8")
    tests = artifact / "test_source.py"
    original_tests = "from source import value\nassert value == 2, value\n"
    tests.write_text(original_tests, encoding="utf-8")
    (artifact / "AGENTS.md").write_text(
        "Synthetic acceptance fixture. Edit only source.py; preserve other files. "
        "No network, external services, delegation, or files outside this directory.\n",
        encoding="utf-8",
    )
    catalog = artifact / "catalog.toml"
    catalog.write_text(
        """[[models]]
route_id = "simulated-codex"
provider = "openai"
product = "codex"
model = "test"
location = "external"
access_method = "codex_cli"
auth_method = "chatgpt_sign_in"
billing_source = "chatgpt_subscription_allowance"
cost_policy_tier = "allowances_allowed"
quality = "high"
[models.capabilities]
chat = true
tools = true
[[models]]
route_id = "github-copilot-cli-default"
provider = "github"
product = "github_copilot"
model = "auto"
location = "external"
access_method = "copilot_cli"
auth_method = "github_account_sign_in"
billing_source = "github_copilot_subscription_allowance"
cost_policy_tier = "allowances_allowed"
quality = "standard"
[models.capabilities]
chat = true
tools = true
""",
        encoding="utf-8",
    )
    local_copilot = root / ".tools" / "copilot" / "copilot.exe"
    if local_copilot.exists():
        os.environ.setdefault("GITHUB_COPILOT_COMMAND", str(local_copilot))
    # Only command construction uses this; the simulated Codex route never spawns it.
    os.environ.setdefault("CODEX_COMMAND", "codex-simulated")
    baseline = subprocess.run((sys.executable, str(tests)), cwd=artifact, capture_output=True)
    assert baseline.returncode != 0
    real_execute = cli._run_external_agent
    real_auth = execution_fallback.check_agent_readiness
    attempts = []

    def execute(prompt, config, **kwargs):
        attempts.append(config.access_method.value)
        if config.access_method is AccessMethod.CODEX_CLI:
            source.write_text(
                "# Partial work before simulated quota exhaustion\nvalue = 1\n", encoding="utf-8"
            )
            event = json.dumps({"type": "error", "message": "You've hit your usage limit"})
            return ExternalAgentResult(
                ("simulated-codex",), 1, event + "\n", "", events=parse_external_agent_jsonl(event)
            )
        assert "Usage-limit continuation" in prompt
        assert "value = 1" in source.read_text(encoding="utf-8")
        return real_execute(prompt, config, **kwargs)

    cli._run_external_agent = execute
    execution_fallback.check_agent_readiness = lambda method: (
        AgentReadiness(True, "simulated initial account")
        if method is AccessMethod.CODEX_CLI
        else real_auth(method)
    )
    try:
        exit_code = cli.main(
            [
                "--mode",
                "implement",
                "Set value to 2 in source.py. Preserve existing comments. "
                "Run test_source.py to verify. Do not edit the test or other fixture files.",
                "--repo-root",
                str(artifact),
                "--catalog",
                str(catalog),
                "--route-id",
                "simulated-codex",
                "--privacy",
                "public_or_low_risk",
                "--cost-policy",
                "allowances_allowed",
                "--approval-policy",
                "trusted_local",
                "--skip-prompt-review",
                "--execute",
                "--timeout-seconds",
                "90",
                "--log-file",
                str(artifact / "assistant.log"),
            ]
        )
    finally:
        cli._run_external_agent = real_execute
        execution_fallback.check_agent_readiness = real_auth
    validation = subprocess.run((sys.executable, str(tests)), cwd=artifact, capture_output=True)
    passed = (
        exit_code == 0
        and validation.returncode == 0
        and tests.read_text(encoding="utf-8") == original_tests
        and "Partial work" in source.read_text(encoding="utf-8")
        and attempts == ["codex_cli", "copilot_cli"]
    )
    result = {
        "passed": passed,
        "simulated_initial_quota": True,
        "real_fallback": "copilot",
        "attempts": attempts,
        "exit_code": exit_code,
        "validation_exit_code": validation.returncode,
    }
    (artifact / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("fallback_acceptance: " + json.dumps(result))
    print(f"acceptance_artifacts: {artifact}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
