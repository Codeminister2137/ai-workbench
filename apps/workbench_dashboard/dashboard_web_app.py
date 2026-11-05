"""Workbench dashboard: local status, chat, plans, runs, and owner inbox."""

from __future__ import annotations

import argparse
import json
import socket
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlparse

from ai_agent.staged_edits import (
    ProjectRoots,
    StagedConflictError,
    StagedEditError,
    apply_staged,
    approve_staged,
    review_staged,
)
from ai_orchestrator.evidence import merge_probe_eval
from ai_provider.chat_transcripts import SQLiteChatTranscriptStore
from dashboard_chat import DashboardChat
from dashboard_config import DEFAULT_CONFIG_PATH, DEFAULT_DATA_DIR, DashboardConfig, load_config
from dashboard_stores import DashboardStores, StoreError, effective_fanout_policy

ROOT = Path(__file__).parent
STATIC_ROOT = ROOT / "web"
REPO_ROOT = ROOT.parent.parent
MAX_REQUEST_BYTES = 512_000
REQUEST_TIMEOUT_SECONDS = 5.0
DEFAULT_PORT = 8766


class InvalidRequest(ValueError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def latest_snapshot(directory: Path, prefix: str) -> tuple[Path | None, list[dict]]:
    """Read the newest `{prefix}-*.json` snapshot rows, tolerating absence."""
    try:
        files = sorted(directory.glob(f"{prefix}-*.json"))
    except OSError:
        return None, []
    if not files:
        return None, []
    latest = files[-1]
    try:
        payload = json.loads(latest.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError, OSError):
        return latest, []
    rows = payload if isinstance(payload, list) else []
    return latest, [row for row in rows if isinstance(row, dict)]


def with_fanout_policy(run: dict) -> dict:
    """Copy one run record with its effective fan-out policy resolved.

    Response-only enrichment: the stored file is never rewritten, so records
    that predate the field simply read as ``unknown``.
    """
    return {**run, "fanout_effective": effective_fanout_policy(run)}


def evidence_snapshot(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Merge the newest probe/eval snapshots into dashboard evidence rows."""
    probe_file, probes = latest_snapshot(repo_root / "artifacts" / "route-probes", "route-probe")
    eval_file, evals = latest_snapshot(repo_root / "artifacts" / "route-evals", "route-eval")
    merged = merge_probe_eval(probes, evals)
    return {
        "available": bool(probes or evals),
        "probe_snapshot": probe_file.name if probe_file else None,
        "eval_snapshot": eval_file.name if eval_file else None,
        "routes": [
            {"route": item.route, "reachable": item.reachable, "passed_eval": item.passed_eval}
            for item in merged
        ],
    }


class DashboardRequestHandler(SimpleHTTPRequestHandler):
    config_path = DEFAULT_CONFIG_PATH
    data_dir = DEFAULT_DATA_DIR
    repo_root = REPO_ROOT

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_ROOT), **kwargs)

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(REQUEST_TIMEOUT_SECONDS)

    def _trusted_request(self) -> bool:
        port = cast(tuple[str, int], self.server.server_address)[1]
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        host = self.headers.get("Host")
        origin = self.headers.get("Origin")
        if (
            len(self.headers.get_all("Host", [])) != 1
            or host not in hosts
            or (origin is not None and origin != f"http://{host}")
        ):
            self.send_error(HTTPStatus.FORBIDDEN, "Untrusted request origin")
            return False
        return True

    def _stores(self) -> DashboardStores:
        return DashboardStores(self.data_dir)

    def _chat(self, config: DashboardConfig) -> DashboardChat:
        store = SQLiteChatTranscriptStore(self.data_dir / "chats.sqlite3")
        return DashboardChat(store, config, self.repo_root)

    def _project_roots(self, config: DashboardConfig) -> ProjectRoots:
        """Build the request-time work-root allowlist (fail-closed).

        Every entry must be an existing directory on every request; a root
        overlapping the dashboard data dir, the checkout venv, or the
        checkout git dir is refused. Raises ``StagedEditError``.
        """
        return ProjectRoots(
            config.work_roots,
            protected_dirs=(
                self.data_dir,
                self.repo_root / ".venv",
                self.repo_root / ".git",
            ),
        )

    def do_GET(self) -> None:
        if not self._trusted_request():
            return
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            self.path = "/index.html"
            return super().do_GET()
        if not path.startswith("/api/"):
            return super().do_GET()
        try:
            config = load_config(self.config_path)
        except ValueError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=500)
        try:
            if path == "/api/status":
                return self._send_json({"ok": True, **self._status(config)})
            if path == "/api/evidence":
                return self._send_json({"ok": True, **evidence_snapshot(self.repo_root)})
            if path == "/api/work-roots":
                return self._send_work_roots(config)
            if path == "/api/chat/sessions":
                return self._send_chat_sessions(config)
            if path.startswith("/api/chat/sessions/") and path.endswith("/messages"):
                session_id = path[len("/api/chat/sessions/") : -len("/messages")]
                return self._send_chat_messages(config, session_id)
            if path == "/api/plans":
                return self._send_collection(self._stores().plans, parsed.query)
            if path.startswith("/api/plans/"):
                return self._send_item(self._stores().plans, path[len("/api/plans/") :])
            if path == "/api/runs":
                return self._send_collection(
                    self._stores().runs, parsed.query, enrich=with_fanout_policy
                )
            if path.startswith("/api/runs/") and path.endswith("/receipts"):
                run_id = path[len("/api/runs/") : -len("/receipts")]
                return self._send_run_receipts(run_id)
            if path.startswith("/api/runs/") and path.endswith("/staged"):
                run_id = path[len("/api/runs/") : -len("/staged")]
                return self._send_run_staged(config, run_id)
            if path.startswith("/api/runs/"):
                return self._send_item(
                    self._stores().runs,
                    path[len("/api/runs/") :],
                    enrich=with_fanout_policy,
                )
            if path == "/api/inbox":
                return self._send_inbox(parsed.query)
            if path == "/api/ideas":
                return self._send_ideas(parsed.query)
            if path.startswith("/api/inbox/"):
                return self._send_item(self._stores().inbox, path[len("/api/inbox/") :])
            if path.startswith("/api/ideas/"):
                return self._send_item(self._stores().ideas, path[len("/api/ideas/") :])
        except (StoreError, ValueError) as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        return self._send_json({"ok": False, "error": "Unknown endpoint"}, status=404)

    def do_POST(self) -> None:
        if not self._trusted_request():
            return
        path = urlparse(self.path).path
        if not path.startswith("/api/"):
            self.send_error(HTTPStatus.NOT_FOUND, "Unknown endpoint")
            return
        try:
            payload = self._read_json_body()
            config = load_config(self.config_path)
        except InvalidRequest as exc:
            self.close_connection = True
            return self._send_json({"ok": False, "error": str(exc)}, status=exc.status)
        except ValueError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=500)
        try:
            if path == "/api/chat/sessions":
                return self._create_chat_session(config, payload)
            if path.startswith("/api/chat/sessions/") and path.endswith("/messages"):
                session_id = path[len("/api/chat/sessions/") : -len("/messages")]
                return self._post_chat_message(config, session_id, payload)
            if path.startswith("/api/chat/sessions/") and path.endswith("/rename"):
                session_id = path[len("/api/chat/sessions/") : -len("/rename")]
                return self._rename_chat_session(config, session_id, payload)
            if path.startswith("/api/chat/sessions/") and path.endswith("/delete"):
                session_id = path[len("/api/chat/sessions/") : -len("/delete")]
                return self._delete_chat_session(config, session_id)
            if path.startswith("/api/chat/sessions/") and path.endswith("/run-request"):
                session_id = path[len("/api/chat/sessions/") : -len("/run-request")]
                return self._request_chat_run(config, session_id, payload)
            if path == "/api/inbox":
                return self._create_inbox_task(payload)
            if path == "/api/ideas":
                return self._create_idea(payload)
            if path.startswith("/api/inbox/") and path.endswith("/answer"):
                item_id = path[len("/api/inbox/") : -len("/answer")]
                return self._answer_inbox_task(item_id, payload)
            if path.startswith("/api/inbox/") and path.endswith("/close"):
                item_id = path[len("/api/inbox/") : -len("/close")]
                return self._close_inbox_task(item_id)
            if path.startswith("/api/plans/") and path.endswith("/approve"):
                plan_id = path[len("/api/plans/") : -len("/approve")]
                return self._decide_plan(plan_id, payload)
            if path.startswith("/api/ideas/") and path.endswith("/review"):
                item_id = path[len("/api/ideas/") : -len("/review")]
                return self._review_idea(item_id, payload)
            if path.startswith("/api/runs/") and path.endswith("/report-request"):
                run_id = path[len("/api/runs/") : -len("/report-request")]
                return self._request_run_report(run_id)
            if path.startswith("/api/runs/") and path.endswith("/approve-staged"):
                run_id = path[len("/api/runs/") : -len("/approve-staged")]
                return self._approve_run_staged(config, run_id, payload)
        except (StoreError, ValueError) as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        return self._send_json({"ok": False, "error": "Unknown endpoint"}, status=404)

    def _status(self, config: DashboardConfig) -> dict[str, Any]:
        stores = self._stores()
        evidence = evidence_snapshot(self.repo_root)
        plans, plan_total = stores.plans.list(limit=1)
        runs, _run_total = stores.runs.list(limit=3)
        current_plan = plans[0] if plans else None
        return {
            "title": config.title,
            "provider": config.provider,
            "model": config.model,
            "open_inbox": stores.open_inbox_count(),
            "new_ideas": stores.new_idea_count(),
            "plan_total": plan_total,
            "current_plan": (
                {"id": current_plan.get("id"), "title": current_plan.get("title")}
                if current_plan
                else None
            ),
            "recent_runs": [
                {"id": run.get("id"), "title": run.get("title"), "status": run.get("status")}
                for run in runs
            ],
            "evidence": {
                "available": evidence["available"],
                "routes": len(evidence["routes"]),
                "passed": sum(1 for row in evidence["routes"] if row["passed_eval"] is True),
            },
        }

    def _send_chat_sessions(self, config: DashboardConfig) -> None:
        sessions = self._chat(config).list_sessions()
        self._send_json(
            {
                "ok": True,
                "sessions": [
                    {
                        "id": record.session_id,
                        "title": record.title,
                        "updated_at_utc": record.updated_at_utc,
                        "privacy_class": record.privacy_class,
                    }
                    for record in sessions
                ],
            }
        )

    def _send_chat_messages(self, config: DashboardConfig, session_id: str) -> None:
        try:
            messages = self._chat(config).list_messages(session_id)
        except ValueError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=404)
        self._send_json(
            {
                "ok": True,
                "messages": [
                    {
                        "id": message.message_id,
                        "order": message.message_order,
                        "role": message.role,
                        "content": message.content,
                        "provider": message.provider,
                        "model": message.model,
                    }
                    for message in messages
                ],
            }
        )

    def _create_chat_session(self, config: DashboardConfig, payload: dict) -> None:
        title = payload.get("title", "")
        if not isinstance(title, str):
            return self._send_json({"ok": False, "error": "Title must be a string"}, status=400)
        record = self._chat(config).create_session(title=title)
        self._send_json({"ok": True, "id": record.session_id, "title": record.title})

    def _post_chat_message(self, config: DashboardConfig, session_id: str, payload: dict) -> None:
        text = payload.get("text", "")
        if not isinstance(text, str) or not text.strip():
            return self._send_json({"ok": False, "error": "Message text is required"}, status=400)
        try:
            outcome = self._chat(config).send(session_id, text)
        except ValueError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=404)
        self._send_json(
            {
                "ok": outcome.execution_status == "completed",
                "response_text": outcome.response_text,
                "execution_status": outcome.execution_status,
                "failure_reason": outcome.failure_reason,
                "provider": outcome.provider,
                "model": outcome.model,
            }
        )

    def _rename_chat_session(self, config: DashboardConfig, session_id: str, payload: dict) -> None:
        title = payload.get("title", "")
        if not isinstance(title, str) or not title.strip():
            return self._send_json({"ok": False, "error": "Title must not be empty"}, status=400)
        try:
            record = self._chat(config).rename_session(session_id, title=title)
        except ValueError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=404)
        self._send_json({"ok": True, "id": record.session_id, "title": record.title})

    def _delete_chat_session(self, config: DashboardConfig, session_id: str) -> None:
        try:
            self._chat(config).delete_session(session_id)
        except ValueError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=404)
        self._send_json({"ok": True, "id": session_id})

    def _request_chat_run(self, config: DashboardConfig, session_id: str, payload: dict) -> None:
        text = payload.get("text", "")
        if not isinstance(text, str) or not text.strip():
            return self._send_json({"ok": False, "error": "Message text is required"}, status=400)
        title = payload.get("title", "")
        if not isinstance(title, str):
            return self._send_json({"ok": False, "error": "Title must be a string"}, status=400)
        project = payload.get("project")
        if project is not None and (not isinstance(project, str) or not project.strip()):
            return self._send_json(
                {"ok": False, "error": "Project must be a root id or path"}, status=400
            )
        project_id: str | None = None
        if project:
            try:
                roots = self._project_roots(config)
            except StagedEditError as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=500)
            try:
                project_id = str(roots.select(project))
            except StagedEditError as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        try:
            receipt = self._chat(config).request_run(
                session_id,
                text,
                stores=self._stores(),
                title=title or None,
                project=project_id,
            )
        except (StoreError, ValueError) as exc:
            code = 404 if "not found" in str(exc).lower() else 400
            return self._send_json({"ok": False, "error": str(exc)}, status=code)
        self._send_json(
            {
                "ok": True,
                "run_id": receipt.run_id,
                "inbox_id": receipt.inbox_id,
                "status": receipt.status,
                "fanout_effective": receipt.fanout_effective,
            }
        )

    def _send_collection(
        self, collection, query: str, *, enrich: Callable[[dict], dict] | None = None
    ) -> None:
        params = parse_qs(query)
        try:
            limit = min(max(int(params.get("limit", ["20"])[0]), 1), 100)
            offset = max(int(params.get("offset", ["0"])[0]), 0)
        except ValueError:
            return self._send_json({"ok": False, "error": "Invalid limit or offset"}, status=400)
        items, total = collection.list(limit=limit, offset=offset)
        if enrich is not None:
            items = [enrich(item) for item in items]
        self._send_json({"ok": True, "items": items, "total": total})

    def _send_item(
        self, collection, item_id: str, *, enrich: Callable[[dict], dict] | None = None
    ) -> None:
        item = collection.get(item_id)
        if item is None:
            return self._send_json({"ok": False, "error": "Not found"}, status=404)
        if enrich is not None:
            item = enrich(item)
        self._send_json({"ok": True, "item": item})

    def _send_inbox(self, query: str) -> None:
        params = parse_qs(query)
        wanted = params.get("status", [None])[0]
        if wanted is not None and wanted not in {"open", "answered", "closed"}:
            return self._send_json({"ok": False, "error": "Invalid status filter"}, status=400)
        items, _total = self._stores().inbox.list(limit=100)
        if wanted is not None:
            items = [item for item in items if item.get("status") == wanted]
        self._send_json({"ok": True, "items": items, "total": len(items)})

    def _create_inbox_task(self, payload: dict) -> None:
        stores = self._stores()
        if not stores.check_supervisor_token(self.headers.get("X-Supervisor-Token")):
            return self._send_json({"ok": False, "error": "Supervisor token required"}, status=403)
        title = payload.get("title", "")
        body = payload.get("body", "")
        task_type = payload.get("type", "")
        if not all(isinstance(value, str) for value in (title, body, task_type)):
            return self._send_json(
                {"ok": False, "error": "title, body, and type must be strings"}, status=400
            )
        record = stores.create_inbox_task(
            title=title,
            body=body,
            task_type=task_type,
            plan_id=payload.get("plan_id"),
            task_id=payload.get("task_id"),
            context_refs=payload.get("context_refs"),
            options=payload.get("options"),
        )
        self._send_json({"ok": True, "id": record["id"]})

    def _answer_inbox_task(self, item_id: str, payload: dict) -> None:
        answer = payload.get("answer", "")
        option_index = payload.get("option_index")
        if not isinstance(answer, str) or (
            option_index is not None and not isinstance(option_index, int)
        ):
            return self._send_json({"ok": False, "error": "Invalid answer payload"}, status=400)
        try:
            record = self._stores().answer_inbox_task(
                item_id, answer=answer, option_index=option_index
            )
        except StoreError as exc:
            status = 404 if "not found" in str(exc).lower() else 400
            return self._send_json({"ok": False, "error": str(exc)}, status=status)
        self._send_json({"ok": True, "id": record["id"], "status": record["status"]})

    def _close_inbox_task(self, item_id: str) -> None:
        try:
            record = self._stores().close_inbox_task(item_id)
        except StoreError as exc:
            status = 404 if "not found" in str(exc).lower() else 400
            return self._send_json({"ok": False, "error": str(exc)}, status=status)
        self._send_json({"ok": True, "id": record["id"], "status": record["status"]})

    def _decide_plan(self, plan_id: str, payload: dict) -> None:
        approved = payload.get("approved")
        if type(approved) is not bool:
            return self._send_json(
                {"ok": False, "error": "approved must be true or false"}, status=400
            )
        try:
            record = self._stores().decide_plan(plan_id, approved=approved)
        except StoreError as exc:
            status = 404 if "not found" in str(exc).lower() else 400
            return self._send_json({"ok": False, "error": str(exc)}, status=status)
        self._send_json({"ok": True, "id": record["id"], "status": record["status"]})

    def _send_run_receipts(self, run_id: str) -> None:
        try:
            receipts = self._stores().get_run_receipts(run_id)
        except StoreError as exc:
            status = 404 if "not found" in str(exc).lower() else 400
            return self._send_json({"ok": False, "error": str(exc)}, status=status)
        self._send_json({"ok": True, "receipts": receipts})

    def _send_work_roots(self, config: DashboardConfig) -> None:
        try:
            roots = self._project_roots(config)
        except StagedEditError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=500)
        self._send_json(
            {
                "ok": True,
                "roots": [
                    {"id": entry.id, "path": entry.path, "display_name": entry.display_name}
                    for entry in roots.entries()
                ],
            }
        )

    def _send_run_staged(self, config: DashboardConfig, run_id: str) -> None:
        try:
            run = self._stores().runs.get(run_id)
        except StoreError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if run is None:
            return self._send_json({"ok": False, "error": "Not found"}, status=404)
        staged = run.get("staged") or []
        if not staged:
            return self._send_json({"ok": True, "files": []})
        if not isinstance(staged, list):
            return self._send_json(
                {"ok": False, "error": "Run staged files are malformed"}, status=400
            )
        project_id = run.get("project_id")
        if not isinstance(project_id, str) or not project_id:
            return self._send_json({"ok": False, "error": "Run has no project root"}, status=400)
        try:
            roots = self._project_roots(config)
        except StagedEditError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=500)
        try:
            root = roots.select(project_id)
            files = review_staged(root, staged)
        except StagedEditError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        self._send_json({"ok": True, "files": files})

    def _send_ideas(self, query: str) -> None:
        from dashboard_stores import IDEA_SOURCES, IDEA_STATUSES

        params = parse_qs(query)
        wanted_status = params.get("status", [None])[0]
        wanted_source = params.get("source", [None])[0]
        if wanted_status is not None and wanted_status not in IDEA_STATUSES:
            return self._send_json({"ok": False, "error": "Invalid status filter"}, status=400)
        if wanted_source is not None and wanted_source not in IDEA_SOURCES:
            return self._send_json({"ok": False, "error": "Invalid source filter"}, status=400)
        items, _total = self._stores().ideas.list(limit=100)
        if wanted_status is not None:
            items = [item for item in items if item.get("status") == wanted_status]
        if wanted_source is not None:
            items = [item for item in items if item.get("source") == wanted_source]
        self._send_json({"ok": True, "items": items, "total": len(items)})

    def _create_idea(self, payload: dict) -> None:
        title = payload.get("title", "")
        body = payload.get("body", "")
        source = payload.get("source", "owner")
        contact = payload.get("contact")
        if not all(isinstance(value, str) for value in (title, body, source)):
            return self._send_json(
                {"ok": False, "error": "title, body, and source must be strings"}, status=400
            )
        if contact is not None and not isinstance(contact, str):
            return self._send_json({"ok": False, "error": "contact must be a string"}, status=400)
        try:
            record = self._stores().create_idea(
                title=title, body=body, source=source, contact=contact
            )
        except StoreError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        self._send_json({"ok": True, "id": record["id"]})

    def _review_idea(self, item_id: str, payload: dict) -> None:
        status = payload.get("status", "")
        decision = payload.get("decision", "")
        if not isinstance(status, str) or not isinstance(decision, str):
            return self._send_json({"ok": False, "error": "Invalid review payload"}, status=400)
        try:
            record = self._stores().set_idea_status(item_id, status=status, decision=decision)
        except StoreError as exc:
            code = 404 if "not found" in str(exc).lower() else 400
            return self._send_json({"ok": False, "error": str(exc)}, status=code)
        self._send_json({"ok": True, "id": record["id"], "status": record["status"]})

    def _request_run_report(self, run_id: str) -> None:
        try:
            run = self._stores().runs.get(run_id)
        except StoreError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if run is None:
            return self._send_json({"ok": False, "error": "Not found"}, status=404)
        if run.get("report"):
            return self._send_json({"ok": True, "id": run_id, "report": True})
        if run.get("report_request_id"):
            return self._send_json(
                {"ok": True, "id": run.get("report_request_id"), "deduped": True}
            )
        try:
            record = self._stores().create_inbox_task(
                title=f"Generate report for {run.get('title') or run_id}",
                body=(
                    "Owner requested a completion report. Write it, attach it "
                    "as the run's `report` field, then close this task."
                ),
                task_type="order",
                task_id=run_id,
                context_refs=[f"run:{run_id}"],
            )
        except StoreError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        run["report_requested"] = True
        run["report_request_id"] = record["id"]
        self._stores().runs.put(run_id, run)
        self._send_json({"ok": True, "id": record["id"]})

    def _approve_run_staged(self, config: DashboardConfig, run_id: str, payload: dict) -> None:
        approved = payload.get("approved")
        if type(approved) is not bool:
            return self._send_json(
                {"ok": False, "error": "approved must be true or false"}, status=400
            )
        try:
            run = self._stores().runs.get(run_id)
        except StoreError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if run is None:
            return self._send_json({"ok": False, "error": "Not found"}, status=404)
        staged = run.get("staged") or []
        if not staged or not isinstance(staged, list):
            return self._send_json({"ok": False, "error": "Run has no staged changes"}, status=400)
        now = datetime.now(UTC).isoformat()
        if not approved:
            run["staged_approved"] = False
            run["staged_applied"] = False
            run["updated_at_utc"] = now
            try:
                self._stores().runs.put(run_id, run)
            except StoreError as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
            return self._send_json({"ok": True, "id": run_id, "applied": []})
        project_id = run.get("project_id")
        if not isinstance(project_id, str) or not project_id:
            return self._send_json({"ok": False, "error": "Run has no project root"}, status=400)
        try:
            roots = self._project_roots(config)
        except StagedEditError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=500)
        try:
            approval = approve_staged(roots, project_id, staged)
            applied = apply_staged(roots.select(project_id), staged)
        except StagedConflictError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=409)
        except StagedEditError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        run["staged_approved"] = True
        run["staged_applied"] = True
        run["staged_checks"] = approval["checks"]
        run["staged_applied_at"] = now
        run["updated_at_utc"] = now
        try:
            self._stores().runs.put(run_id, run)
        except StoreError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        self._send_json({"ok": True, "id": run_id, "applied": applied})

    def _send_json(self, payload: dict | list, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        media_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if media_type != "application/json":
            raise InvalidRequest(415, "Content-Type must be application/json")
        lengths = self.headers.get_all("Content-Length", [])
        if self.headers.get("Transfer-Encoding") or len(lengths) != 1:
            raise InvalidRequest(400, "One Content-Length is required")
        try:
            length = int(lengths[0])
        except ValueError:
            raise InvalidRequest(400, "Invalid Content-Length") from None
        if not 0 < length <= MAX_REQUEST_BYTES:
            raise InvalidRequest(413, "Request body exceeds allowed size")
        expired = threading.Event()

        def abort_read():
            expired.set()
            try:
                self.connection.shutdown(socket.SHUT_RD)
            except OSError:
                pass

        timer = threading.Timer(REQUEST_TIMEOUT_SECONDS, abort_read)
        timer.daemon = True
        timer.start()
        try:
            raw = self.rfile.read(length)
            if expired.is_set() or len(raw) != length:
                raise InvalidRequest(408, "Incomplete request body")
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise InvalidRequest(400, "JSON body must be an object")
            return payload
        except (ValueError, UnicodeError) as exc:
            if isinstance(exc, InvalidRequest):
                raise
            raise InvalidRequest(400, "Invalid JSON body") from None
        except OSError:
            raise InvalidRequest(408, "Request body timed out") from None
        finally:
            timer.cancel()
            timer.join(timeout=1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Workbench dashboard UI.")
    parser.add_argument("--host", default="127.0.0.1", choices=("127.0.0.1", "localhost"))
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    DashboardRequestHandler.config_path = args.config
    DashboardRequestHandler.data_dir = args.data_dir
    server = ThreadingHTTPServer((args.host, args.port), DashboardRequestHandler)
    print(f"Workbench dashboard: http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
