"""File-backed JSON stores for plans, runs, and the owner-task inbox.

Dashboard v1 reads plans/runs created by existing Workbench flows and owns
only chat transcripts plus inbox answers. Everything lives under the
dashboard data directory (gitignored); responses are size-bounded.
"""

from __future__ import annotations

import json
import secrets
import uuid
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path

MAX_RESPONSE_BYTES = 100_000
MAX_OPEN_TASKS = 50
INBOX_TYPES = ("decision", "clarification", "order", "task", "report")
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
RELATED_LIMIT = 1000


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

    def get(self, item_id: str, *, claim: bool = False) -> dict | None:
        """Read an item, or its drain claim when requested; None when absent."""
        if not item_id or "/" in item_id or "\\" in item_id or item_id.startswith("."):
            raise StoreError("Invalid item id")
        path = self.directory / f"{item_id}.json{'.claim' if claim else ''}"
        if not path.exists():
            return None
        return _read_json(path)

    def put(self, item_id: str, payload: dict, *, claim: bool = False) -> Path:
        """Write an item or drain claim atomically; returns the file path."""
        if not item_id or "/" in item_id or "\\" in item_id or item_id.startswith("."):
            raise StoreError("Invalid item id")
        self._ensure()
        path = self.directory / f"{item_id}.json{'.claim' if claim else ''}"
        body = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
        if len(body) > MAX_RESPONSE_BYTES:
            raise StoreError("Stored item exceeds the size bound")
        tmp = path.with_name(path.name + ".tmp")
        from wake_idle import cancel_pending, interlock

        task_state = self.directory.name in {"inbox", "runs"}
        with interlock(self.directory.parent) if task_state else nullcontext():
            if task_state and (
                self.directory.name == "runs"
                or (payload.get("status") == "open" and payload.get("assignee") == "agent")
            ):
                cancel_pending(self.directory.parent)
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

    @staticmethod
    def waiting_on(item: dict) -> str:
        """Whose move next: owner decides, agent closes out.

        Records predating the field default by status: an unanswered
        item waits on the owner; an answered one waits on AI close-out.
        """
        explicit = item.get("waiting_on")
        if explicit in ("owner", "agent"):
            return explicit
        return "agent" if item.get("status") == "answered" else "owner"

    def attention_inbox_items(self) -> list[dict]:
        """Human attention items: what the inbox default view must show.

        Human assignee with open, owner-waiting answered, or follow-up
        state, never the AI queue. Answered items under AI close-out do
        not badge the owner. The badge counts this set; the list
        endpoint unions it in so the default view can never hide a
        badged item past the newest cutoff.
        """
        items, _total = self.inbox.list(limit=1000)
        return [
            item
            for item in items
            if (
                item.get("assignee") != "agent"
                and not (item.get("type") == "report" and item.get("acknowledged"))
                and (
                    item.get("status") == "open"
                    or (item.get("status") == "answered" and self.waiting_on(item) == "owner")
                    or (item.get("resolution_kind") or "final") != "final"
                )
            )
            or (
                item.get("status") == "closed"
                and (item.get("resolution_kind") or "final") != "final"
                and item.get("waiting_on") == "owner"
            )
        ]

    def attention_inbox_count(self) -> int:
        """Human attention items: the badge mirrors the default filter."""
        return len(self.attention_inbox_items())

    def default_project_id(self) -> str:
        """Registry id of the workbench root on this machine.

        The data dir always sits at <repo>/apps/workbench_dashboard/data,
        so the repo root is two levels up; its digest is the default
        project for records without a better home.
        """
        from dashboard_projects import repo_project_id

        return repo_project_id(self.data_dir.parent.parent)

    def project_of(self, record: dict) -> str:
        """Owning project; records predating relations belong to workbench."""
        value = record.get("project_id")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return self.default_project_id()

    def related(self, project_id: str) -> dict[str, list[dict]]:
        """Cross-tab links for one project (plans, inbox, runs, E2E tasks).

        Full-collection scans: volumes are tiny and single-user, so no
        index pays for itself. Slim dicts (id/title/status) keep the
        project view fast.
        """
        want = (project_id or "").strip() or self.default_project_id()
        linked: dict[str, list[dict]] = {"plans": [], "inbox": [], "runs": [], "e2e_tasks": []}
        for key, collection in (
            ("plans", self.plans),
            ("inbox", self.inbox),
            ("runs", self.runs),
            ("e2e_tasks", self.e2e_tasks),
        ):
            items, _total = collection.list(limit=RELATED_LIMIT)
            for item in items:
                if not isinstance(item, dict) or self.project_of(item) != want:
                    continue
                linked[key].append(
                    {
                        "id": item.get("id"),
                        "title": item.get("title") or item.get("name") or item.get("id"),
                        "status": item.get("status"),
                    }
                )
        return linked

    def backfill_project_ids(self, default: str | None = None) -> dict[str, int]:
        """Stamp records missing project_id; returns per-collection counts."""
        default = default or self.default_project_id()
        filled: dict[str, int] = {}
        for key, collection in (
            ("plans", self.plans),
            ("inbox", self.inbox),
            ("runs", self.runs),
            ("e2e_tasks", self.e2e_tasks),
        ):
            count = 0
            items, _total = collection.list(limit=RELATED_LIMIT)
            for item in items:
                if not isinstance(item, dict):
                    continue
                value = item.get("project_id")
                if isinstance(value, str) and value.strip():
                    continue
                item_id = item.get("id")
                if not isinstance(item_id, str) or not item_id.strip():
                    continue
                item["project_id"] = default
                collection.put(item_id, item)
                count += 1
            filled[key] = count
        return filled

    def with_inbox_attribution(self, item: dict) -> dict:
        """Project observed identity without guessing models from route names.

        Legacy records are enriched on read; no historical rewrite is needed.
        Linked execution identity is separate from the filing source.
        """
        metadata = dict(item.get("metadata") or {})
        if item.get("created_by") == "owner":
            return item
        refs = item.get("context_refs") or []
        for ref in refs:
            if not isinstance(ref, str) or not ref.startswith("run:"):
                continue
            run_id = ref[4:]
            if not run_id or "/" in run_id or "\\" in run_id or run_id.startswith("."):
                continue
            run = self.runs.get(run_id)
            if not run:
                continue
            receipts = run.get("receipts") or []
            for receipt in reversed(receipts):
                if not isinstance(receipt, dict):
                    continue
                if receipt.get("route_id") or receipt.get("model_id"):
                    metadata.setdefault("author_route", receipt.get("route_id"))
                    metadata.setdefault("author_model", receipt.get("model_id"))
                    metadata.setdefault("attribution_run_id", ref[4:])
                    break
            if metadata.get("attribution_run_id"):
                break
        return {**item, "metadata": metadata}

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
        project_id: str | None = None,
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
        if task_type == "report" and (created_by != "supervisor" or assignee != "owner"):
            raise StoreError("Chain reports are supervisor-issued to the owner")
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
            "waiting_on": "agent" if assignee == "agent" else "owner",
            "project_id": project_id or self.default_project_id(),
            "created_at": now,
            "answered_at": None,
            "answer": None,
        }
        record = self.with_inbox_attribution(record)
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
        if record.get("type") == "report":
            raise StoreError("Chain reports are acknowledged, not answered")
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
        first_answer = record.get("status") != "answered"
        record["status"] = "answered"
        record["answered_at"] = _utc_now()
        record["waiting_on"] = "agent"
        if first_answer and not (record.get("metadata") or {}).get("closeout_id"):
            if (record.get("metadata") or {}).get("claimed_by"):
                record["closeout_pending"] = True
                record["closeout_deferred"] = f"claimed:{record['metadata']['claimed_by']}"
            else:
                self._queue_closeout(record)
        self.inbox.put(item_id, record)
        return record

    def _queue_closeout(self, record: dict) -> None:
        """File the AI close-out task for an owner answer (implement→close).

        Owner rule: the owner decides, never writes reports. Close-out
        implements the recorded answer, proves it, resolves, and closes.
        When the open-task cap refuses the filing, the item is flagged
        so the sweep surfaces it instead of dropping the work silently.
        """
        try:
            task = self.create_inbox_task(
                title=f"Close out: {str(record.get('title') or record.get('id'))[:80]}",
                body=(
                    f"Owner answered '{record.get('id', '')[:8]}' "
                    f"({record.get('title') or ''}): {record.get('answer') or ''}\n"
                    f"Note: {record.get('note') or '(none)'}\n\n"
                    "Implement the answer, run the proving checks, write the "
                    "resolution on the source item, and close it."
                ),
                task_type="task",
                created_by="supervisor",
                assignee="agent",
                project_id=str(record.get("project_id") or self.default_project_id()),
                metadata={"author_source": "rule", "closeout_for": record.get("id")},
                context_refs=[f"inbox:{record.get('id')}"],
            )
        except StoreError:
            record["closeout_pending"] = True
            return
        metadata = dict(record.get("metadata") or {})
        metadata["closeout_id"] = task["id"]
        record["metadata"] = metadata
        record.pop("closeout_pending", None)

    def retry_closeout(self, record: dict) -> bool:
        """Re-attempt a cap-refused close-out filing; True when filed now."""
        metadata = record.get("metadata") or {}
        if not record.get("closeout_pending") or metadata.get("closeout_id"):
            return False
        if metadata.get("claimed_by"):
            return False
        self._queue_closeout(record)
        self.inbox.put(record["id"], record)
        return bool((record.get("metadata") or {}).get("closeout_id"))

    def reassign_inbox_task(self, item_id: str, assignee: str) -> dict:
        """Move an open/answered item between owner and agent queues.

        Corrections only: closed items stay archival (reopen first).
        """
        if assignee not in INBOX_ASSIGNEES:
            raise StoreError(f"Inbox assignee must be one of {INBOX_ASSIGNEES}")
        record = self.inbox.get(item_id)
        if record is None:
            raise StoreError(f"Inbox task not found: {item_id}")
        if record.get("status") == "closed":
            raise StoreError("Closed items cannot be reassigned")
        record["assignee"] = assignee
        self.inbox.put(item_id, record)
        return record

    def claim_inbox_task(self, item_id: str, by: str | None) -> dict:
        """Claim an item for a loop session, or release it (``by=None``).

        While ``metadata.claimed_by`` is set, owner answers defer their
        close-out filing instead of triggering drain execution, so a loop
        session and the drain never implement the same answer twice.
        Release files a deferred close-out immediately when one waits.
        """
        record = self.inbox.get(item_id)
        if record is None:
            raise StoreError(f"Inbox task not found: {item_id}")
        metadata = dict(record.get("metadata") or {})
        if by:
            metadata["claimed_by"] = by
            record["metadata"] = metadata
            self.inbox.put(item_id, record)
            return record
        metadata.pop("claimed_by", None)
        record["metadata"] = metadata
        if (
            record.get("status") == "answered"
            and record.get("closeout_pending")
            and not metadata.get("closeout_id")
        ):
            self._queue_closeout(record)
            record.pop("closeout_deferred", None)
        self.inbox.put(item_id, record)
        return record

    def _report_close_to_source(self, record: dict) -> None:
        """Report an agent close back to its linked source (best-effort).

        Close-out tasks append one deduped line to their source item's
        note so the answer thread shows its implementation outcome.
        Run-bridged items already report via the drain terminal hook and
        E2E follow-ups close into immutable verdict reports, so neither
        is duplicated here. Never raises: reporting must not fail a close.
        """
        try:
            metadata = record.get("metadata") or {}
            source_id = metadata.get("closeout_for")
            if not source_id:
                return
            source = self.inbox.get(str(source_id))
            if source is None:
                return
            marker = f"closeout:{record.get('id')}"
            note = source.get("note") or ""
            if marker in note:
                return
            line = (
                f"Close-out {str(record.get('id'))[:8]} "
                f"({record.get('resolution_kind') or 'final'}): "
                f"{(record.get('resolution') or '')[:300]} [{marker}]"
            )
            source["note"] = (note + "\n" + line).strip() if note else line
            self.inbox.put(source["id"], source)
        except Exception:  # noqa: BLE001 - report-back never breaks close
            return

    def close_inbox_task(
        self,
        item_id: str,
        *,
        resolution: str | None = None,
        resolution_kind: str = "final",
        waiting_on: str | None = None,
    ) -> dict:
        """Close one inbox task; it stays in the audit trail.

        ``resolution_kind`` is "final" (answered/decided/implemented) or
        "followup" (closed with no final answer: elaboration, investigation
        or deferral still pending). Follow-up closes stay out of the archive.
        A follow-up close may carry ``waiting_on="owner"`` when its
        resolution asks the owner something; that badges the owner even on
        agent-assigned threads, which otherwise never badge.
        """
        record = self.inbox.get(item_id)
        if record is None:
            raise StoreError("Inbox task not found")
        if record.get("type") == "report":
            raise StoreError("Chain reports close via acknowledge, not close")
        if resolution is None or not resolution.strip():
            raise StoreError("Closing needs a resolution note")
        if resolution_kind not in ("final", "followup"):
            raise StoreError("Unknown resolution kind")
        if waiting_on not in (None, "owner", "agent"):
            raise StoreError("waiting_on must be owner, agent, or omitted")
        if waiting_on is not None and resolution_kind != "followup":
            raise StoreError("waiting_on is only meaningful on follow-up closes")
        resolution = resolution.strip()
        record["resolution"] = resolution
        record["resolution_kind"] = resolution_kind
        record["resolved_at"] = _utc_now()
        record["status"] = "closed"
        record["waiting_on"] = waiting_on
        self.inbox.put(item_id, record)
        self._report_close_to_source(record)
        self._maybe_finalize_chain(record)
        return record

    def _maybe_finalize_chain(self, record: dict) -> None:
        """File the chain-end report once source and close-out both close.

        Either close can land last; finalization is deduped on the
        source, refuses the cap with a retry flag, and never raises.
        """
        try:
            from supervisor_followups import finalize_chain_report

            metadata = record.get("metadata") or {}
            source_id = metadata.get("closeout_for") or (
                record.get("id") if metadata.get("closeout_id") else None
            )
            if not source_id:
                return
            source = self.inbox.get(str(source_id))
            if source is None or source.get("status") != "closed":
                return
            closeout_id = (source.get("metadata") or {}).get("closeout_id")
            closeout = self.inbox.get(str(closeout_id)) if closeout_id else None
            if closeout is None or closeout.get("status") != "closed":
                return
            finalize_chain_report(self, str(source_id))
        except Exception:  # noqa: BLE001 - finalization never breaks close
            return

    def acknowledge_report(self, item_id: str) -> dict:
        """Acknowledge a chain report: archived out of the badge, then immutable.

        Only open, unacknowledged reports acknowledge. The record closes
        with its achievement text intact; later edits are rejected except
        append-only supersede links. Reopening stays the explicit
        owner-override path.
        """
        record = self.inbox.get(item_id)
        if record is None:
            raise StoreError("Inbox task not found")
        if record.get("type") != "report":
            raise StoreError("Only chain reports acknowledge")
        if record.get("status") == "closed" or record.get("acknowledged"):
            raise StoreError("Chain report is already acknowledged")
        record["acknowledged"] = True
        record["acknowledged_at"] = _utc_now()
        record["resolution"] = (
            f"Acknowledged {record['acknowledged_at'][:10]}; "
            "chain report archived, content immutable."
        )
        record["resolution_kind"] = "final"
        record["resolved_at"] = record["acknowledged_at"]
        record["status"] = "closed"
        record["waiting_on"] = None
        self.inbox.put(item_id, record)
        return record

    def supersede_report(self, item_id: str, *, by_id: str) -> dict:
        """Append a supersede link to a closed report (the one allowed edit)."""
        record = self.inbox.get(item_id)
        if record is None:
            raise StoreError("Inbox task not found")
        if record.get("type") != "report" or record.get("status") != "closed":
            raise StoreError("Only closed chain reports take supersede links")
        target = self.inbox.get(by_id)
        if target is None or target.get("type") != "report":
            raise StoreError("Supersede target must be a chain report")
        links = list((record.get("metadata") or {}).get("supersede_links") or [])
        if by_id in links:
            return record
        links.append(by_id)
        metadata = dict(record.get("metadata") or {})
        metadata["supersede_links"] = links
        record["metadata"] = metadata
        line = f"Superseded by report {by_id}."
        body = record.get("body") or ""
        record["body"] = (body.rstrip() + "\n\n" + line) if body.strip() else line
        self.inbox.put(item_id, record)
        return record

    def resolve_id(self, token: str) -> list[dict]:
        """Resolve an id or unique prefix across inbox, runs, ideas and plans.

        Exact full-id matches win; otherwise a case-insensitive unique
        prefix (minimum 8 hex chars) resolves; ambiguous or missing
        tokens return every candidate (possibly none) for display.
        Read-only: powers the ID lookup and auto-link verification.
        """
        cleaned = (token or "").strip().lower()
        if not cleaned or any(ch not in "0123456789abcdef" for ch in cleaned):
            return []
        if len(cleaned) < 8:
            return []
        pools = (
            ("inbox", self.inbox, "#/inbox/"),
            ("run", self.runs, "#/runs/"),
            ("idea", self.ideas, "#/ideas/"),
            ("plan", self.plans, "#/plans/"),
        )
        exact: list[dict] = []
        prefixed: list[dict] = []
        for kind, pool, route in pools:
            try:
                items, _total = pool.list(limit=5000)
            except Exception:  # noqa: BLE001 - lookup skips unreadable pools
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                ident = str(item.get("id") or "")
                if not ident or not ident.lower().startswith(cleaned):
                    continue
                entry = {
                    "kind": kind,
                    "id": ident,
                    "title": item.get("title") or ident,
                    "status": item.get("status"),
                    "url": f"{route}{ident}",
                }
                if ident.lower() == cleaned:
                    exact.append(entry)
                else:
                    prefixed.append(entry)
        if exact:
            return exact
        seen: set[str] = set()
        unique: list[dict] = []
        for entry in prefixed:
            if entry["id"] not in seen:
                seen.add(entry["id"])
                unique.append(entry)
        return unique

    def reopen_inbox_task(self, item_id: str) -> dict:
        """Reopen a closed inbox task; history is preserved."""
        record = self.inbox.get(item_id)
        if record is None:
            raise StoreError("Inbox task not found")
        if record.get("status") != "closed":
            raise StoreError("Only closed tasks can be reopened")
        record["status"] = "open"
        record["waiting_on"] = "owner"
        self.inbox.put(item_id, record)
        return record

    def append_plan_evolution(self, plan_id: str, entry: str) -> dict:
        """Append one timestamped entry to a plan's Evolutions log.

        Closeouts call this so Roadmaps stay live surfaces instead of
        stale documents. Creates the section when absent.
        """
        record = self.plans.get(plan_id)
        if record is None:
            raise StoreError("Plan not found")
        entry = entry.strip()
        if not entry:
            raise StoreError("Evolution entry needs text")
        stamp = _utc_now()[:10]
        body = record.get("body") or ""
        line = f"- {stamp}: {entry}"
        if "## Evolutions" not in body:
            body = body.rstrip() + "\n\n## Evolutions\n" + line + "\n"
        else:
            body = body.rstrip() + "\n" + line + "\n"
        record["body"] = body
        record["updated_at_utc"] = _utc_now()
        self.plans.put(plan_id, record)
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

        A transition to adopted files exactly one agent elaboration task;
        re-reviews and other targets file nothing.
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
        previous = record.get("status")
        record["status"] = status
        record["decision"] = (decision or "").strip() or None
        record["plan_id"] = plan_id
        record["reviewed_at"] = _utc_now()
        if status == "adopted" and previous != "adopted":
            self._maybe_file_elaboration(record)
        self.ideas.put(item_id, record)
        return record

    def _maybe_file_elaboration(self, record: dict) -> None:
        """File the agent elaboration task for a newly adopted idea.

        Dedupe: an already-open elaboration task for this idea files
        nothing. A cap refusal never raises; the idea is flagged with
        ``elaboration_pending`` instead so the work is not lost silently.
        """
        idea_id = str(record.get("id") or "")
        items, _total = self.inbox.list(limit=1000)
        for item in items:
            if not isinstance(item, dict) or item.get("status") != "open":
                continue
            if (item.get("metadata") or {}).get("elaboration_for") == idea_id:
                return
        plan_id = record.get("plan_id")
        body = (
            f"Adopted idea '{record.get('title') or ''}': {record.get('body') or ''}\n\n"
            f"Decision: {record.get('decision') or '(no decision)'}\n"
            f"Plan: {plan_id if plan_id else 'no plan link'}\n\n"
            "Elaborate this adopted idea into actionable next steps."
        )
        try:
            self.create_inbox_task(
                title=f"Elaborate adopted idea: {record.get('title') or ''}",
                body=body,
                task_type="task",
                created_by="supervisor",
                assignee="agent",
                context_refs=[f"idea:{idea_id}"],
                metadata={"author_source": "rule", "elaboration_for": idea_id},
            )
        except StoreError:
            record["elaboration_pending"] = True
            return
        record.pop("elaboration_pending", None)

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
        """Count untriaged ideas for the Home badge.

        New ideas plus reviewing items older than 7 days: a review that
        sits undecided is as invisible as an untriaged one.
        """
        items, _total = self.ideas.list(limit=1000)
        now = datetime.now(UTC)
        count = 0
        for item in items:
            status = item.get("status")
            if status == "new":
                count += 1
            elif status == "reviewing":
                try:
                    created = datetime.fromisoformat(str(item.get("created_at") or ""))
                except ValueError:
                    continue
                if created.tzinfo is None:
                    continue
                if (now - created).days >= 7:
                    count += 1
        return count

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
        gate: dict | None = None,
        task_spec: dict | None = None,
    ) -> dict:
        """Capture one backlog item; ``ref`` cites the origin (ledger doc, idea id).

        ``gate`` stores the machine-readable execution condition
        (``manual``/``date``/``inbox_decision``); ``task_spec`` is the
        prepared agent-task plan used when the gate opens.
        """
        title = title.strip()
        if not title:
            raise StoreError("Backlog item needs a title")
        if source not in BACKLOG_SOURCES:
            raise StoreError(f"Backlog source must be one of {BACKLOG_SOURCES}")
        ref = (ref or "").strip() or None
        if ref is not None and len(ref) > 200:
            raise StoreError("Backlog ref must be 1-200 characters")
        gate = self._checked_gate(gate)
        if task_spec is not None:
            self._checked_task_spec(task_spec)
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
            "gate": gate,
            "task_spec": task_spec,
        }
        self.backlog.put(record["id"], record)
        return record

    @staticmethod
    def _checked_gate(gate: dict | None) -> dict | None:
        if gate is None:
            return None
        if not isinstance(gate, dict):
            raise StoreError("Backlog gate must be an object")
        kind = gate.get("kind")
        if kind == "manual":
            return {"kind": "manual", "condition": str(gate.get("condition") or "")}
        if kind == "date":
            try:
                moment = datetime.fromisoformat(str(gate.get("not_before") or ""))
            except ValueError:
                raise StoreError("Backlog date gate needs ISO not_before") from None
            if moment.tzinfo is None:
                raise StoreError("Backlog date gate needs a timezone-aware ISO time")
            return {"kind": "date", "not_before": moment.isoformat()}
        if kind == "inbox_decision":
            item_id = gate.get("item_id")
            if not isinstance(item_id, str) or not item_id.strip():
                raise StoreError("Backlog decision gate needs an inbox item_id")
            return {"kind": "inbox_decision", "item_id": item_id.strip()}
        raise StoreError(f"Unknown backlog gate kind: {kind!r}")

    @staticmethod
    def _checked_task_spec(task_spec: dict) -> None:
        if not isinstance(task_spec, dict):
            raise StoreError("Backlog task_spec must be an object")
        if not str(task_spec.get("title") or "").strip() or not isinstance(
            task_spec.get("body"), str
        ):
            raise StoreError("Backlog task_spec needs a title and a string body")

    def backlog_gate_open(self, item_id: str) -> tuple[bool, str]:
        """True when a backlog item's gate currently permits promotion."""
        record = self.backlog.get(item_id)
        if record is None:
            raise StoreError("Backlog item not found")
        gate = record.get("gate") or {"kind": "manual"}
        kind = gate.get("kind")
        if kind == "manual":
            return True, "manual gate opens on owner click"
        if kind == "date":
            moment = datetime.fromisoformat(gate["not_before"])
            now = datetime.now(UTC)
            if now >= moment:
                return True, f"date gate passed {gate['not_before']}"
            return False, f"date gate opens {gate['not_before']}"
        if kind == "inbox_decision":
            linked = self.inbox.get(gate.get("item_id", ""))
            if linked is not None and linked.get("status") in ("answered", "closed"):
                return True, f"decision {gate['item_id'][:8]} resolved"
            return False, f"awaiting decision {gate.get('item_id', '')[:8]}"
        return False, f"unknown gate kind {kind!r}"

    def promote_backlog_to_task(self, item_id: str) -> dict:
        """Promote a gated backlog item straight to an agent task (no brief).

        Refuses closed gates and re-promotion while the linked task is
        still open; the created task flows through the normal bridge.
        """
        record = self.backlog.get(item_id)
        if record is None:
            raise StoreError("Backlog item not found")
        if record.get("status") in ("doing", "done", "dropped"):
            raise StoreError(f"Backlog item is {record.get('status')}")
        task_spec = record.get("task_spec")
        if task_spec is None:
            raise StoreError("Backlog item has no task_spec to promote")
        open_now, reason = self.backlog_gate_open(item_id)
        if not open_now:
            raise StoreError(f"Backlog gate closed: {reason}")
        if record.get("inbox_id") is not None:
            linked = self.inbox.get(record["inbox_id"])
            if linked is not None and linked.get("status") == "open":
                raise StoreError("Backlog item already has an open task")
        task = self.create_inbox_task(
            title=str(task_spec.get("title")),
            body=str(task_spec.get("body", "")),
            task_type="task",
            created_by="supervisor",
            assignee="agent",
            metadata={"author_source": "rule", "backlog_id": item_id},
        )
        record["inbox_id"] = task["id"]
        record["status"] = "doing"
        record["reviewed_at"] = _utc_now()
        self.backlog.put(item_id, record)
        return {"item": record, "task": task}

    def promote_open_backlog(self) -> list[dict]:
        """Auto-promote backlog items whose non-manual gates opened."""
        promoted = []
        items, _total = self.backlog.list(limit=1000)
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("status") in ("doing", "done", "dropped"):
                continue
            gate = item.get("gate") or {"kind": "manual"}
            if gate.get("kind") == "manual" or item.get("task_spec") is None:
                continue
            open_now, _reason = self.backlog_gate_open(item["id"])
            if not open_now:
                continue
            try:
                result = self.promote_backlog_to_task(item["id"])
            except StoreError:
                continue
            promoted.append(result["item"])
        return promoted

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

    def attention_e2e_count(self) -> int:
        """E2E attention tasks: open checklists awaiting owner tests.

        Drafts are excluded by design: the default E2E view hides them
        (owner verdict) and their pointer request already counts toward
        the inbox badge, so counting them here double-represents them.
        """
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
        draft: bool = False,
        project_id: str | None = None,
    ) -> dict:
        """File one E2E task for a merge; one open task per merge commit.

        A resubmitted merge replaces nothing: while an open task exists
        for the commit, generation refuses so the owner never faces two
        checklists for the same merge. Drafts (tasks awaiting pointers)
        are replaced in place by regeneration since they hold no verdicts.
        """
        merge_commit = merge_commit.strip()
        if not merge_commit:
            raise StoreError("E2E task needs a merge commit")
        if not isinstance(items, list) or not items:
            raise StoreError("E2E task needs at least one checklist item")
        if created_by not in INBOX_PARTIES:
            raise StoreError(f"E2E creator must be one of {INBOX_PARTIES}")
        self._check_e2e_items(items)
        existing, _total = self.e2e_tasks.list(limit=1000)
        for entry in existing:
            if not isinstance(entry, dict) or entry.get("merge_commit") != merge_commit:
                continue
            if entry.get("status") == "open":
                raise StoreError("An open E2E task already exists for this merge")
            if entry.get("status") == "draft":
                entry["title"] = title.strip() or f"E2E promotion for {merge_commit}"
                entry["items"] = items
                entry["range_base"] = (range_base or "").strip() or None
                self.e2e_tasks.put(entry["id"], entry)
                return entry
        now = _utc_now()
        record = {
            "id": uuid.uuid4().hex,
            "merge_commit": merge_commit,
            "range_base": (range_base or "").strip() or None,
            "title": title.strip() or f"E2E promotion for {merge_commit}",
            "items": items,
            "status": "draft" if draft else "open",
            "created_by": created_by,
            "project_id": project_id or self.default_project_id(),
            "created_at": now,
            "submitted_at": None,
            "report_id": None,
        }
        self.e2e_tasks.put(record["id"], record)
        return record

    @staticmethod
    def _check_e2e_items(items: list[dict]) -> None:
        """Shared checklist validation for filing and reauthoring."""
        from e2e_promotion import BEHAVIOR_AREA_IDS

        for item in items:
            if not isinstance(item, dict):
                raise StoreError("E2E checklist items must be objects")
            if item.get("kind") not in ("behavior", "regression", "nonbehavioral"):
                raise StoreError("E2E item kind must be behavior, regression or nonbehavioral")
            if item.get("area") not in BEHAVIOR_AREA_IDS:
                raise StoreError(f"Unknown E2E area: {item.get('area')}")
            if not str(item.get("id", "")).strip():
                raise StoreError("E2E items need ids")
            DashboardStores._check_item_steps(item)

    @staticmethod
    def _check_item_steps(item: dict) -> None:
        """Steps are optional (legacy tasks) but must be well-formed."""
        steps = item.get("steps")
        if steps is None:
            return
        if not isinstance(steps, list):
            raise StoreError("E2E item steps must be a list")
        for step in steps:
            if not isinstance(step, dict):
                raise StoreError("E2E steps must be objects")
            if not str(step.get("action", "")).strip() or not str(step.get("expected", "")).strip():
                raise StoreError("E2E steps need an action and an expected result")

    def submit_e2e_task(self, task_id: str, results: list[dict], verdict_by: str = "owner") -> dict:
        """Submit verdicts; submitting auto-builds the E2E report.

        Every pending item needs exactly one pass/fail verdict; the
        report (including carried ancestor approvals with warnings) is
        stored alongside the task. Submitted tasks are immutable, and
        drafts finalize before they can take verdicts. ``verdict_by``
        is "owner" or "agent" (machine-verdicted all-agent checklists).
        """
        from e2e_promotion import build_report

        record = self.e2e_tasks.get(task_id)
        if record is None:
            raise StoreError("E2E task not found")
        if record.get("status") == "draft":
            raise StoreError("E2E task is a draft awaiting pointers")
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
                "steps": entry.get("steps"),
            }
        if verdict_by not in ("owner", "agent"):
            raise StoreError("verdict_by must be owner or agent")
        try:
            report = build_report(record, submissions, verdict_by=verdict_by)
        except ValueError as exc:
            raise StoreError(str(exc)) from exc
        report["id"] = uuid.uuid4().hex
        self.e2e_reports.put(report["id"], report)
        record["status"] = "submitted"
        record["submitted_at"] = _utc_now()
        record["report_id"] = report["id"]
        self.e2e_tasks.put(task_id, record)
        followup_id = self._maybe_file_e2e_followup(record, report)
        return {"task": record, "report": report, "followup_id": followup_id}

    def _maybe_file_e2e_followup(self, record: dict, report: dict) -> str | None:
        """File one agent follow-up when fails or notes need action.

        A failed item means the behavior is broken; a note on a pass
        means the tester saw something worth considering; a bad-test
        flag means the steps themselves were untestable; an item whose
        every step is machine-runnable needs a human-test redesign.
        All land in a single AI-queue task so none dies in the report.
        Filing never fails the submit: a refusal is stamped on the task.
        """
        fails = []
        noted = []
        bad_tests = []
        mismatched = []
        redesign = []
        for entry in report.get("items", []):
            if entry.get("status") != "tested":
                continue
            notes = str(entry.get("notes", "") or "").strip()
            if entry.get("verdict") == "bad-test":
                bad_tests.append(entry)
            elif entry.get("verdict") == "fail":
                fails.append(entry)
            elif notes:
                noted.append(entry)
            if entry.get("agent_check_mismatches"):
                mismatched.append(entry)
            steps = entry.get("steps") or []
            if (
                steps
                and all(isinstance(step, dict) and step.get("agent_runnable") for step in steps)
                and entry.get("verdict") != "bad-test"
            ):
                redesign.append(entry)
        if not fails and not noted and not bad_tests and not mismatched and not redesign:
            return None
        merge = str(record.get("merge_commit") or "")
        parts = [f"{len(fails)} failed"] if fails else []
        if noted:
            parts.append(f"{len(noted)} noted")
        if bad_tests:
            parts.append(f"{len(bad_tests)} bad-test")
        if mismatched:
            parts.append(f"{len(mismatched)} mismatched")
        if redesign:
            parts.append(f"{len(redesign)} redesign")
        lines = [f"E2E report {report.get('id')} for merge {merge} needs action.", ""]
        for entry in fails:
            lines.append(f"FAIL {entry.get('id')} ({entry.get('behavior') or ''}):")
            lines.append(str(entry.get("notes", "") or "(no notes)").strip()[:2000] or "(no notes)")
            lines.append("")
        for entry in bad_tests:
            lines.append(f"BAD TEST DESIGN {entry.get('id')} (fix the test, not the product):")
            lines.append(str(entry.get("notes", "") or "").strip()[:2000])
            lines.append("")
        for entry in noted:
            lines.append(f"NOTE on {entry.get('id')} (passed):")
            lines.append(str(entry.get("notes", "") or "").strip()[:2000])
            lines.append("")
        for entry in mismatched:
            lines.append(f"MISMATCH on {entry.get('id')} (owner passed, agent check failed):")
            lines.append(
                "; ".join(str(action) for action in entry.get("agent_check_mismatches", []))[:2000]
            )
            lines.append("")
        for entry in redesign:
            actions = "; ".join(str(step.get("action", "")) for step in (entry.get("steps") or []))[
                :2000
            ]
            lines.append(
                f"REDESIGN {entry.get('id')} (all {len(entry.get('steps') or [])} steps "
                "machine-runnable; rewrite as human-observable checks):"
            )
            lines.append(actions or "(no step text)")
            lines.append(
                "Adopt the automatable coverage into pytest where missing; "
                "do not hand machine steps to the human tester again."
            )
            lines.append("")
        try:
            filed = self.create_inbox_task(
                title=f"E2E follow-up: {merge} ({', '.join(parts)})",
                body="\n".join(lines).strip(),
                task_type="task",
                created_by="supervisor",
                assignee="agent",
                metadata={
                    "author_source": "rule",
                    "kind": "e2e-followup",
                    "merge_commit": merge,
                    "report_id": report.get("id"),
                },
            )
        except StoreError as exc:
            record["followup_error"] = str(exc)
            self.e2e_tasks.put(record["id"], record)
            return None
        return str(filed["id"])

    def retry_e2e_followup(self, task_id: str) -> str | None:
        """Re-attempt a refused E2E follow-up filing; id of the filed task."""
        record = self.e2e_tasks.get(task_id)
        if record is None or not record.get("followup_error"):
            return None
        report_id = record.get("report_id")
        report = self.e2e_reports.get(str(report_id)) if report_id else None
        if report is None:
            return None
        filed_id = self._maybe_file_e2e_followup(record, report)
        if filed_id is not None:
            record.pop("followup_error", None)
            self.e2e_tasks.put(task_id, record)
        return filed_id

    def finalize_e2e_task(self, task_id: str, steps_by_item: dict) -> dict:
        """Turn a draft into an open task with finalized checkable steps.

        Called after the owner answers the pointer request: every
        pending behavior/regression item gets its authored steps, the
        pointers flag clears, and the task opens for testing.
        """
        from e2e_cases import validate_steps

        record = self.e2e_tasks.get(task_id)
        if record is None:
            raise StoreError("E2E task not found")
        if record.get("status") != "draft":
            raise StoreError("Only draft E2E tasks can be finalized")
        if not isinstance(steps_by_item, dict):
            raise StoreError("Finalize needs steps per item id")
        for item in record.get("items", []):
            if not isinstance(item, dict) or item.get("status") == "auto-pass":
                continue
            item_id = str(item.get("id", ""))
            if item_id not in steps_by_item:
                raise StoreError(f"Finalize needs steps for {item_id}")
            try:
                item["steps"] = validate_steps(steps_by_item[item_id])
            except ValueError as exc:
                raise StoreError(str(exc)) from exc
            item["needs_pointers"] = False
        record["status"] = "open"
        record["finalized_at"] = _utc_now()
        self.e2e_tasks.put(task_id, record)
        return record

    def open_resolved_draft(self, task_id: str) -> dict:
        """Open a draft whose items no longer need pointers.

        Used after partial agent verdicts complete the set: grounded
        generator steps plus validated agent steps are all checkable.
        Refuses drafts with remaining needs_pointers items.
        """
        record = self.e2e_tasks.get(task_id)
        if record is None:
            raise StoreError("E2E task not found")
        if record.get("status") != "draft":
            raise StoreError("Only draft E2E tasks can be opened")
        pending = [
            item
            for item in record.get("items", [])
            if isinstance(item, dict)
            and item.get("status") != "auto-pass"
            and item.get("needs_pointers", True)
        ]
        if pending:
            raise StoreError("Draft still needs pointers for open items")
        record["status"] = "open"
        record["finalized_at"] = _utc_now()
        self.e2e_tasks.put(task_id, record)
        return record

    def reauthor_e2e_items(
        self, task_id: str, items: list[dict], reauthored_by: str = "agent"
    ) -> dict:
        """Replace the checklist on an open, verdict-less task.

        Used when a filed checklist proves unusable (vague steps) and no
        verdicts exist yet: the new items must validate like a fresh
        filing, keep the task id/merge/title, and the replacement is
        stamped. Submitted tasks are immutable; drafts use finalize.
        """
        record = self.e2e_tasks.get(task_id)
        if record is None:
            raise StoreError("E2E task not found")
        if record.get("status") != "open":
            raise StoreError("Only open E2E tasks can be reauthored")
        if record.get("submitted_at") or record.get("report_id"):
            raise StoreError("E2E task already holds verdicts")
        if not isinstance(items, list) or not items:
            raise StoreError("E2E task needs at least one checklist item")
        if reauthored_by not in INBOX_PARTIES:
            raise StoreError(f"E2E reauthor must be one of {INBOX_PARTIES}")
        self._check_e2e_items(items)
        record["items"] = items
        record["reauthored_at"] = _utc_now()
        record["reauthored_by"] = reauthored_by
        self.e2e_tasks.put(task_id, record)
        return record

    def history_for_area(self, area: str, limit: int = 3) -> list[dict]:
        """Recent per-area verdicts, newest first — the forensic trail.

        Each entry names the tested commit and report so the owner can
        look up what worked, on which patch, at any moment.
        """
        reports, _total = self.e2e_reports.list(limit=1000)
        trail: list[dict] = []
        for report in sorted(
            (r for r in reports if isinstance(r, dict)),
            key=lambda r: str(r.get("built_utc") or ""),
            reverse=True,
        ):
            for entry in report.get("items", []):
                if not isinstance(entry, dict) or entry.get("area") != area:
                    continue
                if entry.get("verdict") not in ("pass", "fail"):
                    continue
                trail.append(
                    {
                        "report_id": report.get("id"),
                        "commit": entry.get("tested_on") or report.get("commit"),
                        "built_utc": report.get("built_utc"),
                        "verdict": entry.get("verdict"),
                        "verdict_by": entry.get("verdict_by"),
                    }
                )
            if len(trail) >= limit:
                break
        return trail[:limit]

    def save_e2e_draft_notes(self, task_id: str, item_id: str, notes: str) -> dict:
        """Save in-progress notes for one open checklist item.

        Drafts let the owner jot behaviour down while using the app;
        submitting still requires explicit per-item verdicts.
        """
        record = self.e2e_tasks.get(task_id)
        if record is None:
            raise StoreError("E2E task not found")
        if record.get("status") != "open":
            raise StoreError("E2E task is already submitted")
        if not isinstance(notes, str):
            raise StoreError("E2E draft notes must be a string")
        for item in record.get("items", []):
            if isinstance(item, dict) and item.get("id") == item_id:
                if item.get("status") == "auto-pass":
                    raise StoreError("Auto-passed items take no notes")
                item["draft_notes"] = notes
                self.e2e_tasks.put(task_id, record)
                return record
        raise StoreError("E2E item not found")

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

    def touch_chat_heartbeat(self, session_id: str) -> dict:
        """Record that the owner has the chat thread open (presence)."""
        record = self.get_chat_mode(session_id)
        record["last_seen_at"] = _utc_now()
        self.chat_modes.put(session_id, record)
        return record

    def park_chat_turn(self, session_id: str, text: str) -> dict:
        """Park one agent turn awaiting approval (ask-always policy)."""
        if not str(text).strip():
            raise StoreError("Parked turn needs text")
        record = self.get_chat_mode(session_id)
        if record.get("pending_turn"):
            raise StoreError("A turn is already parked for this chat")
        record["pending_turn"] = {"text": str(text), "parked_at": _utc_now()}
        record["updated_at"] = _utc_now()
        self.chat_modes.put(session_id, record)
        return record

    def take_parked_turn(self, session_id: str) -> dict:
        """Take (and clear) the parked turn; raises when none is parked."""
        record = self.get_chat_mode(session_id)
        pending = record.get("pending_turn")
        if not isinstance(pending, dict) or not str(pending.get("text", "")).strip():
            raise StoreError("No parked turn for this chat")
        record["pending_turn"] = None
        record["updated_at"] = _utc_now()
        self.chat_modes.put(session_id, record)
        return pending
