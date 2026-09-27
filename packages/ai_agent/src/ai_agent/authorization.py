"""Reusable authorization contracts for external tool and app integrations."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from ai_agent.permissions import ApprovalPolicyPreset


class AuthorizationState(StrEnum):
    """High-level authorization state for one external service."""

    UNKNOWN = "unknown"
    NOT_CONFIGURED = "not_configured"
    AUTHORIZED = "authorized"
    UNAUTHORIZED = "unauthorized"
    EXPIRED = "expired"
    ERROR = "error"


class AuthorizationMethod(StrEnum):
    """How a service is expected to prove user authorization."""

    NONE = "none"
    API_KEY = "api_key"
    OAUTH = "oauth"
    CLI_SESSION = "cli_session"
    APP_CONNECTOR = "app_connector"
    SERVICE_ACCOUNT = "service_account"


class CredentialLocation(StrEnum):
    """Where credentials or sessions are expected to live."""

    NONE = "none"
    ENVIRONMENT = "environment"
    LOCAL_CLI = "local_cli"
    LOCAL_CONFIG = "local_config"
    MANAGED_CONNECTOR = "managed_connector"
    SECRET_STORE = "secret_store"


@dataclass(frozen=True, slots=True)
class CapabilityGrant:
    """Read/write capability summary for one service or tool surface."""

    read: bool = False
    write: bool = False
    scopes: tuple[str, ...] = ()
    write_approval_policy: ApprovalPolicyPreset = ApprovalPolicyPreset.INTERACTIVE
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly, secret-free capability summary."""

        return {
            "read": self.read,
            "write": self.write,
            "scopes": list(self.scopes),
            "write_approval_policy": self.write_approval_policy.value,
            "notes": self.notes,
        }


@dataclass(frozen=True, slots=True)
class ServiceAuthorization:
    """Secret-free authorization snapshot for one external service."""

    service_id: str
    display_name: str
    state: AuthorizationState
    method: AuthorizationMethod
    credential_location: CredentialLocation
    capability: CapabilityGrant = field(default_factory=CapabilityGrant)
    account_label: str | None = None
    diagnostic_summary: str | None = None
    reauthorize_hint: str | None = None

    @property
    def authorized(self) -> bool:
        """Return whether the service is currently authorized."""

        return self.state is AuthorizationState.AUTHORIZED

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly snapshot that never includes credential values."""

        return {
            "service_id": self.service_id,
            "display_name": self.display_name,
            "state": self.state.value,
            "authorized": self.authorized,
            "method": self.method.value,
            "credential_location": self.credential_location.value,
            "capability": self.capability.to_dict(),
            "account_label": self.account_label,
            "diagnostic_summary": self.diagnostic_summary,
            "reauthorize_hint": self.reauthorize_hint,
        }


@dataclass(slots=True)
class AuthorizationRegistry:
    """In-memory registry of secret-free service authorization snapshots."""

    _services: dict[str, ServiceAuthorization] = field(default_factory=dict)

    def register(self, authorization: ServiceAuthorization) -> None:
        """Register or replace one service authorization snapshot."""

        self._services[authorization.service_id] = authorization

    def get(self, service_id: str) -> ServiceAuthorization | None:
        """Return one registered service authorization snapshot, if present."""

        return self._services.get(service_id)

    def list(self) -> tuple[ServiceAuthorization, ...]:
        """Return registered service authorizations ordered by service id."""

        return tuple(self._services[key] for key in sorted(self._services))

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly registry summary."""

        services = self.list()
        return {
            "service_count": len(services),
            "authorized_count": sum(1 for service in services if service.authorized),
            "services": [service.to_dict() for service in services],
        }
