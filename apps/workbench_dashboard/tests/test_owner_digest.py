"""Offline policy, persistence, cadence and delivery recovery proofs."""

import sqlite3

import owner_digest as digest
import owner_mail
import pytest


@pytest.fixture
def mail(tmp_path, monkeypatch):
    sent = []
    clock = [10000.0]
    monkeypatch.setattr(digest.time, "time", lambda: clock[0])

    def deliver(**kwargs):
        sent.append(kwargs)
        return {"sent": True, "error": None}

    monkeypatch.setattr(owner_mail, "_send_owner_mail_now", deliver)
    config = {"owner": "owner@example.test"}

    def queue(subject="progress", **kwargs):
        return digest.queue_notification(
            data_dir=tmp_path,
            supervision="unattended",
            subject=subject,
            body=subject,
            config=config,
            **kwargs,
        )

    def flush(**kwargs):
        return digest.flush_digest(
            data_dir=tmp_path, supervision="unattended", config=config, **kwargs
        )

    return sent, clock, queue, flush, config


def test_hourly_quiet_flush_restart_and_blocker_priority(mail):
    sent, clock, queue, flush, _ = mail
    assert queue()["queued"]
    queue("owner decision", blocker=True)
    assert not flush()["sent"]
    clock[0] += 3599
    assert not flush()["sent"]
    clock[0] += 1
    assert flush()["sent"]
    assert sent[0]["body"].index("owner decision") < sent[0]["body"].index("--- DONE ---")
    assert not flush()["sent"]
    assert queue()["deduped"]  # durable keys survive new connections
    queue("closeout")
    assert not flush()["sent"]
    clock[0] += 3600
    assert flush()["sent"]
    assert len(sent) == 2


def test_only_confirmed_whole_window_blocker_bypasses(mail):
    sent, _, queue, _, _ = mail
    queue("one failed task", blocker=True)
    queue("sleep", all_work_blocked=True)
    assert not sent
    assert queue("all blocked", blocker=True, all_work_blocked=True)["sent"]
    assert queue("all blocked", blocker=True, all_work_blocked=True)["deduped"]
    assert len(sent) == 1


def test_attended_holds_routine_alerts_for_periodic_status(mail, tmp_path):
    sent, clock, queue, _, config = mail
    queued = digest.queue_notification(
        data_dir=tmp_path,
        supervision="attended",
        subject="done work",
        body="Outcome: done",
        config=config,
    )
    assert queued["queued"]
    assert (tmp_path / "owner-digest.sqlite3").exists()
    assert (
        digest.flush_digest(data_dir=tmp_path, supervision="attended", config=config)["skipped"]
        == "attended"
    )
    assert not sent
    digest.queue_notification(
        data_dir=tmp_path,
        supervision="attended",
        subject="need decision",
        body="b",
        config=config,
        tier="needs-you",
    )
    queue("one failed task", blocker=True)
    clock[0] += 3600
    page = digest.flush_digest(data_dir=tmp_path, supervision="attended", config=config)
    assert page["skipped"] == "attended"
    assert not sent
    queue()
    clock[0] += 3600
    batch = digest.flush_digest(data_dir=tmp_path, supervision="unattended", config=config)
    assert batch["sent"]
    assert "done work" in sent[0]["body"]
    assert "need decision" in sent[0]["body"]
    assert "one failed task" in sent[0]["body"]
    assert "Hourly digest" in sent[0]["subject"]


def test_attended_whole_window_blocker_pages_immediately(mail, tmp_path):
    sent, _, _, _, config = mail
    result = digest.queue_notification(
        data_dir=tmp_path,
        supervision="attended",
        subject="blocked",
        body="b",
        config=config,
        blocker=True,
        all_work_blocked=True,
    )
    assert result["sent"]
    assert len(sent) == 1


def test_delivery_failure_preserves_pending(mail, monkeypatch):
    sent, clock, queue, flush, _ = mail
    queue()
    clock[0] += 3600
    original = owner_mail._send_owner_mail_now
    monkeypatch.setattr(
        owner_mail, "_send_owner_mail_now", lambda **kw: {"sent": False, "error": "down"}
    )
    assert flush()["error"] == "down"
    monkeypatch.setattr(owner_mail, "_send_owner_mail_now", original)
    assert flush()["sent"]
    assert len(sent) == 1


def test_wrapper_coordinates_producers_and_limits_body(mail, tmp_path):
    sent, clock, _, flush, config = mail
    for index in range(3):
        assert owner_mail.send_owner_mail(
            to=config["owner"],
            subject=str(index),
            body="x" * 49000,
            config=config,
            dry_run=False,
            receipts_dir=tmp_path,
            data_dir=tmp_path,
            supervision="unattended",
        )["queued"]
    clock[0] += 3600
    flush()
    assert len(sent[0]["body"]) <= owner_mail.MAX_BODY_CHARS
    with sqlite3.connect(tmp_path / "owner-digest.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM events WHERE delivered=0").fetchone()[0] == 2


