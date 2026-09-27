from __future__ import annotations

from ai_agent import (
    ApprovalPolicyPreset,
    AuthorizationMethod,
    AuthorizationRegistry,
    AuthorizationState,
    CapabilityGrant,
    CredentialLocation,
    ServiceAuthorization,
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
