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
INBOX_TYPES = ("decision", "clarification", "order", "task")
INBOX_STATUSES = ("open", "answered", "closed")
INBOX_PARTIES = ("supervisor", "owner", "agent")
INBOX_ASSIGNEES = ("owner", "agent")
FANOUT_POLICIES = ("allowed", "restricted", "denied")
FANOUT_UNKNOWN = "unknown"
IDEA_SOURCES = ("owner", "third-party")
IDEA_STATUSES = ("new", "reviewing", "adopted", "parked", "declined")


class StoreError(ValueError):
    """A store refusal safe to report to the dashboard caller."""


def effective_fanout_policy(record: dict) -> str:
    """Read one run record's effective fan-out policy for display.

    Prefers the resolved ``fanout_effective`` field, falls back to the raw
    ``fanout_policy`` request, and reports ``unknown`` when the record predates
    both fields or holds only blank/non-string values.
    """
    for key in ("fanout_effective", "fanout_policy"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return FANOUT_UNKNOWN


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
        self.ideas = JsonCollection(data_dir / "ideas")

    @property
    def token_path(self) -> Path:
        """Local supervisor token file; absent means tailnet-membership trust."""
        return self.data_dir / "supervisor.token"

    def check_supervisor_token(self, provided: str | None) -> bool:
        """Accept when no token is configured (single-user tailnet), else exact match."""
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
        metadata: dict | None = None,
        created_by: str = "supervisor",
        assignee: str = "owner",
    ) -> dict:
        """Create one inbox task; tasks default to a single Done choice.

        Direction defaults to supervisor->owner; owner->agent files AI backlog.
        """
        title = title.strip()
        if not title:
            raise StoreError("Inbox task needs a title")
        if task_type not in INBOX_TYPES:
            raise StoreError(f"Inbox task type must be one of {INBOX_TYPES}")
        if created_by not in INBOX_PARTIES:
            raise StoreError(f"Inbox creator must be one of {INBOX_PARTIES}")
        if assignee not in INBOX_ASSIGNEES:
            raise StoreError(f"Inbox assignee must be one of {INBOX_ASSIGNEES}")
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
            "options": list(options)
            if options is not None
            else (["Done"] if task_type == "task" else []),
            "metadata": dict(metadata or {}),
            "status": "open",
            "created_by": created_by,
            "assignee": assignee,
            "created_at": now,
            "answered_at": None,
            "answer": None,
        }
        self.inbox.put(record["id"], record)
        return record

    def agent_queue(self, *, limit: int = 50) -> list[dict]:
        """Open owner->agent items, oldest-first (FIFO backlog)."""
        items, _total = self.inbox.list(limit=MAX_OPEN_TASKS + 1)
        # list() is newest-first; reverse so equal timestamps keep oldest first.
        queued = [
            item
            for item in reversed(items)
            if item.get("status") == "open" and item.get("assignee") == "agent"
        ]
        queued.sort(key=lambda item: item.get("created_at") or "")
        return queued[: max(limit, 0)]

    def answer_inbox_task(
        self, item_id: str, *, answer: str, option_index: int | None = None
    ) -> dict:
        """Record the owner's answer; closed tasks are immutable.

        A choice and free text are independent: when both are given, the
        choice is the answer and the text is kept as a note expanding it.
        Typed-only replies keep working as before.
        """
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
        if option_index is not None:
            record["answer"] = options[option_index]
            record["option_index"] = option_index
            record["note"] = answer or None
        else:
            record["answer"] = answer
            record["option_index"] = None
            record["note"] = None
        record["status"] = "answered"
        record["answered_at"] = _utc_now()
        self.inbox.put(item_id, record)
        return record

    def close_inbox_task(self, item_id: str, *, resolution: str | None = None) -> dict:
        """Close one inbox task; it stays in the audit trail."""
        record = self.inbox.get(item_id)
        if record is None:
            raise StoreError("Inbox task not found")
        if resolution is None or not resolution.strip():
            raise StoreError("Closing needs a resolution note")
        resolution = resolution.strip()
        record["resolution"] = resolution
        record["resolved_at"] = _utc_now()
        record["status"] = "closed"
        self.inbox.put(item_id, record)
        return record

    def reopen_inbox_task(self, item_id: str) -> dict:
        """Reopen a closed inbox task; history is preserved."""
        record = self.inbox.get(item_id)
        if record is None:
            raise StoreError("Inbox task not found")
        if record.get("status") != "closed":
            raise StoreError("Only closed tasks can be reopened")
        record["status"] = "open"
        self.inbox.put(item_id, record)
        return record

    def decide_plan(self, plan_id: str, *, approved: bool) -> dict:
        """Approve or reject one proposed plan; only proposed plans decide."""
        if type(approved) is not bool:
            raise StoreError("Plan decision needs true or false")
        record = self.plans.get(plan_id)
        if record is None:
            raise StoreError("Plan not found")
        if record.get("status") != "proposed":
            raise StoreError("Plan is not awaiting approval")
        now = _utc_now()
        record["status"] = "approved" if approved else "rejected"
        record["decided_at"] = now
        record["updated_at_utc"] = now
        self.plans.put(plan_id, record)
        return record

    def get_run_receipts(self, run_id: str) -> list[dict]:
        """Return one run's receipts; absent receipts read as empty."""
        record = self.runs.get(run_id)
        if record is None:
            raise StoreError("Run not found")
        receipts = record.get("receipts", [])
        if receipts is None:
            return []
        if not isinstance(receipts, list):
            raise StoreError("Run receipts are malformed")
        return receipts

    def create_idea(
        self,
        *,
        title: str,
        body: str,
        source: str,
        contact: str | None = None,
    ) -> dict:
        """Capture one idea; source tags owner vs third-party origin."""
        title = title.strip()
        if not title:
            raise StoreError("Idea needs a title")
        if source not in IDEA_SOURCES:
            raise StoreError(f"Idea source must be one of {IDEA_SOURCES}")
        now = _utc_now()
        record = {
            "id": uuid.uuid4().hex,
            "title": title,
            "body": body,
            "source": source,
            "contact": (contact or "").strip() or None,
            "status": "new",
            "created_at": now,
            "reviewed_at": None,
            "decision": None,
        }
        self.ideas.put(record["id"], record)
        return record

    def set_idea_status(
        self,
        item_id: str,
        *,
        status: str,
        decision: str | None = None,
        plan_id: str | None = None,
    ) -> dict:
        """Move one idea through triage; the record stays as the audit trail.

        ``plan_id`` optionally links the idea to backlog work; it must
        reference an existing plan. A linked idea influences the backlog;
        an unlinked archived idea is archive-only.
        """
        record = self.ideas.get(item_id)
        if record is None:
            raise StoreError("Idea not found")
        if status not in IDEA_STATUSES:
            raise StoreError(f"Idea status must be one of {IDEA_STATUSES}")
        if plan_id is not None:
            plan_id = plan_id.strip()
            if not plan_id or len(plan_id) > 80:
                raise StoreError("Idea plan link must be 1-80 characters")
            try:
                exists = self.plans.get(plan_id)
            except StoreError:
                raise StoreError("Idea plan link must reference an existing plan") from None
            if exists is None:
                raise StoreError("Idea plan link must reference an existing plan")
        record["status"] = status
        record["decision"] = (decision or "").strip() or None
        record["plan_id"] = plan_id
        record["reviewed_at"] = _utc_now()
        self.ideas.put(item_id, record)
        return record

    def new_idea_count(self) -> int:
        """Count untriaged ideas for the Home badge."""
        items, _total = self.ideas.list(limit=1000)
        return sum(1 for item in items if item.get("status") == "new")
