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
FANOUT_UNKNOWN = "unknown"
IDEA_SOURCES = ("owner", "third-party")
IDEA_STATUSES = ("new", "reviewing", "adopted", "parked", "declined", "implemented")
BACKLOG_SOURCES = ("owner", "agent")
BACKLOG_STATUSES = ("proposed", "ready", "doing", "blocked", "done", "dropped")
BACKLOG_OPEN = ("proposed", "ready", "doing", "blocked")
WORKFLOW_STATUSES = ("active", "archived")


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

    def delete(self, item_id: str) -> bool:
        """Remove one item; True when a file was removed."""
        if not item_id or "/" in item_id or "\\" in item_id or item_id.startswith("."):
            raise StoreError("Invalid item id")
        path = self.directory / f"{item_id}.json"
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        return True


class DashboardStores:
    """Plans, runs, and inbox collections plus the supervisor token gate."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.plans = JsonCollection(data_dir / "plans")
        self.runs = JsonCollection(data_dir / "runs")
        self.inbox = JsonCollection(data_dir / "inbox")
        self.ideas = JsonCollection(data_dir / "ideas")
        self.backlog = JsonCollection(data_dir / "backlog")
        self.workflows = JsonCollection(data_dir / "workflows")
        self.invoices = JsonCollection(data_dir / "invoices")
        self.e2e_tasks = JsonCollection(data_dir / "e2e_tasks")
        self.e2e_reports = JsonCollection(data_dir / "e2e_reports")
        self.chat_modes = JsonCollection(data_dir / "chat_modes")

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

    def close_inbox_task(
        self,
        item_id: str,
        *,
        resolution: str | None = None,
        resolution_kind: str = "final",
    ) -> dict:
        """Close one inbox task; it stays in the audit trail.

        ``resolution_kind`` is "final" (answered/decided/implemented) or
        "followup" (closed with no final answer: elaboration, investigation
        or deferral still pending). Follow-up closes stay out of the archive.
        """
        record = self.inbox.get(item_id)
        if record is None:
            raise StoreError("Inbox task not found")
        if resolution is None or not resolution.strip():
            raise StoreError("Closing needs a resolution note")
        if resolution_kind not in ("final", "followup"):
            raise StoreError("Unknown resolution kind")
        resolution = resolution.strip()
        record["resolution"] = resolution
        record["resolution_kind"] = resolution_kind
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

    def create_workflow(
        self,
        *,
        name: str,
        description: str = "",
        nodes: list | None = None,
    ) -> dict:
        """Save one workflow graph; the schema accepts or refuses the nodes."""
        from ai_agent.workflow_graph import graph_from_dict, graph_to_dict

        try:
            graph = graph_from_dict(
                {"name": name, "description": description, "nodes": nodes or []}
            )
        except ValueError as exc:
            raise StoreError(str(exc)) from None
        now = _utc_now()
        record = {
            "id": uuid.uuid4().hex,
            "status": "active",
            "created_at": now,
            **graph_to_dict(graph),
        }
        self.workflows.put(record["id"], record)
        return record

    def set_workflow_status(self, item_id: str, *, status: str) -> dict:
        """Archive or reactivate one workflow; the graph stays as the record."""
        record = self.workflows.get(item_id)
        if record is None:
            raise StoreError("Workflow not found")
        if status not in WORKFLOW_STATUSES:
            raise StoreError(f"Workflow status must be one of {WORKFLOW_STATUSES}")
        record["status"] = status
        self.workflows.put(item_id, record)
        return record

    def new_idea_count(self) -> int:
        """Count untriaged ideas for the Home badge."""
        items, _total = self.ideas.list(limit=1000)
        return sum(1 for item in items if item.get("status") == "new")

    def open_backlog_count(self) -> int:
        """Count groomed-but-unfinished backlog items for the Home badge."""
        items, _total = self.backlog.list(limit=1000)
        return sum(1 for item in items if item.get("status") in BACKLOG_OPEN)

    def create_backlog_item(
        self,
        *,
        title: str,
        body: str,
        source: str = "owner",
        ref: str | None = None,
    ) -> dict:
        """Capture one backlog item; ``ref`` cites the origin (ledger doc, idea id)."""
        title = title.strip()
        if not title:
            raise StoreError("Backlog item needs a title")
        if source not in BACKLOG_SOURCES:
            raise StoreError(f"Backlog source must be one of {BACKLOG_SOURCES}")
        ref = (ref or "").strip() or None
        if ref is not None and len(ref) > 200:
            raise StoreError("Backlog ref must be 1-200 characters")
        now = _utc_now()
        record = {
            "id": uuid.uuid4().hex,
            "title": title,
            "body": body,
            "source": source,
            "ref": ref,
            "status": "proposed",
            "inbox_id": None,
            "created_at": now,
            "reviewed_at": None,
            "decision": None,
        }
        self.backlog.put(record["id"], record)
        return record

    def set_backlog_status(self, item_id: str, *, status: str, decision: str | None = None) -> dict:
        """Groom one backlog item; the record stays as the audit trail."""
        record = self.backlog.get(item_id)
        if record is None:
            raise StoreError("Backlog item not found")
        if status not in BACKLOG_STATUSES:
            raise StoreError(f"Backlog status must be one of {BACKLOG_STATUSES}")
        record["status"] = status
        record["decision"] = (decision or "").strip() or None
        record["reviewed_at"] = _utc_now()
        self.backlog.put(item_id, record)
        return record

    def promote_backlog_item(self, item_id: str, *, created_by: str = "supervisor") -> dict:
        """File one backlog item as an inbox decision (take into run, or hold).

        Refuses while a previous promotion is still undecided so one item
        cannot spam the inbox; a closed brief may be re-proposed.
        """
        record = self.backlog.get(item_id)
        if record is None:
            raise StoreError("Backlog item not found")
        if record.get("inbox_id") is not None:
            brief = self.inbox.get(record["inbox_id"])
            if brief is not None and brief.get("status") != "closed":
                raise StoreError("Backlog item already has an open inbox brief")
        body = record.get("body") or ""
        if record.get("ref"):
            body = f"{body}\n\nRef: {record['ref']}".strip()
        brief = self.create_inbox_task(
            title=f"Take into run: {record['title']}",
            body=body,
            task_type="decision",
            options=["A: Take into next run", "B: Hold"],
            created_by=created_by,
        )
        record["inbox_id"] = brief["id"]
        record["reviewed_at"] = _utc_now()
        self.backlog.put(item_id, record)
        return {"item": record, "inbox": brief}

    def open_e2e_count(self) -> int:
        """Count unsubmitted E2E tasks for the owner badge."""
        items, _total = self.e2e_tasks.list(limit=1000)
        return sum(1 for item in items if item.get("status") == "open")

    def create_e2e_task(
        self,
        *,
        merge_commit: str,
        title: str,
        items: list[dict],
        created_by: str = "supervisor",
        range_base: str | None = None,
    ) -> dict:
        """File one E2E task for a merge; one open task per merge commit.

        A resubmitted merge replaces nothing: while an open task exists
        for the commit, generation refuses so the owner never faces two
        checklists for the same merge.
        """
        from e2e_promotion import BEHAVIOR_AREA_IDS

        merge_commit = merge_commit.strip()
        if not merge_commit:
            raise StoreError("E2E task needs a merge commit")
        if not isinstance(items, list) or not items:
            raise StoreError("E2E task needs at least one checklist item")
        if created_by not in INBOX_PARTIES:
            raise StoreError(f"E2E creator must be one of {INBOX_PARTIES}")
        for item in items:
            if not isinstance(item, dict):
                raise StoreError("E2E checklist items must be objects")
            if item.get("kind") not in ("behavior", "regression", "nonbehavioral"):
                raise StoreError("E2E item kind must be behavior, regression or nonbehavioral")
            if item.get("area") not in BEHAVIOR_AREA_IDS:
                raise StoreError(f"Unknown E2E area: {item.get('area')}")
            if not str(item.get("id", "")).strip():
                raise StoreError("E2E items need ids")
        existing, _total = self.e2e_tasks.list(limit=1000)
        if any(
            entry.get("merge_commit") == merge_commit and entry.get("status") == "open"
            for entry in existing
            if isinstance(entry, dict)
        ):
            raise StoreError("An open E2E task already exists for this merge")
        now = _utc_now()
        record = {
            "id": uuid.uuid4().hex,
            "merge_commit": merge_commit,
            "range_base": (range_base or "").strip() or None,
            "title": title.strip() or f"E2E promotion for {merge_commit}",
            "items": items,
            "status": "open",
            "created_by": created_by,
            "created_at": now,
            "submitted_at": None,
            "report_id": None,
        }
        self.e2e_tasks.put(record["id"], record)
        return record

    def submit_e2e_task(self, task_id: str, results: list[dict]) -> dict:
        """Submit owner verdicts; submitting auto-builds the E2E report.

        Every pending item needs exactly one pass/fail verdict; the
        report (including carried ancestor approvals with warnings) is
        stored alongside the task. Submitted tasks are immutable.
        """
        from e2e_promotion import build_report

        record = self.e2e_tasks.get(task_id)
        if record is None:
            raise StoreError("E2E task not found")
        if record.get("status") != "open":
            raise StoreError("E2E task is already submitted")
        if not isinstance(results, list):
            raise StoreError("E2E submission needs a results list")
        submissions: dict[str, dict] = {}
        for entry in results:
            if not isinstance(entry, dict) or not str(entry.get("item_id", "")).strip():
                raise StoreError("E2E results need item ids")
            submissions[str(entry["item_id"])] = {
                "verdict": entry.get("verdict"),
                "notes": entry.get("notes", ""),
            }
        try:
            report = build_report(record, submissions)
        except ValueError as exc:
            raise StoreError(str(exc)) from exc
        report["id"] = uuid.uuid4().hex
        self.e2e_reports.put(report["id"], report)
        record["status"] = "submitted"
        record["submitted_at"] = _utc_now()
        record["report_id"] = report["id"]
        self.e2e_tasks.put(task_id, record)
        return {"task": record, "report": report}

    def get_chat_mode(self, session_id: str) -> dict:
        """Chat mode record; sessions default to ask with no binding."""
        record = self.chat_modes.get(session_id)
        if isinstance(record, dict):
            return record
        return {"session_id": session_id, "mode": "ask", "coding_session_id": None}

    def set_chat_mode(self, session_id: str, *, mode: str) -> dict:
        """Set one chat session's mode (ask or agent)."""
        if mode not in ("ask", "agent"):
            raise StoreError("Chat mode must be ask or agent")
        record = self.get_chat_mode(session_id)
        record["mode"] = mode
        record["updated_at"] = _utc_now()
        self.chat_modes.put(session_id, record)
        return record

    def set_chat_binding(self, session_id: str, coding_session_id: str) -> dict:
        """Bind one chat session to its Mai coding session."""
        if not str(coding_session_id).strip():
            raise StoreError("Coding session id is required")
        record = self.get_chat_mode(session_id)
        record["coding_session_id"] = str(coding_session_id).strip()
        record["updated_at"] = _utc_now()
        self.chat_modes.put(session_id, record)
        return record
