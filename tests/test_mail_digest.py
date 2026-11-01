"""Offline checks for the local mail-digest slice; no network is used."""

import imaplib
import importlib.util
import json
from email.message import EmailMessage
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/mail_digest.py"
spec = importlib.util.spec_from_file_location("mail_digest", SCRIPT)
assert spec is not None
assert spec.loader is not None
digest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(digest)

CREDS = ("owner@example.com", "super-secret-pw")


def _plain_raw() -> bytes:
    msg = EmailMessage()
    msg["From"] = "Alice <alice@example.com>"
    msg["Date"] = "Sat, 1 Nov 2026 10:00:00 +0100"
    msg["Subject"] = "Plain hello"
    msg["Message-ID"] = "<plain-1@example.com>"
    msg.set_content("Hi there, see https://example.com/a for details.")
    return msg.as_bytes()


def _multipart_raw() -> bytes:
    msg = EmailMessage()
    msg["From"] = "Bob <bob@example.com>"
    msg["Date"] = "Sat, 1 Nov 2026 11:00:00 +0100"
    msg["Subject"] = "Multipart café update"
    msg["Message-ID"] = "<multi-2@example.com>"
    msg.set_content("Plain part with http://example.org/p inside.")
    msg.add_alternative("<html><body>HTML part https://example.net/h</body></html>")
    return msg.as_bytes()


class FakeIMAP4:
    """Configurable stand-in for imaplib.IMAP4_SSL. No network."""

    connect_error: type[BaseException] | None = None
    login_error: type[BaseException] | None = None
    mailbox: list[bytes] = []

    def __init__(self, host):
        self.host = host
        if FakeIMAP4.connect_error is not None:
            raise FakeIMAP4.connect_error("connect down")

    def login(self, user, password):
        self.user = user
        if FakeIMAP4.login_error is not None:
            raise FakeIMAP4.login_error("auth down")
        return "OK", [b"logged in"]

    def select(self, mailbox="INBOX", readonly=False):
        assert mailbox == "INBOX"
        return "OK", [str(len(FakeIMAP4.mailbox)).encode()]

    def search(self, charset, *criteria):
        ids = b" ".join(str(i + 1).encode() for i in range(len(FakeIMAP4.mailbox)))
        return "OK", [ids]

    def fetch(self, num, _spec):
        raw = FakeIMAP4.mailbox[int(num) - 1]
        return "OK", [(b"%s (RFC822 {%d})" % (num, len(raw)), raw)]

    def logout(self):
        return "OK", [b"bye"]


@pytest.fixture
def fake_imap(monkeypatch):
    FakeIMAP4.connect_error = None
    FakeIMAP4.login_error = None
    FakeIMAP4.mailbox = []
    monkeypatch.setattr(digest.imaplib, "IMAP4_SSL", FakeIMAP4)
    monkeypatch.setattr(digest, "read_gmail_config", lambda: CREDS)
    return FakeIMAP4


def test_probe_ok(fake_imap, capsys):
    assert digest.probe() == (True, "ok")
    assert digest.main(["--probe"]) == 0
    out = capsys.readouterr().out
    assert "PROBE_OK" in out
    assert CREDS[0] not in out
    assert CREDS[1] not in out


def test_probe_auth_fail(fake_imap, capsys):
    fake_imap.login_error = imaplib.IMAP4.error
    assert digest.probe() == (False, "auth")
    assert digest.main(["--probe"]) == 1
    out = capsys.readouterr().out
    assert "PROBE_FAIL auth" in out
    assert CREDS[1] not in out


def test_probe_network_fail(fake_imap, capsys):
    fake_imap.connect_error = OSError
    assert digest.probe() == (False, "network")
    assert digest.main(["--probe"]) == 1
    assert "PROBE_FAIL network" in capsys.readouterr().out


def test_probe_missing_credentials(monkeypatch, capsys):
    class NoNetwork:
        def __init__(self, host):
            raise AssertionError("must not touch the network without credentials")

    monkeypatch.setattr(digest.imaplib, "IMAP4_SSL", NoNetwork)
    monkeypatch.setattr(digest, "read_gmail_config", lambda: None)
    assert digest.probe() == (False, "missing-credentials")
    assert digest.main(["--probe"]) == 1
    assert "PROBE_FAIL missing-credentials" in capsys.readouterr().out


def test_fetch_parses_plain_and_multipart(fake_imap, tmp_path):
    fake_imap.mailbox = [_plain_raw(), _multipart_raw()]
    messages = digest.fetch_latest(5)
    assert len(messages) == 2
    # Newest first.
    multi, plain = messages
    assert multi["from"] == "Bob <bob@example.com>"
    assert multi["subject"] == "Multipart café update"
    assert multi["message-id"] == "<multi-2@example.com>"
    assert "2026" in multi["date"]
    assert "Plain part" in multi["snippet"]
    assert "http://example.org/p" in multi["urls"]
    assert plain["subject"] == "Plain hello"
    assert plain["message-id"] == "<plain-1@example.com>"
    assert plain["urls"] == ["https://example.com/a"]
    assert "Hi there" in plain["snippet"]

    out = tmp_path / "digest.json"
    assert digest.main(["--fetch", "2", "--out", str(out)]) == 0
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert [m["message-id"] for m in saved] == ["<multi-2@example.com>", "<plain-1@example.com>"]


