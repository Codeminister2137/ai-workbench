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
    assert sent[0]["body"].index("owner decision") < sent[0]["body"].index("\nprogress")
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


def test_attended_queue_and_flush_cannot_deliver(mail, tmp_path):
    sent, clock, queue, _, config = mail
    result = digest.queue_notification(
        data_dir=tmp_path,
        supervision="attended",
        subject="blocked",
        body="b",
        config=config,
        blocker=True,
        all_work_blocked=True,
    )
    assert result["skipped"] == "attended"
    assert not (tmp_path / "owner-digest.sqlite3").exists()
    queue()
    clock[0] += 3600
    assert digest.flush_digest(data_dir=tmp_path, supervision="attended", config=config)["skipped"]
    assert not sent


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
