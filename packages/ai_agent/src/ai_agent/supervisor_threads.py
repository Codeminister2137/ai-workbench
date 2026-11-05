"""Supervisor planning threads over file-backed dashboard collections.

Adapted from remote-operator ``supervisor.py`` mechanics — threads carry
chat history plus one pending plan approval, and approving a plan binds the
exact reviewed plan bytes through a plan-digest + nonce + expiry triple —
onto P6 data shapes: threads and plans are plain JSON records in injected
file-backed collections (``JsonCollection``-compatible), never sqlite task
rows.

Approval has two modes. Planning-only approval (``execute=False``) records
the decision and stops. Executable approval (``execute=True``) additionally
enqueues one approval-gated run: a queued run record plus a linked inbox
decision in the step-2 chat wake-path shape, so the run drain applies its
uniform inbox-approval rule before anything executes.
"""

from __future__ import annotations

import hashlib
import secrets
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from ai_agent.fanout import FanoutPolicy

PLAN_APPROVAL_SECONDS = 600
MAX_TOPIC_CHARS = 4000
MAX_MESSAGE_CHARS = 4000
MAX_PLAN_BODY_CHARS = 4000


class RecordStore(Protocol):
    """Structural twin of the dashboard ``JsonCollection`` (get/put/list)."""

    def get(self, item_id: str) -> dict | None: ...
    def put(self, item_id: str, payload: dict) -> object: ...
    def list(self, *, limit: int = 20, offset: int = 0) -> tuple[list[dict], int]: ...


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _scripted_reply(thread: dict) -> str:
    count = sum(1 for turn in thread.get("history", []) if turn.get("role") == "user")
    return (
        "[SCRIPTED OFFLINE REFERENCE] "
        f"Recorded message {count}. "
        "Live AI is not connected in this thread, so this is a placeholder "
        "reply, not an answer. Describe what you want to build; when "
        "requirements are complete, ask for a plan artifact."
    )


