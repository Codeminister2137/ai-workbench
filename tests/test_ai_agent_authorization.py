from __future__ import annotations

from ai_agent import (
    ApprovalPolicyPreset,
    AuthorizationMethod,
    AuthorizationRegistry,
    AuthorizationState,
    CapabilityGrant,
    CredentialLocation,
    ServiceAuthorization,
    codex_authorization_from_status,
    codex_authorization_registry,
)


def test_service_authorization_to_dict_is_secret_free() -> None:
    authorization = ServiceAuthorization(
        service_id="github",
        display_name="GitHub",
        state=AuthorizationState.AUTHORIZED,
        method=AuthorizationMethod.OAUTH,
        credential_location=CredentialLocation.MANAGED_CONNECTOR,
        capability=CapabilityGrant(
            read=True,
            write=False,
            scopes=("repo:read",),
            write_approval_policy=ApprovalPolicyPreset.INTERACTIVE,
            notes="Writes disabled until explicitly approved.",
        ),
        account_label="octocat",
        diagnostic_summary="Authorized through managed connector.",
        reauthorize_hint="Reconnect GitHub if repository access fails.",
    )

    payload = authorization.to_dict()

    assert payload["authorized"] is True
    assert payload["capability"]["read"] is True
    assert payload["capability"]["write"] is False
    assert payload["capability"]["write_approval_policy"] == "interactive"
    assert "token" not in repr(payload).lower()
    assert "secret" not in repr(payload).lower()


def test_authorization_registry_summarizes_services() -> None:
    registry = AuthorizationRegistry()
    registry.register(
        ServiceAuthorization(
            service_id="codex",
            display_name="Codex CLI",
            state=AuthorizationState.AUTHORIZED,
            method=AuthorizationMethod.CLI_SESSION,
            credential_location=CredentialLocation.LOCAL_CLI,
        )
    )
    registry.register(
        ServiceAuthorization(
            service_id="github",
            display_name="GitHub",
            state=AuthorizationState.NOT_CONFIGURED,
            method=AuthorizationMethod.OAUTH,
            credential_location=CredentialLocation.MANAGED_CONNECTOR,
        )
    )

    summary = registry.to_dict()

    assert summary["service_count"] == 2
    assert summary["authorized_count"] == 1
    assert [service["service_id"] for service in summary["services"]] == ["codex", "github"]
    assert registry.get("missing") is None


def test_codex_authorization_maps_logged_in_cli_status() -> None:
    authorization = codex_authorization_from_status(
        {
            "available": True,
            "command": "codex",
            "version": "codex-cli 0.137.0",
            "login_status": "Logged in using ChatGPT",
            "exec_json_supported": True,
            "config_path": "C:\\codex\\config.toml",
            "mcp_list": {"ok": True, "stdout": "repo_assistant_tools", "stderr": ""},
            "plugin_summary": {
                "marketplaces": ["openai-curated"],
                "available_count": 65,
                "installed_count": 5,
                "plugins": [],
            },
        }
    )

    payload = authorization.to_dict()

    assert payload["service_id"] == "codex"
    assert payload["state"] == "authorized"
    assert payload["authorized"] is True
    assert payload["method"] == "cli_session"
    assert payload["credential_location"] == "local_cli"
    assert payload["capability"]["read"] is True
    assert payload["capability"]["write"] is True
    assert "read:codex.plugins" in payload["capability"]["scopes"]
    assert "write:codex.plugin_install_remove" in payload["capability"]["scopes"]
    assert payload["capability"]["write_approval_policy"] == "interactive"
    assert "token" not in repr(payload).lower()
    assert "secret" not in repr(payload).lower()


def test_codex_authorization_maps_missing_cli_as_not_configured() -> None:
    registry = codex_authorization_registry(
        {
            "available": False,
            "command": None,
            "login_status": "unavailable",
            "exec_json_supported": False,
            "plugin_summary": None,
            "mcp_list": None,
        }
    )

    service = registry.get("codex")
    assert service is not None
    assert service.state is AuthorizationState.NOT_CONFIGURED
    assert service.method is AuthorizationMethod.NONE
    assert service.credential_location is CredentialLocation.NONE
    assert service.capability.read is False
    assert service.capability.write is False
