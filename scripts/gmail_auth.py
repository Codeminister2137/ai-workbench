"""Gmail send authorization (ADR-099 runtime slice 1): owned-class sends.

Deterministic recipient enforcement with a content-free local audit.
Owned-only envelopes (every To/Cc/Bcc recipient a verified owned
mailbox) send without per-message approval; anything else needs an
exact-message approval binding sender, recipients, subject, body and
attachments. No external automatic-send class exists.

Audit records carry operation IDs, UTC time, account reference, class,
rule/approval reference, verdict and fingerprints only: no subjects,
bodies, snippets, attachments, credentials or raw server replies.
Evidence persists before dispatch; an unavailable sink blocks sending.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import secrets
import sys
import time
from dataclasses import dataclass, field
from email.utils import getaddresses
from pathlib import Path
from typing import Protocol

HERE = Path(__file__).resolve().parent

RULE_OWNED = "owned-only/v1"
AUDIT_VERSION = 1


def _load_loop_notify():
    spec = importlib.util.spec_from_file_location("loop_notify_gmail", HERE / "loop_notify.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["loop_notify_gmail"] = module
    spec.loader.exec_module(module)
    return module


def owned_mailboxes() -> frozenset[str]:
    """Verified owned identities: the authenticated owner account only.

    No inference from domains, aliases, reply history or plus-addresses.
    Future company addresses join only after confirmed ownership (ADR-099).
    """
    config = _load_loop_notify().read_gmail_config()
    if config is None:
        return frozenset()
    return frozenset({config[0].strip().lower()})


@dataclass(frozen=True)
class Envelope:
    """Complete final transport envelope (reply-all/forwards resolved)."""

    sender: str
    to: tuple[str, ...] = ()
    cc: tuple[str, ...] = ()
    bcc: tuple[str, ...] = ()
    subject: str = ""
    body: str = ""
    attachments: tuple[tuple[str, str], ...] = ()

    def recipients(self) -> tuple[str, ...]:
        return self.to + self.cc + self.bcc


def parse_address_list(*headers: str) -> tuple[str, ...]:
    """Mail-aware address parsing; rejects injection and malformed entries."""
    for header in headers:
        if "\n" in header or "\r" in header:
            raise ValueError("header injection rejected")
    parsed = getaddresses(headers)
    addresses = []
    for _name, addr in parsed:
        addr = addr.strip().lower()
        if not addr:
            continue
        local, sep, domain = addr.partition("@")
        if not sep or not local or not domain or "." not in domain:
            raise ValueError(f"malformed recipient: {addr!r}")
        addresses.append(addr)
    return tuple(addresses)


def fingerprint(envelope: Envelope) -> str:
    """Stable payload fingerprint binding sender/recipients/subject/body/files."""
    canonical = json.dumps(
        {
            "sender": envelope.sender.strip().lower(),
            "recipients": sorted(envelope.recipients()),
            "subject": envelope.subject,
            "body": envelope.body,
            "attachments": sorted(envelope.attachments),
        },
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def authorize(envelope: Envelope, owned: frozenset[str]) -> tuple[str, str]:
    """Return (verdict, reason): owned auto-allow or approval-required."""
    recipients = envelope.recipients()
    if not recipients:
        return "deny", "empty recipient set"
    if envelope.sender.strip().lower() not in owned:
        return "deny", "unverified sending identity"
    if all(recipient in owned for recipient in recipients):
        return "allow", RULE_OWNED
    return "pending", "exact-message approval required"


@dataclass
class AuditSink:
    """Content-free JSON audit; every record atomic, evidence before dispatch."""

    directory: Path

    def record(self, entry: dict) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime(entry.get("utc", time.time())))
        target = self.directory / f"gmail-{stamp}-{secrets.token_hex(4)}.json"
        payload = {"audit_version": AUDIT_VERSION, **entry}
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        tmp.replace(target)
        return target


@dataclass
class ApprovalStore:
    """Exact-message approvals with revocation; persisted beside the audit."""

    directory: Path

    def _path(self, token: str) -> Path:
        return self.directory / f"approval-{token}.json"

    def approve(self, envelope: Envelope, *, approved_by: str) -> str:
        if not approved_by.strip():
            raise ValueError("approval requires an operator identity")
        token = secrets.token_hex(16)
        record = {
            "token": token,
            "approved_by": approved_by.strip(),
            "approved_at_utc": time.time(),
            "fingerprint": fingerprint(envelope),
            "recipient_count": len(envelope.recipients()),
            "revoked": False,
        }
        self.directory.mkdir(parents=True, exist_ok=True)
        self._path(token).write_text(json.dumps(record, indent=1), encoding="utf-8")
        return token

    def check(self, token: str, envelope: Envelope) -> tuple[bool, str]:
        path = self._path(token)
        if not path.is_file():
            return False, "unknown approval"
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("revoked"):
            return False, "approval revoked"
        if record.get("fingerprint") != fingerprint(envelope):
            return False, "payload changed since approval"
        return True, "exact-message approval"

    def revoke(self, token: str) -> bool:
        path = self._path(token)
        if not path.is_file():
            return False
        record = json.loads(path.read_text(encoding="utf-8"))
        record["revoked"] = True
        path.write_text(json.dumps(record, indent=1), encoding="utf-8")
        return True


class Transport(Protocol):
    def deliver(self, envelope: Envelope) -> str: ...


class UnknownOutcome(RuntimeError):
    """Transport submitted but the outcome is unknown; reconcile first."""


@dataclass
class GmailSender:
    audit: AuditSink
    approvals: ApprovalStore
    transport: Transport
    owned: frozenset[str] = field(default_factory=frozenset)
    account_ref: str = "gmail-owner"

    def send(
        self,
        envelope: Envelope,
        *,
        approval_token: str | None = None,
        dry_run: bool = True,
        op_id: str | None = None,
    ) -> dict:
        op_id = op_id or secrets.token_hex(8)
        verdict, reason = authorize(envelope, self.owned)
        rule_ref: str | None = None
        if verdict == "pending":
            if approval_token is None:
                return self._record(
                    op_id, envelope, "deny", "no exact-message approval", None, "refused"
                )
            ok, approval_reason = self.approvals.check(approval_token, envelope)
            if not ok:
                return self._record(op_id, envelope, "deny", approval_reason, None, "refused")
            verdict, reason = "allow", approval_reason
            rule_ref = f"approval:{approval_token[:8]}"
        else:
            rule_ref = reason if verdict == "allow" else None
        if verdict != "allow":
            return self._record(op_id, envelope, verdict, reason, None, "refused")
        try:
            self._record(op_id, envelope, verdict, reason, rule_ref, "attempt")
        except OSError as exc:
            return {"op_id": op_id, "verdict": "deny", "reason": f"audit unavailable: {exc}"}
        if dry_run:
            return self._record(op_id, envelope, verdict, reason, rule_ref, "dry-run")
        try:
            transport_result = self.transport.deliver(envelope)
        except UnknownOutcome as exc:
            return self._record(
                op_id, envelope, verdict, f"unknown outcome: {exc}", rule_ref, "unknown"
            )
        except Exception as exc:
            return self._record(
                op_id, envelope, verdict, f"transport failed: {exc}", rule_ref, "failed"
            )
        return self._record(op_id, envelope, verdict, reason, rule_ref, transport_result)

    def _record(
        self,
        op_id: str,
        envelope: Envelope,
        verdict: str,
        reason: str,
        rule_ref: str | None,
        transport_result: str,
    ) -> dict:
        recipients = envelope.recipients()
        entry = {
            "op_id": op_id,
            "utc": time.time(),
            "account_ref": self.account_ref,
            "class": "owned" if verdict == "allow" and rule_ref == RULE_OWNED else "external",
            "rule_ref": rule_ref,
            "verdict": verdict,
            "reason": reason,
            "transport_result": transport_result,
            "recipient_set_sha256": hashlib.sha256(
                ",".join(sorted(recipients)).encode()
            ).hexdigest(),
            "recipient_count": len(recipients),
            "payload_sha256": fingerprint(envelope),
        }
        path = self.audit.record(entry)
        return {**entry, "audit": path.name}