def test_fetch_latest_n_newest_first(fake_imap):
    raws = []
    for i in range(3):
        msg = EmailMessage()
        msg["From"] = f"sender-{i}@example.com"
        msg["Subject"] = f"note {i}"
        msg["Message-ID"] = f"<m{i}@example.com>"
        msg.set_content(f"body {i}")
        raws.append(msg.as_bytes())
    fake_imap.mailbox = raws
    messages = digest.fetch_latest(2)
    assert [m["message-id"] for m in messages] == ["<m2@example.com>", "<m1@example.com>"]


def test_fetch_missing_credentials(monkeypatch, tmp_path, capsys):
    class NoNetwork:
        def __init__(self, host):
            raise AssertionError("must not touch the network without credentials")

    monkeypatch.setattr(digest.imaplib, "IMAP4_SSL", NoNetwork)
    monkeypatch.setattr(digest, "read_gmail_config", lambda: None)
    with pytest.raises(digest.DigestError, match="missing-credentials"):
        digest.fetch_latest(3)
    out = tmp_path / "digest.json"
    assert digest.main(["--fetch", "3", "--out", str(out)]) == 1
    assert "FETCH_FAIL missing-credentials" in capsys.readouterr().out
    assert not out.exists()


def test_fetch_auth_fail_prints_no_secrets(fake_imap, tmp_path, capsys):
    fake_imap.login_error = imaplib.IMAP4.error
    out = tmp_path / "digest.json"
    assert digest.main(["--fetch", "1", "--out", str(out)]) == 1
    printed = capsys.readouterr().out
    assert "FETCH_FAIL auth" in printed
    assert CREDS[1] not in printed


def _ai_stubs():
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages/ai_provider/src"))
    from ai_provider.contracts import (
        AIMessage,
        AIResponse,
        BackendInfo,
        BackendLocation,
        MessageRole,
        ModelCapabilities,
        PrivacyClass,
        UsageMetadata,
        UsageSource,
    )

    return (
        AIMessage,
        AIResponse,
        BackendInfo,
        BackendLocation,
        MessageRole,
        ModelCapabilities,
        PrivacyClass,
        UsageMetadata,
        UsageSource,
    )


class _FakeClient:
    def __init__(self, text="- item needs a reply", finish="stop"):
        makers = _ai_stubs()
        self.requests = []
        self._text = text
        self._finish = finish
        self._makers = makers

    def complete(self, request):
        (
            AIMessage,
            AIResponse,
            BackendInfo,
            BackendLocation,
            MessageRole,
            ModelCapabilities,
            PrivacyClass,
            UsageMetadata,
            UsageSource,
        ) = self._makers
        self.requests.append(request)
        return AIResponse(
            message=AIMessage(MessageRole.ASSISTANT, self._text),
            backend=BackendInfo(
                provider="meta",
                model="muse-spark-1.3",
                location=BackendLocation.EXTERNAL,
                base_url="https://example.invalid",
                capabilities=ModelCapabilities(),
            ),
            finish_reason=self._finish,
            usage=UsageMetadata(
                source=UsageSource.PROVIDER_REPORTED,
                input_tokens=10000,
                output_tokens=500,
                total_tokens=10500,
            ),
        )


def test_summarize_reports_usage_and_cost():
    makers = _ai_stubs()
    PrivacyClass = makers[6]
    client = _FakeClient()
    result = digest.summarize_digest(
        [{"subject": "Hi", "snippet": "please reply"}],
        client=client,
    )
    (request,) = client.requests
    assert request.model == "muse-spark-1.3"
    assert request.max_output_tokens == digest.SUMMARY_MAX_OUTPUT_TOKENS
    assert request.privacy_class is PrivacyClass.EXTERNAL_ALLOWED
    assert result["summary"] == "- item needs a reply"
    assert result["input_tokens"] == 10000
    assert result["output_tokens"] == 500
    assert result["estimated_usd"] == round((10000 * 1.25 + 500 * 4.25) / 1_000_000, 6)


def test_summarize_refuses_empty_and_oversize():
    with pytest.raises(digest.DigestError, match="empty-digest"):
        digest.summarize_digest([], client=_FakeClient())
    big = [{"subject": "s", "snippet": "x" * (digest.MAX_SUMMARY_CHARS + 1)}]
    with pytest.raises(digest.DigestError, match="digest-too-large"):
        digest.summarize_digest(big, client=_FakeClient())


def test_summarize_missing_key(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(digest, "_meta_api_key", lambda: None)
    with pytest.raises(digest.DigestError, match="missing-meta-key"):
        digest.summarize_digest([{"subject": "s", "snippet": "b"}])
    src = tmp_path / "digest.json"
    src.write_text(json.dumps([{"subject": "s", "snippet": "b"}]), encoding="utf-8")
    out = tmp_path / "summary.json"
    assert digest.main(["--summarize", str(src), "--out", str(out)]) == 1
    assert "SUMMARIZE_FAIL missing-meta-key" in capsys.readouterr().out
    assert not out.exists()


def test_summarize_cli_roundtrip(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(digest, "_summary_client", lambda: _FakeClient("done"))
    src = tmp_path / "digest.json"
    src.write_text(json.dumps([{"subject": "s", "snippet": "b"}]), encoding="utf-8")
    out = tmp_path / "summary.json"
    assert digest.main(["--summarize", str(src), "--out", str(out)]) == 0
    assert "SUMMARIZE_OK 0.014625" in capsys.readouterr().out
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["summary"] == "done"
    assert saved["model"] == "muse-spark-1.3"


def test_summarize_truncated_is_an_error():
    client = _FakeClient("", finish="length")
    with pytest.raises(digest.DigestError, match="summary-truncated"):
        digest.summarize_digest([{"subject": "s", "snippet": "b"}], client=client)
