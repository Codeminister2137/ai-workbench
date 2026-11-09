"""Tests for the weekly digest one-shot (fetch, summarize, mail, receipt)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/weekly_digest.py"
spec = importlib.util.spec_from_file_location("weekly_digest", SCRIPT)
assert spec is not None
assert spec.loader is not None
weekly = importlib.util.module_from_spec(spec)
spec.loader.exec_module(weekly)


class FakeDigestError(Exception):
    pass


def _fake_digest(*, probe_ok=True, messages=None, summary=None, manual=None):
    seen = {}

    def fetch_latest(count, query="ALL"):
        seen.setdefault("queries", []).append(query)
        return list(messages or [])

    def summarize_with_proposals(msgs, manual_items):
        seen["proposals"] = True
        return dict(summary or {})

    stub = SimpleNamespace(
        DigestError=FakeDigestError,
        probe=lambda: (probe_ok, "ok" if probe_ok else "auth"),
        fetch_latest=fetch_latest,
        summarize_digest=lambda msgs: dict(summary or {}),
        summarize_with_proposals=summarize_with_proposals,
        read_manual_items=lambda manual_dir: list(manual or []),
    )
    stub.seen = seen
    return stub


def _fake_notify(*, success=True):
    calls = {}

    def send_ping(**kwargs):
        calls.update(kwargs)
        return {"success": success}

    return SimpleNamespace(send_ping=send_ping), calls


def test_dry_run_probes_and_fetches_without_send(tmp_path: Path) -> None:
    digest = _fake_digest(messages=[{"subject": "Hi", "snippet": "yo"}])
    notify, calls = _fake_notify()
    receipt = weekly.run(out_dir=tmp_path, dry_run=True, digest_module=digest, notify_module=notify)
    assert receipt["status"] == "skipped"
    assert receipt["reason"] == "dry-run"
    assert receipt["fetched"] == 1
    assert calls == {}
    assert json.loads(Path(receipt["receipt_path"]).read_text())["status"] == "skipped"


def test_full_cycle_mails_summary(tmp_path: Path) -> None:
    digest = _fake_digest(
        messages=[{"subject": "Hi", "snippet": "yo"}],
        summary={"summary": "One mail.", "model": "m", "estimated_usd": 0.001},
    )
    notify, calls = _fake_notify()
    receipt = weekly.run(out_dir=tmp_path, digest_module=digest, notify_module=notify)
    assert receipt["status"] == "mailed"
    assert receipt["estimated_usd"] == 0.001
    assert "One mail." in calls["body"]
    assert calls["event"] == "weekly-digest"


def test_probe_failure_skips_with_reason(tmp_path: Path) -> None:
    digest = _fake_digest(probe_ok=False)
    notify, calls = _fake_notify()
    receipt = weekly.run(out_dir=tmp_path, digest_module=digest, notify_module=notify)
    assert receipt["status"] == "skipped"
    assert receipt["reason"] == "probe-auth"
    assert calls == {}


def test_empty_inbox_skips_without_summarize(tmp_path: Path) -> None:
    seen = []
    digest = _fake_digest(messages=[])
    digest.summarize_digest = lambda msgs: seen.append(msgs) or {}
    notify, _ = _fake_notify()
    receipt = weekly.run(out_dir=tmp_path, digest_module=digest, notify_module=notify)
    assert receipt["reason"] == "empty-inbox"
    assert seen == []


def test_send_failure_marks_failed(tmp_path: Path) -> None:
    digest = _fake_digest(
        messages=[{"subject": "Hi", "snippet": "yo"}],
        summary={"summary": "s", "model": "m", "estimated_usd": 0.0},
    )
    notify, _ = _fake_notify(success=False)
    receipt = weekly.run(out_dir=tmp_path, digest_module=digest, notify_module=notify)
    assert receipt["status"] == "failed"


def test_registration_script_pins_weekly_task() -> None:
    text = (Path(__file__).resolve().parents[1] / "scripts/register-weekly-digest.ps1").read_text(
        encoding="utf-8"
    )
    assert "WorkbenchWeeklyDigest" in text
    assert "New-ScheduledTaskTrigger -Weekly" in text
    assert "weekly_digest.py" in text
    assert "Unregister-ScheduledTask" in text


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


def test_manual_items_trigger_proposals_path(tmp_path: Path) -> None:
    digest = _fake_digest(
        messages=[{"subject": "Hi", "snippet": "yo"}],
        manual=[{"subject": "Ad", "snippet": "look"}],
        summary={"summary": "S.", "model": "m", "estimated_usd": 0.001},
    )
    notify, calls = _fake_notify()
    receipt = weekly.run(out_dir=tmp_path, digest_module=digest, notify_module=notify)
    assert receipt["status"] == "mailed"
    assert receipt["manual"] == 1
    assert digest.seen.get("proposals") is True


def test_sources_config_fetches_per_sender(tmp_path: Path) -> None:
    digest = _fake_digest(messages=[{"subject": "Hi", "snippet": "yo"}])
    notify, calls = _fake_notify()
    (tmp_path / "digest-sources.json").write_text(
        json.dumps({"senders": ["news@example.com"], "per_sender": 2}), encoding="utf-8"
    )
    out_dir = tmp_path / "run"
    receipt = weekly.run(out_dir=out_dir, dry_run=True, digest_module=digest, notify_module=notify)
    assert receipt["status"] == "skipped"
    assert '(FROM "news@example.com")' in digest.seen.get("queries", [])
