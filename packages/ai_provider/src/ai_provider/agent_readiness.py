"""Secret-free native-client authentication checks; never run inference."""

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Any

from ai_orchestrator import AccessMethod

from ai_provider.external_agents import external_agent_command, run_diagnostic_command


@dataclass(frozen=True)
class AgentReadiness:
    ready: bool
    reason: str
    login_command: tuple[str, ...] = ()


def _copilot_authenticated(command: str, timeout: float) -> bool:
    """Read account auth with bounded framing and verified owned-tree cleanup."""
    from ai_provider.native_account_usage import read_native_account_usage

    report = read_native_account_usage(
        (command, "--headless", "--no-auto-update", "--log-level", "none", "--stdio"),
        source="copilot_auth_status",
        timeout_seconds=timeout,
        exchange=_exchange_copilot_auth,
    )
    return report["status"] == "available" and report["cleanup_verified"]


def _exchange_copilot_auth(process: subprocess.Popen[Any], deadline: float) -> list[dict[str, Any]]:
    from ai_provider.copilot_usage import _exchange_account_result

    result = _exchange_account_result(process, deadline, "auth.getStatus")
    if type(result.get("isAuthenticated")) is not bool:
        raise ValueError("Invalid authentication status")
    return [{"authenticated": True}] if result["isAuthenticated"] else []


def check_agent_readiness(method: AccessMethod, *, timeout: float = 15) -> AgentReadiness:
    """Check authentication without reading tokens or publishing account details."""

    command = external_agent_command(method)
    if command is None:
        return AgentReadiness(False, "official client is not installed/configured")
    if method is AccessMethod.COPILOT_CLI:
        login = (command, "login")
        if any(
            os.getenv(key)
            for key in (
                "COPILOT_PROVIDER_BASE_URL",
                "COPILOT_PROVIDER_API_KEY",
            )
        ):
            return AgentReadiness(False, "Copilot BYOK overrides subscription billing")
        try:
            ready = _copilot_authenticated(command, timeout)
        except OSError:
            ready = False
    elif method is AccessMethod.CODEX_CLI:
        login = (command, "login")
        result = run_diagnostic_command(command, "login", "status", timeout_seconds=timeout)
        ready = result["ok"] and "chatgpt" in (result["stdout"] + result["stderr"]).lower()
    elif method is AccessMethod.KIRO_CLI:
        login = (command, "login")
        result = run_diagnostic_command(
            command, "whoami", "--format", "json", timeout_seconds=timeout
        )
        try:
            identity = json.loads(result["stdout"])
            ready = (
                result["ok"] and isinstance(identity, dict) and bool(identity.get("accountType"))
            )
        except ValueError:
            ready = False
    elif method is AccessMethod.ANTIGRAVITY_CLI:
        login = (command,)
        if os.getenv("GEMINI_API_KEY"):
            return AgentReadiness(False, "Gemini API key may override subscription billing")
        result = run_diagnostic_command(command, "models", timeout_seconds=timeout)
        ready = result["ok"] and bool(result["stdout"])
    else:
        return AgentReadiness(False, "no native authentication check for this access method")
    return AgentReadiness(
        bool(ready), "authenticated" if ready else "sign-in needed or could not be verified", login
    )