def test_concurrent_flushes_send_once(mail):
    from concurrent.futures import ThreadPoolExecutor

    sent, clock, queue, flush, _ = mail
    queue()
    clock[0] += 3600
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: flush(), range(2)))
    assert sum(bool(result["sent"]) for result in results) == 1
    assert len(sent) == 1


def test_shared_root_resolves_linked_worktree(tmp_path):
    main = tmp_path / "main"
    git_dir = main / ".git/worktrees/linked"
    git_dir.mkdir(parents=True)
    (git_dir / "commondir").write_text("../..")
    linked = tmp_path / "linked"
    linked.mkdir()
    (linked / ".git").write_text(f"gitdir: {git_dir.as_posix()}")
    assert owner_mail.shared_mail_root(linked) == main


def test_failed_urgent_delivery_can_retry_without_false_success(mail, monkeypatch):
    sent, _, queue, _, _ = mail
    original = owner_mail._send_owner_mail_now
    monkeypatch.setattr(
        owner_mail, "_send_owner_mail_now", lambda **kw: {"sent": False, "error": "down"}
    )
    assert queue("urgent", blocker=True, all_work_blocked=True)["error"] == "down"
    monkeypatch.setattr(owner_mail, "_send_owner_mail_now", original)
    assert queue("urgent", blocker=True, all_work_blocked=True)["sent"]
    assert len(sent) == 1


def test_verdict_tiers_blocker_soon_relax(mail):
    """Digest v2: ASAP on blockers, soon on needs-you, relax on done-only."""
    sent, clock, queue, flush, _ = mail
    queue("nightly sweep done")
    clock[0] += 3601
    assert flush()["sent"]
    assert sent[0]["body"].startswith("Verdict: relax — 0 need you, 1 done.")
    assert "[relax]" in sent[0]["subject"]
    queue("run failed", tier="needs-you")
    clock[0] += 3601
    assert flush()["sent"]
    assert sent[1]["body"].startswith("Verdict: soon — 1 need you, 0 done.")
    assert "[soon]" in sent[1]["subject"]
    queue("owner decision needed", blocker=True)
    clock[0] += 3601
    assert flush()["sent"]
    assert sent[2]["body"].startswith("Verdict: ASAP — 1 need you, 0 done.")
    assert "[ASAP]" in sent[2]["subject"]
    assert "BLOCKER: owner decision needed" in sent[2]["body"]


def test_unknown_tier_fails_visible(mail):
    sent, clock, queue, flush, _ = mail
    queue("mystery event", tier="nonsense")
    clock[0] += 3601
    assert flush()["sent"]
    assert "Verdict: soon" in sent[0]["body"]
    assert "--- NEEDS YOU ---" in sent[0]["body"]


def test_legacy_schema_migrates_with_done_backfill(mail, tmp_path):
    """Pre-tier databases gain the column; old rows flush as done."""
    sent, clock, _, flush, config = mail
    db = sqlite3.connect(tmp_path / "owner-digest.sqlite3")
    db.execute(
        "CREATE TABLE events (key TEXT PRIMARY KEY, subject TEXT, body TEXT, blocker INTEGER, created REAL, delivered INTEGER DEFAULT 0)"
    )
    db.execute(
        "INSERT INTO events(key,subject,body,blocker,created) VALUES(?,?,?,?,?)",
        ("legacy", "old progress", "old progress", 0, 10000.0),
    )
    db.commit()
    db.close()
    clock[0] += 3601
    assert flush()["sent"]
    assert "Verdict: relax" in sent[0]["body"]
    assert "- old progress — old progress" in sent[0]["body"]


def test_golden_digest_rendering(mail, tmp_path):
    """Golden v2 digest: verdict, tiered sections, compact done lines."""
    sent, clock, _, flush, config = mail

    def queue_body(subject, body, **kwargs):
        return digest.queue_notification(
            data_dir=tmp_path,
            supervision="unattended",
            subject=subject,
            body=body,
            config=config,
            **kwargs,
        )

    queue_body(
        "Blocked: approve deploy",
        "Stopped for owner input: approve deploy.\nNext: inbox:abc123.",
        blocker=True,
    )
    queue_body(
        "Failed: night sweep",
        "Failed\nTitle: night sweep\nOutcome: Could not complete: night sweep.\nNext: Triage queued; inbox:def456.",
        tier="needs-you",
    )
    queue_body(
        "Done: docs pass",
        "Done\nTitle: docs pass\nOutcome: Completed: docs pass.\nNext: Merged as abc1234.",
    )
    clock[0] += 3601
    assert flush()["sent"]
    assert sent[0]["subject"] == "[workbench] [ASAP] Hourly digest"
    assert sent[0]["body"] == (
        "Verdict: ASAP — 2 need you, 1 done. Unattended session updates:\n"
        "\n--- NEEDS YOU ---\n"
        "\nBLOCKER: Blocked: approve deploy\n"
        "Stopped for owner input: approve deploy.\nNext: inbox:abc123.\n"
        "\nFailed: night sweep\n"
        "Failed\nTitle: night sweep\nOutcome: Could not complete: night sweep.\nNext: Triage queued; inbox:def456.\n"
        "\n--- DONE ---\n"
        "\n- Done: docs pass — Outcome: Completed: docs pass.\n"
    )
