"""ADR-099 proving cases: fake transport + temporary private audit sink."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/gmail_auth.py"
spec = importlib.util.spec_from_file_location("gmail_auth", SCRIPT)
assert spec is not None
assert spec.loader is not None
auth = importlib.util.module_from_spec(spec)
sys.modules["gmail_auth"] = auth
spec.loader.exec_module(auth)

OWNER = "owner@example.com"
OWNED = frozenset({OWNER})
EXTERNAL = "client@example.org"


class FakeTransport:
    """Configurable stand-in for SMTP delivery. No network."""

    def __init__(self, result="sent"):
        self.result = result
        self.delivered = []

    def deliver(self, envelope):
        self.delivered.append(envelope)
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


@pytest.fixture
def sender(tmp_path):
    transport = FakeTransport()
    return auth.GmailSender(
        audit=auth.AuditSink(tmp_path / "audit"),
        approvals=auth.ApprovalStore(tmp_path / "approvals"),
        transport=transport,
        owned=OWNED,
    )


def _envelope(**overrides):
    args = {
        "sender": OWNER,
        "to": (OWNER,),
        "subject": "s",
        "body": "b",
    }
    args.update(overrides)
    return auth.Envelope(**args)


def test_owned_to_only_auto_allows(sender):
    result = sender.send(_envelope(), dry_run=False)
    assert result["verdict"] == "allow"
    assert result["transport_result"] == "sent"
    assert len(sender.transport.delivered) == 1


def test_owned_cc_bcc_and_reply_shapes_auto_allow(sender):
    envelope = _envelope(to=(OWNER,), cc=(OWNER,), bcc=(OWNER,))
    assert sender.send(envelope, dry_run=False)["verdict"] == "allow"
    reply = _envelope(to=(OWNER,), subject="Re: s")
    assert sender.send(reply, dry_run=False)["verdict"] == "allow"


def test_mixed_owned_external_requires_approval(sender):
    envelope = _envelope(to=(OWNER, EXTERNAL))
    refused = sender.send(envelope, dry_run=False)
    assert refused["verdict"] == "deny"
    assert sender.transport.delivered == []
    token = sender.approvals.approve(envelope, approved_by="owner")
    allowed = sender.send(envelope, approval_token=token, dry_run=False)
    assert allowed["verdict"] == "allow"


def test_lookalike_and_plus_aliases_are_not_owned(sender):
    for impostor in ("owner@gmai1.com", "owner+news@example.com", "Owner@Example.COMx"):
        envelope = _envelope(to=(impostor,))
        assert sender.send(envelope, dry_run=False)["verdict"] == "deny"
    assert sender.transport.delivered == []


def test_malformed_recipients_and_injection_rejected():
    with pytest.raises(ValueError):
        auth.parse_address_list("not-an-address")
    with pytest.raises(ValueError):
        auth.parse_address_list("a@b")
    with pytest.raises(ValueError):
        auth.parse_address_list(f"{OWNER}\nBcc: {EXTERNAL}")
    parsed = auth.parse_address_list(f"Me <{OWNER}>, {EXTERNAL}")
    assert parsed == (OWNER, EXTERNAL)


def test_reply_all_adding_external_loses_owned_class(sender):
    envelope = _envelope(to=(OWNER,), cc=(EXTERNAL,))
    result = sender.send(envelope, dry_run=False)
    assert result["verdict"] == "deny"


def test_exact_approval_binds_payload(sender):
    envelope = _envelope(to=(EXTERNAL,), subject="Quote", body="100")
    token = sender.approvals.approve(envelope, approved_by="owner")
    assert sender.send(envelope, approval_token=token, dry_run=False)["verdict"] == "allow"
    changed_subject = _envelope(to=(EXTERNAL,), subject="Quote!", body="100")
    assert sender.send(changed_subject, approval_token=token, dry_run=False)["verdict"] == "deny"
    changed_body = _envelope(to=(EXTERNAL,), subject="Quote", body="200")
    assert sender.send(changed_body, approval_token=token, dry_run=False)["verdict"] == "deny"
    changed_rcpt = _envelope(to=(EXTERNAL, OWNER), subject="Quote", body="100")
    assert sender.send(changed_rcpt, approval_token=token, dry_run=False)["verdict"] == "deny"


def test_revocation_blocks_send(sender):
    envelope = _envelope(to=(EXTERNAL,))
    token = sender.approvals.approve(envelope, approved_by="owner")
    assert sender.approvals.revoke(token) is True
    assert sender.send(envelope, approval_token=token, dry_run=False)["verdict"] == "deny"


def test_audit_failure_blocks_dispatch(sender, tmp_path):
    blocker = tmp_path / "file-not-dir"
    blocker.write_text("x", encoding="utf-8")
    sender.audit = auth.AuditSink(blocker)
    result = sender.send(_envelope(), dry_run=False)
    assert result["verdict"] == "deny"
    assert "audit unavailable" in result["reason"]
    assert sender.transport.delivered == []


def test_audit_records_are_content_and_secret_free(sender, tmp_path):
    secret = "app-password-SECRET-xyz"
    envelope = _envelope(subject="Secret subject", body=f"Body {secret}")
    sender.send(envelope, dry_run=False)
    for record_file in (tmp_path / "audit").glob("*.json"):
        text = record_file.read_text(encoding="utf-8")
        assert "Secret subject" not in text
        assert secret not in text
        record = json.loads(text)
        assert record["payload_sha256"]
        assert record["recipient_count"] == 1


def test_unknown_outcome_recorded_separately(sender):
    sender.transport.result = auth.UnknownOutcome("submitted, confirm lost")
    result = sender.send(_envelope(), dry_run=False)
    assert result["verdict"] == "allow"
    assert result["transport_result"] == "unknown"


def test_transport_failure_recorded_attempt_first(sender):
    sender.transport.result = TimeoutError("smtp down")
    result = sender.send(_envelope(), dry_run=False)
    assert result["transport_result"] == "failed"


def test_empty_recipients_and_unverified_sender_denied(sender):
    assert sender.send(_envelope(to=()), dry_run=False)["verdict"] == "deny"
    assert sender.send(_envelope(sender=EXTERNAL), dry_run=False)["verdict"] == "deny"
    assert sender.transport.delivered == []


def test_approval_requires_operator_identity(sender):
    with pytest.raises(ValueError):
        sender.approvals.approve(_envelope(to=(EXTERNAL,)), approved_by="  ")
