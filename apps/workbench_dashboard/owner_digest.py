"""Durable, coordinated owner notification digest; no independent service."""

from __future__ import annotations

import hashlib
import sqlite3
import time
from pathlib import Path

INTERVAL = 3600
TIER_NEEDS_YOU = "needs-you"
TIER_DONE = "done"


class _BodyFull(Exception):
    """Internal stop: body budget reached after at least one entry."""


def _connect(data_dir: Path) -> sqlite3.Connection:
    data_dir.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(data_dir / "owner-digest.sqlite3", timeout=30)
    db.execute(
        "CREATE TABLE IF NOT EXISTS events (key TEXT PRIMARY KEY, subject TEXT, body TEXT, blocker INTEGER, created REAL, delivered INTEGER DEFAULT 0, tier TEXT DEFAULT 'done')"
    )
    columns = {row[1] for row in db.execute("PRAGMA table_info(events)").fetchall()}
    if "tier" not in columns:
        db.execute("ALTER TABLE events ADD COLUMN tier TEXT DEFAULT 'done'")
    db.execute("CREATE TABLE IF NOT EXISTS progress (id INTEGER PRIMARY KEY, last_sent REAL)")
    db.commit()
    db.execute("BEGIN IMMEDIATE")
    return db


def _coerce_tier(tier: object) -> str:
    """Fail-visible tier: unknown values surface, never bury."""
    return TIER_NEEDS_YOU if tier != TIER_DONE else TIER_DONE


def _one_line(body: str) -> str:
    """Compact a queued body to its outcome line for the done summary."""
    for line in (body or "").splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("outcome:"):
            return stripped
    for line in (body or "").splitlines():
        if line.strip():
            return " ".join(line.split())
    return "No details recorded."


def queue_notification(
    *,
    data_dir: Path,
    supervision: str,
    subject: str,
    body: str,
    config: dict,
    dedupe_key: str | None = None,
    blocker: bool = False,
    all_work_blocked: bool = False,
    tier: str = TIER_DONE,
) -> dict:
    """Enqueue once, including blockers first; only whole-window blockers page.

    Tiered policy (owner C on 716e02b3): needs-you pages send in any
    supervision mode; done summaries wait for unattended. Enqueueing
    always persists so attended pages have records to flush.
    """
    result = {"sent": False, "error": None, "finished": time.time()}
    key = dedupe_key or hashlib.sha256((subject + "\n" + body).encode()).hexdigest()
    db = _connect(data_dir)
    try:
        inserted = db.execute(
            "INSERT OR IGNORE INTO events(key,subject,body,blocker,created,tier) VALUES(?,?,?,?,?,?)",
            (key, subject, body, int(blocker), time.time(), _coerce_tier(tier)),
        ).rowcount
        delivered = db.execute("SELECT delivered FROM events WHERE key=?", (key,)).fetchone()[0]
        db.commit()
    finally:
        db.close()
    if not inserted and delivered:
        return dict(result, deduped=True)
    if blocker and all_work_blocked:
        return flush_digest(
            data_dir=data_dir, supervision=supervision, config=config, urgent_key=key
        )
    return dict(result, queued=True, deduped=not bool(inserted))


def flush_digest(
    *,
    data_dir: Path,
    supervision: str,
    config: dict,
    now: float | None = None,
    urgent_key: str | None = None,
) -> dict:
    """Flush due records atomically against other producers/ticks.

    Failed delivery leaves records pending. SMTP cannot guarantee exactly-once
    delivery if the process dies after acceptance but before committing progress.
    Attended mode pages needs-you/blocker rows immediately and leaves done
    summaries queued; unattended mode flushes the hourly batch as before.
    """
    result = {"sent": False, "error": None, "finished": time.time()}
    attended = supervision != "unattended"
    from owner_mail import MAX_BODY_CHARS, _send_owner_mail_now

    clock = time.time() if now is None else now
    db = _connect(data_dir)
    try:
        rows = db.execute(
            "SELECT key,subject,body,blocker,created,tier FROM events WHERE delivered=0 ORDER BY blocker DESC,created,key"
        ).fetchall()
        if not rows:
            return dict(result, pending=0)
        if attended:
            rows = [row for row in rows if row[3] or row[5] == TIER_NEEDS_YOU]
            if not rows:
                return dict(result, skipped="attended")
        last = db.execute("SELECT last_sent FROM progress WHERE id=1").fetchone()
        due = max(min(row[4] for row in rows), last[0] if last else 0) + INTERVAL
        if urgent_key:
            rows = [row for row in rows if row[0] == urgent_key and row[3]]
            if not rows:
                return dict(result, pending=0)
        elif not attended and clock < due:
            return dict(result, queued=True, due=due)
        needs = [row for row in rows if row[3] or row[5] == TIER_NEEDS_YOU]
        done = [row for row in rows if row not in needs]
        if any(row[3] for row in rows):
            verdict = "ASAP"
        elif needs:
            verdict = "soon"
        else:
            verdict = "relax"
        selected = []
        body = (
            f"Verdict: {verdict} — {len(needs)} need you, {len(done)} done. "
            f"{'Attended page' if attended else 'Unattended session updates'}:\n"
        )

        def append_entry(entry: str, key: str) -> None:
            nonlocal body
            if len(body) + len(entry) > MAX_BODY_CHARS:
                if selected:
                    raise _BodyFull
                entry = (
                    entry[: MAX_BODY_CHARS - len(body) - 40]
                    + "\n[See dashboard for full details]\n"
                )
            body += entry
            selected.append(key)

        try:
            if needs:
                body += "\n--- NEEDS YOU ---\n"
                for row in rows:
                    if row not in needs:
                        continue
                    append_entry(f"\n{'BLOCKER: ' if row[3] else ''}{row[1]}\n{row[2]}\n", row[0])
            if done:
                body += "\n--- DONE ---\n"
                for row in rows:
                    if row not in done:
                        continue
                    append_entry(f"\n- {row[1]} — {_one_line(row[2])}\n", row[0])
        except _BodyFull:
            pass
        receipt = _send_owner_mail_now(
            to=config["owner"],
            subject="[workbench] "
            + (
                "All work blocked"
                if urgent_key
                else (f"[{verdict}] Page" if attended else f"[{verdict}] Hourly digest")
            ),
            body=body,
            config=config,
            dry_run=False,
            receipts_dir=data_dir / "mail-receipts",
            dedupe_key="digest:" + hashlib.sha256("|".join(selected).encode()).hexdigest(),
        )
        if receipt["sent"]:
            db.executemany(
                "UPDATE events SET delivered=1 WHERE key=?", [(key,) for key in selected]
            )
            db.execute("INSERT OR REPLACE INTO progress VALUES(1,?)", (clock,))
            db.commit()
        return receipt
    finally:
        db.close()
