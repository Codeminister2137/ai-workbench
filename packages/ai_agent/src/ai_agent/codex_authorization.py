"""Codex CLI authorization mapping for local development tool diagnostics."""

from __future__ import annotations

from typing import Any

from ai_agent.authorization import (
    AuthorizationMethod,
    AuthorizationRegistry,
    AuthorizationState,
    CapabilityGrant,
    CredentialLocation,
    ServiceAuthorization,
)
from ai_agent.permissions import ApprovalPolicyPreset

CODEX_SERVICE_ID = "codex"


def codex_authorization_from_status(status: dict[str, Any]) -> ServiceAuthorization:
    """Build a secret-free Codex CLI authorization snapshot from diagnostics."""

    available = bool(status.get("available"))
    login_status = str(status.get("login_status") or "")
    state = _codex_authorization_state(available=available, login_status=login_status)
    plugin_summary = status.get("plugin_summary")
    mcp_list = status.get("mcp_list")

    return ServiceAuthorization(
        service_id=CODEX_SERVICE_ID,
        display_name="Codex CLI",
        state=state,
        method=AuthorizationMethod.CLI_SESSION if available else AuthorizationMethod.NONE,
        credential_location=CredentialLocation.LOCAL_CLI if available else CredentialLocation.NONE,
        capability=CapabilityGrant(
            read=available,
            write=available and state is AuthorizationState.AUTHORIZED,
            scopes=_codex_capability_scopes(
                available=available,
                plugin_summary=plugin_summary if isinstance(plugin_summary, dict) else None,
                mcp_list=mcp_list if isinstance(mcp_list, dict) else None,
            ),
            write_approval_policy=ApprovalPolicyPreset.INTERACTIVE,
            notes=(
                "Writes are limited to explicit Codex plugin install/remove, MCP registration, "
                "session persistence, and workspace-write executions gated by CLI flags and "
                "approval policy."
            ),
        ),
        diagnostic_summary=_codex_diagnostic_summary(
            available=available,
            state=state,
            exec_json_supported=bool(status.get("exec_json_supported")),
            plugin_summary=plugin_summary if isinstance(plugin_summary, dict) else None,
        ),
        reauthorize_hint=(
            "Run `codex login` or repair the local Codex CLI session."
            if available and state is not AuthorizationState.AUTHORIZED
            else None
        ),
    )


def codex_authorization_registry(status: dict[str, Any]) -> AuthorizationRegistry:
    """Return an authorization registry containing the local Codex CLI service."""

    registry = AuthorizationRegistry()
    registry.register(codex_authorization_from_status(status))
    return registry


def _codex_authorization_state(
    *,
    available: bool,
    login_status: str,
) -> AuthorizationState:
    if not available:
        return AuthorizationState.NOT_CONFIGURED

    normalized = login_status.lower()
    if "logged in" in normalized or "authenticated" in normalized:
        return AuthorizationState.AUTHORIZED
    if "not logged in" in normalized or "unauthorized" in normalized:
        return AuthorizationState.UNAUTHORIZED
    if "expired" in normalized:
        return AuthorizationState.EXPIRED
    if "error" in normalized or "failed" in normalized:
        return AuthorizationState.ERROR
    return AuthorizationState.UNKNOWN


def _codex_capability_scopes(
    *,
    available: bool,
    plugin_summary: dict[str, Any] | None,
    mcp_list: dict[str, Any] | None,
) -> tuple[str, ...]:
    if not available:
        return ()

    scopes = [
        "read:codex.command",
        "read:codex.login_status",
        "read:codex.config_path",
        "read:codex.exec_json_support",
        "read:codex.plugins",
        "read:codex.mcp_servers",
        "write:codex.workspace_execution",
        "write:codex.session_state",
        "write:codex.plugin_install_remove",
        "write:codex.mcp_registration",
    ]
    if plugin_summary is not None:
        scopes.append("read:codex.plugin_summary")
    if mcp_list is not None:
        scopes.append("read:codex.mcp_list")
    return tuple(scopes)


def _codex_diagnostic_summary(
    *,
    available: bool,
    state: AuthorizationState,
    exec_json_supported: bool,
    plugin_summary: dict[str, Any] | None,
) -> str:
    if not available:
        return "Codex CLI was not discovered."

    parts = [
        f"Codex CLI discovered; authorization state is {state.value}.",
        f"exec_json_supported={exec_json_supported}.",
    ]
    if plugin_summary is not None:
        parts.append(
            "plugins="
            f"{plugin_summary.get('installed_count', 0)}/"
            f"{plugin_summary.get('available_count', 0)} installed."
        )
    return " ".join(parts)
