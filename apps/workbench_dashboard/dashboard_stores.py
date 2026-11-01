"""File-backed JSON stores for plans, runs, and the owner-task inbox.

Dashboard v1 reads plans/runs created by existing Workbench flows and owns
only chat transcripts plus inbox answers. Everything lives under the
dashboard data directory (gitignored); responses are size-bounded.
"""

from __future__ import annotations

import json
import secrets
import uuid
from datetime import UTC, datetime
from pathlib import Path

MAX_RESPONSE_BYTES = 100_000
MAX_OPEN_TASKS = 50
INBOX_TYPES = ("decision", "clarification")
INBOX_STATUSES = ("open", "answered", "closed")


class StoreError(ValueError):
    """A store refusal safe to report to the dashboard caller."""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _read_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise StoreError(f"Stored file is not valid JSON: {path.name}") from exc
    if not isinstance(payload, dict):
        raise StoreError(f"Stored file must hold a JSON object: {path.name}")
    return payload


class JsonCollection:
    """One directory of `{id}.json` files with newest-first listing."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def _ensure(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)

    def list(self, *, limit: int = 20, offset: int = 0) -> tuple[list[dict], int]:
        """Return (page, total) newest-first by created_at_utc fallback name."""
        self._ensure()
        files = sorted(
            self.directory.glob("*.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        total = len(files)
        page: list[dict] = []
        for path in files[offset : offset + limit]:
            try:
                page.append(_read_json(path))
            except StoreError:
                page.append({"id": path.stem, "unreadable": True})
        return page, total

    def get(self, item_id: str) -> dict | None:
        """Return one item by single-segment id, or None when absent."""
        if not item_id or "/" in item_id or "\\" in item_id or item_id.startswith("."):
            raise StoreError("Invalid item id")
        path = self.directory / f"{item_id}.json"
        if not path.exists():
            return None
        return _read_json(path)

    def put(self, item_id: str, payload: dict) -> Path:
        """Write one item atomically; returns the file path."""
        if not item_id or "/" in item_id or "\\" in item_id or item_id.startswith("."):
            raise StoreError("Invalid item id")
        self._ensure()
        path = self.directory / f"{item_id}.json"
        body = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
        if len(body) > MAX_RESPONSE_BYTES:
            raise StoreError("Stored item exceeds the size bound")
        tmp = path.with_suffix(".json.tmp")
        tmp.write_bytes(body)
        tmp.replace(path)
        return path


class DashboardStores:
    """Plans, runs, and inbox collections plus the supervisor token gate."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.plans = JsonCollection(data_dir / "plans")
        self.runs = JsonCollection(data_dir / "runs")
        self.inbox = JsonCollection(data_dir / "inbox")

    @property
    def token_path(self) -> Path:
        """Local supervisor token file; absent means localhost-trust only."""
        return self.data_dir / "supervisor.token"

    def check_supervisor_token(self, provided: str | None) -> bool:
        """Accept when no token is configured, else require an exact match."""
        path = self.token_path
        if not path.exists():
            return True
        expected = path.read_text(encoding="utf-8").strip()
        if not expected or not provided:
            return False
        return secrets.compare_digest(provided, expected)

    def open_inbox_count(self) -> int:
        """Count open inbox tasks without loading every body twice."""
        items, _total = self.inbox.list(limit=MAX_OPEN_TASKS + 1)
        return sum(1 for item in items if item.get("status") == "open")

    def create_inbox_task(
        self,
        *,
        title: str,
        body: str,
        task_type: str,
        plan_id: str | None = None,
        task_id: str | None = None,
        context_refs: list[str] | None = None,
        options: list[str] | None = None,
    ) -> dict:
        """Create one owner task; decisions and clarifications only in v1."""
        title = title.strip()
        if not title:
            raise StoreError("Inbox task needs a title")
        if task_type not in INBOX_TYPES:
            raise StoreError(f"Inbox task type must be one of {INBOX_TYPES}")
        if self.open_inbox_count() >= MAX_OPEN_TASKS:
            raise StoreError("Too many open inbox tasks")
        now = _utc_now()
        record = {
            "id": uuid.uuid4().hex,
            "plan_id": plan_id,
            "task_id": task_id,
            "type": task_type,
            "title": title,
            "body": body,
            "context_refs": list(context_refs or []),
            "options": list(options or []),
            "status": "open",
            "created_by": "supervisor",
            "assignee": "owner",
            "created_at": now,
            "answered_at": None,
            "answer": None,
        }
        self.inbox.put(record["id"], record)
        return record

    def answer_inbox_task(
        self, item_id: str, *, answer: str, option_index: int | None = None
    ) -> dict:
        """Record the owner's answer; closed tasks are immutable."""
        record = self.inbox.get(item_id)
        if record is None:
            raise StoreError("Inbox task not found")
        if record.get("status") == "closed":
            raise StoreError("Closed inbox tasks cannot be re-answered")
        answer = answer.strip()
        if not answer and option_index is None:
            raise StoreError("An answer or option choice is required")
        options = record.get("options") or []
        if option_index is not None and not 0 <= option_index < len(options):
            raise StoreError("Option choice is out of range")
        record["answer"] = answer or options[option_index or 0]
        record["option_index"] = option_index
        record["status"] = "answered"
        record["answered_at"] = _utc_now()
        self.inbox.put(item_id, record)
        return record

    def close_inbox_task(self, item_id: str) -> dict:
        """Close one inbox task; it stays in the audit trail."""
        record = self.inbox.get(item_id)
        if record is None:
            raise StoreError("Inbox task not found")
        record["status"] = "closed"
        self.inbox.put(item_id, record)
        return record
