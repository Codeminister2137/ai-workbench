"""Run-level subagent fan-out policy.

Leaf module with stdlib-only imports, so every child-spawn entry point can
enforce the policy without import cycles.
"""

from __future__ import annotations

from enum import StrEnum


class FanoutPolicy(StrEnum):
    """Run-level child-spawn policy. Enforceable, never advisory.

    Both RESTRICTED and DENIED refuse every child spawn; they differ in
    provenance, not in force. RESTRICTED is a run-context limit (for example
    an unattended run that must not fan out), while DENIED records an
    explicit owner prohibition. The distinction is preserved so the run
    record and user-visible indicator can show why fan-out is off.
    """

    ALLOWED = "allowed"
    RESTRICTED = "restricted"
    DENIED = "denied"

    @classmethod
    def coerce(cls, value: FanoutPolicy | str) -> FanoutPolicy:
        """Normalize host configuration; refuse unknown values instead of guessing."""
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            valid = ", ".join(item.value for item in cls)
            raise ValueError(
                f"Unknown fan-out policy: {value!r} (expected one of: {valid})"
            ) from None

    @property
    def allows_spawn(self) -> bool:
        return self is FanoutPolicy.ALLOWED


_FANOUT_RESTRICTIVENESS = {
    FanoutPolicy.ALLOWED: 0,
    FanoutPolicy.RESTRICTED: 1,
    FanoutPolicy.DENIED: 2,
}


def resolve_fanout_policy(
    configured: FanoutPolicy | str,
    parent_effective: FanoutPolicy | str | None = None,
) -> FanoutPolicy:
    """Resolve the effective policy: configured, never wider than the parent grant."""
    effective = FanoutPolicy.coerce(configured)
    if parent_effective is None:
        return effective
    parent = FanoutPolicy.coerce(parent_effective)
    if _FANOUT_RESTRICTIVENESS[parent] > _FANOUT_RESTRICTIVENESS[effective]:
        return parent
    return effective
