"""--vacancies batch mode: resolve-on-outreach with a vendor-consult cap.

Pipeline A (inbox 49c94683-A): a JSONL vacancy batch resolves to
recipients through the contact registry (manual first, then ready
vendors) before the normal preview/approval loop. Manual hits are
free; vendor consults stop at --max-enriches. Every vacancy is
reported: queued, unresolved, malformed, or skipped on budget. All
fixtures are synthetic; the stub vendor never touches the network.
"""

from __future__ import annotations

import outreach_cli as cli
import pytest
from contacts import ContactProposal, ContactRegistry, ManualContactSource


class StubVendor:
    name = "stub"

    def __init__(self, email=None):
        self.email = email
        self.calls = []

    def resolve(self, vacancy):
        self.calls.append(vacancy.id)
        if self.email is None:
            return None
        return ContactProposal(email=self.email, source="stub:fake", verified=True)


@pytest.fixture
def batch_env(monkeypatch, tmp_path):
    attachment = tmp_path / "cv.pdf"
    attachment.write_bytes(b"reviewed CV")
    monkeypatch.setenv("CV_ATTACHMENT", str(attachment))
    monkeypatch.setenv("SENT_FILE", str(tmp_path / "sent.txt"))
    monkeypatch.setenv("RECORDS_FILE", str(tmp_path / "records.jsonl"))
    monkeypatch.setenv("GMAIL_EMAIL", "")
    monkeypatch.setenv("GMAIL_PASSWORD", "")
    monkeypatch.setattr("builtins.input", lambda *args: pytest.fail("Preview asked for approval"))
    return tmp_path


def _write(path, lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def _stub_registry(monkeypatch, email):
    vendor = StubVendor(email)
    registry = ContactRegistry([ManualContactSource(), vendor])
    monkeypatch.setattr(cli, "default_contact_registry", lambda: registry)
    return vendor


def test_batch_queues_manual_and_vendor_hits(batch_env, monkeypatch, capsys):
    vendor = _stub_registry(monkeypatch, "ana@example.invalid")
    path = _write(
        batch_env / "vac.jsonl",
        [
            '{"id": "v-manual", "company": "Acme", "contact_email": "bo@example.invalid"}',
            '{"id": "v-vendor", "company": "Globex", "recruiter_name": "Ana Example"}',
        ],
    )
    assert cli.main(["--vacancies", path]) == 0
    out = capsys.readouterr().out
    assert "vac:v-manual -> bo@example.invalid (via manual (free))." in out
    assert "vac:v-vendor -> ana@example.invalid (via stub:fake)." in out
    assert "2 total, 2 queued, 0 unresolved, 0 malformed, 0 skipped on budget" in out
    assert "1/25 vendor consults" in out
    # Manual hit never consulted the vendor; both recipients previewed.
    assert vendor.calls == ["v-vendor"]
    assert "To: bo@example.invalid" in out
    assert "To: ana@example.invalid" in out


def test_max_enriches_stops_vendor_consults(batch_env, monkeypatch, capsys):
    vendor = _stub_registry(monkeypatch, "ana@example.invalid")
    path = _write(
        batch_env / "vac.jsonl",
        [
            '{"id": "v-one", "company": "Acme"}',
            '{"id": "v-two", "company": "Globex"}',
            '{"id": "v-three", "company": "Initech"}',
        ],
    )
    assert cli.main(["--vacancies", path, "--max-enriches", "1"]) == 0
    out = capsys.readouterr().out
    assert "vac:v-one -> ana@example.invalid" in out
    assert "vac:v-two" not in out and "vac:v-three" not in out
    assert "3 total, 1 queued, 0 unresolved, 0 malformed, 2 skipped on budget" in out
    assert "1/1 vendor consults" in out
    assert vendor.calls == ["v-one"]


def test_unresolved_and_malformed_are_reported_not_dropped(batch_env, monkeypatch, capsys):
    _stub_registry(monkeypatch, None)
    path = _write(
        batch_env / "vac.jsonl",
        [
            '{"id": "v-none", "company": "Acme"}',
            "not json at all",
            '{"id": "v-nocompany"}',
        ],
    )
    assert cli.main(["--vacancies", path]) == 0
    out = capsys.readouterr().out
    assert "vac:v-none: unresolved (tried: manual, stub)." in out
    assert "vacancies:2: malformed JSON; skipped." in out
    assert "vacancies:3: needs 'id' and 'company'; skipped." in out
    assert "3 total, 0 queued, 1 unresolved, 2 malformed, 0 skipped on budget" in out


def test_missing_vacancies_file_fails(batch_env, capsys):
    missing = str(batch_env / "nope.jsonl")
    assert cli.main(["--vacancies", missing]) == 1
    assert f"Cannot read vacancies file {missing}" in capsys.readouterr().out


def test_needs_recipients_or_vacancies(batch_env):
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert exc.value.code == 2


def test_explicit_recipients_still_work_alone(batch_env, capsys):
    assert cli.main(["recruiter@example.invalid"]) == 0
    assert "To: recruiter@example.invalid" in capsys.readouterr().out