class SupervisorThreads:
    """Planning threads bound to injected file-backed collections.

    ``threads`` holds thread records (history, pending approval),
    ``plans`` holds reviewable plan records in dashboard shape
    (``{id, title, status, body, ...}``). ``runs`` plus ``create_approval``
    are only needed for executable approval; planning-only use leaves them
    unset. ``reply_fn`` maps a thread record to the next assistant reply
    text (a deterministic scripted placeholder by default, so posting never
    needs model wiring). ``is_cancelled`` is an optional cancellation hook
    consulted at approve time.
    """

    def __init__(
        self,
        *,
        threads: RecordStore,
        plans: RecordStore,
        runs: RecordStore | None = None,
        create_approval: Callable[..., dict] | None = None,
        reply_fn: Callable[[dict], str] | None = None,
        is_cancelled: Callable[[str], bool] | None = None,
        now: Callable[[], float] | None = None,
    ) -> None:
        self._threads = threads
        self._plans = plans
        self._runs = runs
        self._create_approval = create_approval
        self._reply_fn = reply_fn
        self._is_cancelled = is_cancelled
        self._now = now or time.time

    def _iso_now(self) -> str:
        return datetime.fromtimestamp(self._now(), UTC).isoformat()

    def _thread(self, thread_id: str) -> dict:
        if not isinstance(thread_id, str) or not thread_id.isalnum() or len(thread_id) != 32:
            raise ValueError("Invalid thread identifier")
        thread = self._threads.get(thread_id)
        if thread is None or thread.get("id") != thread_id or not thread.get("supervisor_thread"):
            raise ValueError("Unknown supervisor thread")
        return thread

    def open_thread(self, topic: str, *, title: str | None = None) -> dict:
        """Open a planning thread for ``topic``; returns its summary."""
        if not isinstance(topic, str) or not topic.strip() or len(topic) > MAX_TOPIC_CHARS:
            raise ValueError(f"Thread requires a 1-{MAX_TOPIC_CHARS} character topic")
        thread_id = uuid.uuid4().hex
        now_iso = self._iso_now()
        thread = {
            "id": thread_id,
            "supervisor_thread": True,
            "title": (title or "").strip() or topic.strip()[:60],
            "topic": topic,
            "status": "open",
            "history": [],
            "plan_id": None,
            "approval": None,
            "created_at_utc": now_iso,
            "updated_at_utc": now_iso,
        }
        self._threads.put(thread_id, thread)
        return {"id": thread_id, "topic": topic, "status": "open"}

    def get_thread(self, thread_id: str) -> dict:
        """Return one thread record with its history."""
        return self._thread(thread_id)

    def list_threads(self, limit: int = 20) -> list[dict]:
        """Return id/topic/status summaries for threads, newest first."""
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError(f"limit must be an integer between 1 and 50: got {limit!r}")
        items, _total = self._threads.list(limit=limit)
        return [
            {
                "id": item["id"],
                "topic": str(item.get("topic", ""))[:160],
                "status": item.get("status"),
            }
            for item in items
            if item.get("supervisor_thread")
        ]

    def post_message(self, thread_id: str, text: str) -> dict:
        """Append a user message and generate the assistant planning reply."""
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_MESSAGE_CHARS:
            raise ValueError(f"Message requires 1-{MAX_MESSAGE_CHARS} characters")
        thread = self._thread(thread_id)
        if thread["status"] != "open":
            raise ValueError("Thread is closed to new messages")
        thread.setdefault("history", []).append({"role": "user", "text": text})
        if self._reply_fn is None:
            reply, route = _scripted_reply(thread), "scripted"
        else:
            reply, route = self._reply_fn(thread), "host"
        thread["history"].append({"role": "assistant", "text": reply, "route": route})
        thread["updated_at_utc"] = self._iso_now()
        self._threads.put(thread_id, thread)
        return {"reply": reply, "route": route}

    def write_plan(self, thread_id: str, *, title: str | None = None) -> dict:
        """Render the plan artifact from the transcript; returns it with a nonce."""
        thread = self._thread(thread_id)
        if thread["status"] not in ("open", "planned"):
            raise ValueError("Thread is closed to new plans")
        if thread["status"] == "planned":
            approval = thread.get("approval") or {}
            if self._now() < (approval.get("expires") or 0):
                raise ValueError("A plan is already pending approval")
            # Expired plan: fall through and mint a fresh approval window.
        user_turns = [
            turn["text"] for turn in thread.get("history", []) if turn.get("role") == "user"
        ]
        if not user_turns:
            raise ValueError("Thread has no requirements yet")
        lines = [f"# Plan: {thread.get('topic', '')}", ""]
        for index, text in enumerate(user_turns, 1):
            lines.append(f"{index}. {text}")
        lines += ["", "Assistant turns recorded: ", ""]
        for turn in thread.get("history", []):
            if turn.get("role") == "assistant":
                lines.append(f"- ({turn.get('route', 'unknown')}) {turn.get('text', '')[:200]}")
        markdown = "\n".join(lines)
        plan_digest = _sha256(markdown)
        approval = {
            "nonce": secrets.token_hex(16),
            "plan_digest": plan_digest,
            "plan_id": thread.get("plan_id") or uuid.uuid4().hex,
            "expires": self._now() + PLAN_APPROVAL_SECONDS,
        }
        now_iso = self._iso_now()
        existing = self._plans.get(approval["plan_id"])
        plan_record = {
            "id": approval["plan_id"],
            "title": (title or "").strip()
            or thread.get("title")
            or str(thread.get("topic", ""))[:60],
            "status": "proposed",
            "body": markdown,
            "thread_id": thread_id,
            "digest": plan_digest,
            "created_at_utc": (existing or {}).get("created_at_utc", now_iso),
            "updated_at_utc": now_iso,
        }
        self._plans.put(approval["plan_id"], plan_record)
        thread["plan_id"] = approval["plan_id"]
        thread["approval"] = approval
        thread["status"] = "planned"
        thread["updated_at_utc"] = now_iso
        self._threads.put(thread_id, thread)
        return {
            "plan_id": approval["plan_id"],
            "digest": plan_digest,
            "markdown": markdown,
            "nonce": approval["nonce"],
            "expires": approval["expires"],
        }

    def approve_plan(
        self,
        thread_id: str,
        nonce: str,
        *,
        execute: bool = True,
        fanout_policy: str = "restricted",
    ) -> dict:
        """Approve the exact reviewed plan bytes; optionally enqueue a run job.

        With ``execute=False`` (planning-only mode) the plan is approved
        and recorded but no run is queued. With ``execute=True`` one queued
        run plus its linked inbox approval decision are written first (so a
        refusal leaves the thread planned with its nonce live for retry),
        and only then is the approval recorded.
        """
        thread = self._thread(thread_id)
        approval = thread.get("approval")
        if thread["status"] != "planned" or not approval:
            raise ValueError("No pending plan approval")
        if not isinstance(nonce, str):
            raise ValueError("Invalid or expired approval")
        try:
            nonce.encode("ascii")
        except UnicodeEncodeError:
            raise ValueError("Invalid or expired approval") from None
        expected = approval.get("nonce")
        if (
            not isinstance(expected, str)
            or not secrets.compare_digest(expected, nonce)
            or self._now() >= approval.get("expires", 0)
        ):
            raise ValueError("Invalid or expired approval")
        if self._is_cancelled is not None and self._is_cancelled(thread_id):
            raise ValueError("Cancellation invalidated this approval")
        plan_id = approval.get("plan_id")
        plan = self._plans.get(plan_id) if isinstance(plan_id, str) else None
        body = plan.get("body", "") if plan is not None else ""
        if (
            plan is None
            or not isinstance(body, str)
            or _sha256(body) != approval.get("plan_digest")
        ):
            thread["status"] = "open"
            thread["approval"] = None
            thread["updated_at_utc"] = self._iso_now()
            self._threads.put(thread_id, thread)
            if isinstance(plan, dict):
                plan["status"] = "invalidated"
                plan["updated_at_utc"] = thread["updated_at_utc"]
                self._plans.put(plan["id"], plan)
            raise ValueError("Reviewed plan changed")
        if type(execute) is not bool:
            raise ValueError("execute must be true or false")
        if execute and (self._runs is None or self._create_approval is None):
            raise ValueError("Executable approval needs runs and inbox sinks")
        run_id: str | None = None
        inbox_id: str | None = None
        if execute:
            assert self._runs is not None and self._create_approval is not None
            policy = FanoutPolicy.coerce(fanout_policy)
            run_id = uuid.uuid4().hex
            run_title = str(plan.get("title") or thread.get("topic", ""))[:60]
            decision = self._create_approval(
                title=f"Approve agent run: {run_title}",
                body=(
                    f"Approved plan {approval['plan_digest'][:12]} queued an agent run "
                    f"(fan-out: {policy.value}).\n\n"
                    "Approve to let a run worker execute it; "
                    "Reject leaves it parked (never executed)."
                ),
                task_type="decision",
                plan_id=plan_id,
                task_id=run_id,
                context_refs=[f"run:{run_id}", f"plan:{plan_id}", f"thread:{thread_id}"],
                options=["Approve", "Reject"],
            )
            inbox_id = decision["id"]
            now_iso = self._iso_now()
            self._runs.put(
                run_id,
                {
                    "id": run_id,
                    "title": run_title,
                    "status": "queued",
                    "body": body[:MAX_PLAN_BODY_CHARS],
                    "body_truncated": len(body) > MAX_PLAN_BODY_CHARS,
                    "origin": "plan",
                    "plan_id": plan_id,
                    "thread_id": thread_id,
                    "plan_digest": approval["plan_digest"],
                    "fanout_policy": policy.value,
                    "fanout_effective": policy.value,
                    "inbox_id": inbox_id,
                    "created_at_utc": now_iso,
                    "updated_at_utc": now_iso,
                },
            )
        now_iso = self._iso_now()
        thread["status"] = "approved"
        thread["approval"] = None
        thread["updated_at_utc"] = now_iso
        self._threads.put(thread_id, thread)
        plan["status"] = "approved"
        plan["updated_at_utc"] = now_iso
        self._plans.put(plan["id"], plan)
        if not execute:
            return {"plan_id": plan_id, "run_id": None, "status": "approved"}
        return {"plan_id": plan_id, "run_id": run_id, "status": "queued", "inbox_id": inbox_id}
