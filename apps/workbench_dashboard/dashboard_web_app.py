"""Workbench dashboard: local status, chat, plans, runs, and owner inbox."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import threading
import urllib.request
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar, cast
from urllib.parse import parse_qs, quote, unquote, urlparse

from agent_executor import build_executor
from ai_agent.run_tracking import request_run_cancel
from ai_agent.staged_edits import (
    ProjectRoots,
    StagedConflictError,
    StagedEditError,
    apply_staged,
    approve_staged,
    review_staged,
)
from ai_agent.supervisor_drain import Executor, RunDrain
from ai_orchestrator.evidence import merge_probe_eval
from ai_orchestrator.spend_ledger import (
    SpendLedger,
    allowance_from_file,
    policy_from_file,
)
from ai_provider.adapters.meta_asr import MetaAsrEngine
from ai_provider.chat_transcripts import SQLiteChatTranscriptStore
from ai_provider.secrets import read_secret_key
from ai_provider.stt import (
    STT_BODY_MAX_BYTES,
    MeteringHook,
    SttFailure,
    TranscribeEngine,
    parse_transcribe_form,
    transcribe_audio,
)
from ai_provider.translation import TranslationError, Translator
from chat_channel_tools import build_chat_channel_tools
from dashboard_chat import DashboardChat
from dashboard_config import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_DATA_DIR,
    DashboardConfig,
    load_config,
    save_supervision,
)
from dashboard_projects import create_project, get_project, list_projects
from dashboard_stores import DashboardStores, StoreError, effective_fanout_policy
from document_library import DocumentLibrary
from drain_scheduler import DrainScheduler
from meeting_notes import (
    MEETING_BODY_MAX_BYTES,
    assemble_transcript,
    parse_meeting_form,
    split_wav_clips,
    store_meeting,
)
from nl_tasks import ORDER_OPTIONS, SCHEDULE_ANSWER, propose_task, scheduled_run_record
from owner_mail import mail_configured
from p7_intake import approve_intake, list_intake
from providers_view import provider_status as providers_status
from providers_view import refresh_provider_status
from restrictions_view import restrictions_status
from window_status import load_window_status

ROOT = Path(__file__).parent
STATIC_ROOT = ROOT / "web"
REPO_ROOT = ROOT.parent.parent
MAX_REQUEST_BYTES = 512_000
REQUEST_TIMEOUT_SECONDS = 5.0
DEFAULT_PORT = 8766

# Served inline in the dashboard origin: active types would execute with
# full API access, so they are downgraded to inert text (audit 2026-11-06).
_ACTIVE_CONTENT_TYPES = frozenset({"text/html", "image/svg+xml", "application/xhtml+xml"})


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


RUN_FAILURE_STATUSES = frozenset({"failed"})
RUN_FAILURE_EVENT_KINDS = frozenset({"run_failed", "failure", "execution_failed"})
RUN_FAILURE_RECEIPT_STATUSES = frozenset({"failed", "error"})


def run_failure(run: dict) -> dict[str, Any] | None:
    """Derive a failure summary from existing run-record fields.

    Pure response-side helper: reads ``status``/``events``/``receipts`` only
    and never writes the store (existing record fields only, no new capture).
    ``status == "failed"`` is the record's own verdict and the only trigger;
    a failed receipt under a recovered (non-failed) status means the run
    recovered, so no banner. ``validation`` is free text, not a signal.
    Returns ``{"state", "reason", "at_utc"}`` or None when healthy.
    """
    if (run.get("status") or "") not in RUN_FAILURE_STATUSES:
        return None
    reason = None
    at_utc = None
    for event in run.get("events") or []:
        if not isinstance(event, dict):
            continue
        if (event.get("kind") or "") in RUN_FAILURE_EVENT_KINDS:
            payload = event.get("payload") or {}
            if isinstance(payload, dict):
                reason = payload.get("reason") or payload.get("detail") or payload.get("error")
            at_utc = event.get("at_utc")
    if reason is None:
        for receipt in run.get("receipts") or []:
            if not isinstance(receipt, dict):
                continue
            if (receipt.get("status") or "") in RUN_FAILURE_RECEIPT_STATUSES:
                reason = receipt.get("detail") or receipt.get("summary") or receipt.get("error")
                at_utc = receipt.get("at_utc")
                break
    return {"state": "failed", "reason": reason, "at_utc": at_utc}


def with_run_failure(run: dict) -> dict:
    """Copy one run record with its derived failure summary attached."""
    return {**run, "failure": run_failure(run)}


def with_run_detail(run: dict) -> dict:
    """Copy one run record with every detail-page enrichment applied."""
    return with_run_failure(with_fanout_policy(run))


def load_spend_ledger(data_dir: Path) -> SpendLedger:
    """Load grant files into one shared ledger (cef496c3 shared bucket).

    Fail-loud on malformed grant files (money); a missing grants dir means
    unconfigured (deny-by-default), never an error.
    """
    policy_path = data_dir / "spend" / "policy.json"
    rules = None
    if policy_path.is_file():
        try:
            rules = policy_from_file(policy_path)
        except ValueError as exc:
            raise ValueError(f"spend policy {policy_path.name}: {exc}") from exc
    ledger = SpendLedger(rules=rules)
    grants_dir = data_dir / "spend" / "grants"
    if grants_dir.is_dir():
        for path in sorted(grants_dir.glob("*.json")):
            try:
                ledger.add_allowance(allowance_from_file(path))
            except ValueError as exc:
                raise ValueError(f"spend grant {path.name}: {exc}") from exc
    return ledger


def spend_status(data_dir: Path, ledger: SpendLedger | None = None) -> dict[str, Any]:
    """Return the ledger dashboard view, shared when the server holds one.

    A passed ledger keeps STT spend and the spend view on the same buckets;
    None loads a fresh view (tests, unconfigured servers).
    """
    view = (ledger or load_spend_ledger(data_dir)).status()
    view["configured"] = bool(view["buckets"])
    return view


class LedgerSttMetering:
    """MeteringHook over one shared SpendLedger (cef496c3 shared bucket).

    Thread-safe for ThreadingHTTPServer: one lock around admit/settle.
    Deny-by-default: deferred/rejected admissions raise SttFailure (409),
    so STT never spends without a fitting grant.
    """

    def __init__(self, ledger: SpendLedger, *, provider: str = "meta") -> None:
        self._ledger = ledger
        self._provider = provider
        self._lock = threading.Lock()

    def reserve(self, *, operation: str, estimated_cents: int, **kwargs: object) -> str:
        with self._lock:
            admission = self._ledger.admit(
                task_id=f"stt-{uuid.uuid4().hex[:12]}",
                task_class=f"stt:{operation}",
                estimated_cents=estimated_cents,
                provider=self._provider,
            )
        if admission.decision != "admitted" or admission.reservation is None:
            raise SttFailure(
                "allowance",
                f"STT allowance {admission.decision}: {admission.reason}",
                409,
            )
        return admission.reservation.id

    def commit(self, receipt_id: str, actual_cents: int) -> None:
        with self._lock:
            self._ledger.settle(receipt_id, actual_cents=actual_cents)


def meta_stt_key() -> str | None:
    """Return the Meta STT key from ambient env or the repo .env file.

    Never logged: callers pass it straight to the engine constructor.
    None means unconfigured (Dictate keeps its honest 409).
    """
    key = os.environ.get("META_API_KEY", "").strip()
    if key:
        return key
    try:
        return read_secret_key(REPO_ROOT / ".env", "META_API_KEY", label="Meta STT credential")
    except ValueError:
        return None


FLEET_TASKS = (
    "WorkbenchDashboard",
    "MsiUdpWatchdog",
    "UDPPortExhaustionTrap",
    "CloneScan",
    "WakeSelfTest",
    "PrivateBackup",
    "WorkbenchWeeklyDigest",
)
FLEET_TERMINAL_RUN_STATUSES = frozenset({"completed", "failed", "cancelled", "canceled", "merged"})


def _fleet_task_script() -> str:
    names = ",".join(f"'{name}'" for name in FLEET_TASKS)
    return (
        f"$names = {names};"
        " $out = foreach ($n in $names) {"
        " $t = Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue;"
        " if (-not $t) { [pscustomobject]@{name=$n; present=$false}; continue };"
        " $i = try { $t | Get-ScheduledTaskInfo -ErrorAction Stop } catch { $null };"
        " $lr = $null; $nr = $null; $res = $null;"
        " if ($i -and $i.LastRunTime) { $lr = $i.LastRunTime.ToString('o') };"
        " if ($i -and $i.NextRunTime) { $nr = $i.NextRunTime.ToString('o') };"
        " if ($i -and $null -ne $i.LastTaskResult) { $res = $i.LastTaskResult };"
        " [pscustomobject]@{name=$n; present=$true; state=$t.State.ToString();"
        " last_run=$lr; next_run=$nr; last_result=$res} };"
        " $out | ConvertTo-Json -Compress"
    )


def fleet_tasks(runner=None) -> list[dict[str, Any]]:
    """Probe owned Windows scheduled tasks; fail-soft (a gap is data)."""

    def _missing(detail: str) -> list[dict[str, Any]]:
        return [{"name": name, "present": False, "detail": detail} for name in FLEET_TASKS]

    if sys.platform != "win32":
        return _missing("task probe is Windows-only")
    run = runner or subprocess.run
    try:
        completed = run(
            ["powershell", "-NoProfile", "-Command", _fleet_task_script()],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001 - health board never raises
        return _missing(f"probe failed: {type(exc).__name__}")
    try:
        payload = json.loads(completed.stdout or "null")
    except ValueError:
        return _missing("unparseable probe output")
    rows = payload if isinstance(payload, list) else [payload]
    by_name = {row.get("name"): row for row in rows if isinstance(row, dict)}
    probed = []
    for name in FLEET_TASKS:
        row = by_name.get(name)
        if not isinstance(row, dict) or not row.get("present"):
            probed.append({"name": name, "present": False, "detail": "not registered"})
            continue
        probed.append(
            {
                "name": name,
                "present": True,
                "state": str(row.get("state") or "unknown"),
                "last_run": row.get("last_run"),
                "next_run": row.get("next_run"),
                "last_result": row.get("last_result"),
            }
        )
    return probed


def fleet_ollama(urlopen=None) -> dict[str, Any]:
    """Probe the local Ollama server; fail-soft."""
    opener = urlopen or urllib.request.urlopen
    try:
        with opener("http://127.0.0.1:11434/api/tags", timeout=4) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - health board never raises
        return {"up": False, "detail": f"{type(exc).__name__}: {exc}"[:200]}
    models = payload.get("models", []) if isinstance(payload, dict) else []
    return {"up": True, "models": len(models)}


def fleet_sleep(repo_root: Path) -> dict[str, Any]:
    """Summarize the newest unattended sleep receipt; idle when none."""
    try:
        receipts = sorted(
            (repo_root / ".tmp").glob("unattended-*/sleep-*.json"),
            key=lambda path: path.stat().st_mtime,
        )
    except OSError:
        return {"active": False}
    if not receipts:
        return {"active": False}
    try:
        payload = json.loads(receipts[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"active": False, "detail": f"unreadable {receipts[-1].name}"}
    if not isinstance(payload, dict):
        return {"active": False, "detail": f"unreadable {receipts[-1].name}"}
    status = payload.get("status")
    return {
        "active": status == "sleep_scheduled",
        "status": status,
        "due_utc": payload.get("planned_sleep_utc"),
        "deadline_utc": payload.get("window_deadline_utc"),
        "pid": payload.get("process_id"),
        "receipt": receipts[-1].name,
    }


def fleet_runs(stores) -> list[dict[str, Any]]:
    """Non-terminal runs (live work plus anything awaiting merge/review)."""
    try:
        items, _total = stores.runs.list(limit=100)
    except Exception:  # noqa: BLE001 - health board never raises
        return []
    return [
        {
            "id": run.get("id"),
            "title": run.get("title") or run.get("id"),
            "status": run.get("status"),
            "updated": run.get("updated_at_utc"),
        }
        for run in items
        if isinstance(run, dict) and (run.get("status") or "") not in FLEET_TERMINAL_RUN_STATUSES
    ]


FLEET_SERVICES_DOC = "docs/fleet-services.md"


def fleet_explain(repo_root: Path) -> dict[str, str]:
    """Parse per-service explanations from the fleet services doc.

    Strict ``## <name>`` headers; the first paragraph under each header is
    the explanation. Fail-soft: unreadable or unparseable docs yield {}.
    """
    try:
        text = (repo_root / FLEET_SERVICES_DOC).read_text(encoding="utf-8")
    except OSError:
        return {}
    found: dict[str, str] = {}
    name: str | None = None
    paragraph: list[str] = []

    def _flush() -> None:
        if name and paragraph:
            found[name] = " ".join(paragraph)

    for line in text.splitlines():
        if line.startswith("## "):
            _flush()
            name = line[3:].strip()
            paragraph = []
        elif name is not None:
            stripped = line.strip()
            if not stripped:
                if paragraph:
                    _flush()
                    name = None
                    paragraph = []
            elif not line.startswith("#"):
                paragraph.append(stripped)
    _flush()
    return found


def fleet_status(repo_root: Path, stores) -> dict[str, Any]:
    """Aggregate live fleet probes; every probe is fail-soft."""
    explain = fleet_explain(repo_root)
    dashboard: dict[str, Any] = {"up": True}
    if explain.get("dashboard"):
        dashboard["explain"] = explain["dashboard"]
    ollama = fleet_ollama()
    if explain.get("ollama"):
        ollama["explain"] = explain["ollama"]
    sleep = fleet_sleep(repo_root)
    if explain.get("sleep guard"):
        sleep["explain"] = explain["sleep guard"]
    tasks = []
    for row in fleet_tasks():
        if explain.get(row["name"]):
            row["explain"] = explain[row["name"]]
        tasks.append(row)
    return {
        "dashboard": dashboard,
        "ollama": ollama,
        "tasks": tasks,
        "sleep": sleep,
        "runs": fleet_runs(stores),
    }


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
    # Speech/translation seams. None means unconfigured: transcription and
    # non-English ingestion fail closed (409) until the owner wires a keyed
    # engine, metering, and translator. Tests inject fakes here.
    stt_engine_factory: Callable[[], TranscribeEngine] | None = None
    stt_metering: MeteringHook | None = None
    spend_ledger: ClassVar[SpendLedger | None] = None
    chat_translator: Translator | None = None
    drain_executor_factory: ClassVar[Callable[[], Executor] | None] = None
    # Live scheduler handle (None when off). Set once in main(); read by _status.
    drain_scheduler: ClassVar[DrainScheduler | None] = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_ROOT), **kwargs)

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(REQUEST_TIMEOUT_SECONDS)

    def _trusted_request(self) -> bool:
        port = cast(tuple[str, int], self.server.server_address)[1]
        local_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        try:
            extra_hosts = set(load_config(self.config_path).trusted_hosts)
        except ValueError:
            extra_hosts = set()
        host = self.headers.get("Host")
        origin = self.headers.get("Origin")
        if len(self.headers.get_all("Host", [])) != 1 or host not in local_hosts | extra_hosts:
            self.send_error(HTTPStatus.FORBIDDEN, "Untrusted request origin")
            return False
        expected_origin = f"https://{host}" if host in extra_hosts else f"http://{host}"
        if origin is not None and origin != expected_origin:
            self.send_error(HTTPStatus.FORBIDDEN, "Untrusted request origin")
            return False
        return True

    def _stores(self) -> DashboardStores:
        return DashboardStores(self.data_dir)

    def _library(self) -> DocumentLibrary:
        return DocumentLibrary(self.repo_root)

    def _chat(self, config: DashboardConfig) -> DashboardChat:
        store = SQLiteChatTranscriptStore(self.data_dir / "chats.sqlite3")
        return DashboardChat(
            store,
            config,
            self.repo_root,
            chat_tools=build_chat_channel_tools(self._stores(), self._library()),
        )

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
            if path == "/api/spend":
                return self._send_json(
                    {"ok": True, "spend": spend_status(self.data_dir, self.spend_ledger)}
                )
            if path == "/api/restrictions":
                return self._send_json(self._restrictions_with_toggles())
            if path == "/api/providers":
                return self._send_json(providers_status(self.data_dir, self.repo_root))
            if path == "/api/fleet":
                return self._send_json(
                    {"ok": True, "fleet": fleet_status(self.repo_root, self._stores())}
                )
            if path == "/api/work-roots":
                return self._send_work_roots(config)
            if path == "/api/settings":
                return self._send_settings(config)
            if path == "/api/agent-status":
                return self._send_json({"ok": True, **load_window_status(self.repo_root)})
            if path == "/api/intake":
                return self._send_json({"ok": True, "files": list_intake(self.repo_root)})
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
                    self._stores().runs,
                    parsed.query,
                    enrich=with_fanout_policy,
                    filterable=("project_id", "plan_id"),
                )
            if path == "/api/documents":
                return self._send_json({"ok": True, "documents": self._library().list_documents()})
            if path.startswith("/api/documents/") and path.endswith("/file"):
                doc_id = unquote(path[len("/api/documents/") : -len("/file")])
                return self._send_document_file(doc_id)
            if path.startswith("/api/documents/"):
                doc_id = unquote(path[len("/api/documents/") :])
                return self._send_document(doc_id, parsed.query)
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
                    enrich=with_run_detail,
                )
            if path == "/api/inbox":
                return self._send_inbox(parsed.query)
            if path == "/api/ideas":
                return self._send_ideas(parsed.query)
            if path == "/api/backlog":
                return self._send_backlog(parsed.query)
            if path == "/api/projects":
                try:
                    projects = list_projects(self.data_dir)
                except StagedEditError as exc:
                    return self._send_json({"ok": False, "error": str(exc)}, status=500)
                return self._send_json({"ok": True, "projects": projects})
            if path.startswith("/api/projects/"):
                return self._send_project(path[len("/api/projects/") :])
            if path.startswith("/api/inbox/"):
                return self._send_item(self._stores().inbox, path[len("/api/inbox/") :])
            if path.startswith("/api/ideas/"):
                return self._send_item(self._stores().ideas, path[len("/api/ideas/") :])
            if path.startswith("/api/backlog/"):
                return self._send_item(self._stores().backlog, path[len("/api/backlog/") :])
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
        if path == "/api/meetings/transcribe":
            return self._transcribe_meeting()
        if path == "/api/stt/transcribe":
            return self._transcribe_audio()
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
            if path.startswith("/api/chat/sessions/") and path.endswith("/draft-plan"):
                session_id = path[len("/api/chat/sessions/") : -len("/draft-plan")]
                return self._draft_plan_from_chat(config, session_id, payload)
            if path == "/api/providers/refresh":
                return self._send_json(refresh_provider_status(self.data_dir, self.repo_root))
            if path == "/api/inbox":
                return self._create_inbox_task(payload)
            if path == "/api/ideas":
                return self._create_idea(payload)
            if path == "/api/backlog":
                return self._create_backlog_item(payload)
            if path == "/api/tasks/propose":
                return self._propose_task(payload)
            if path == "/api/projects":
                return self._create_project(payload)
            if path == "/api/settings":
                return self._save_settings(payload)
            if path == "/api/restrictions/toggles":
                return self._set_restriction_toggle(payload)
            if path.startswith("/api/inbox/") and path.endswith("/answer"):
                item_id = path[len("/api/inbox/") : -len("/answer")]
                return self._answer_inbox_task(item_id, payload)
            if path.startswith("/api/inbox/") and path.endswith("/close"):
                item_id = path[len("/api/inbox/") : -len("/close")]
                return self._close_inbox_task(item_id, payload)
            if path.startswith("/api/inbox/") and path.endswith("/reopen"):
                item_id = path[len("/api/inbox/") : -len("/reopen")]
                return self._reopen_inbox_task(item_id)
            if path == "/api/inbox/bridge-runs":
                return self._bridge_inbox_runs()
            if path.startswith("/api/plans/") and path.endswith("/approve"):
                plan_id = path[len("/api/plans/") : -len("/approve")]
                return self._decide_plan(plan_id, payload)
            if path.startswith("/api/ideas/") and path.endswith("/review"):
                item_id = path[len("/api/ideas/") : -len("/review")]
                return self._review_idea(item_id, payload)
            if path.startswith("/api/backlog/") and path.endswith("/review"):
                item_id = path[len("/api/backlog/") : -len("/review")]
                return self._review_backlog_item(item_id, payload)
            if path.startswith("/api/backlog/") and path.endswith("/promote"):
                item_id = path[len("/api/backlog/") : -len("/promote")]
                return self._promote_backlog_item(item_id, payload)
            if path.startswith("/api/runs/") and path.endswith("/report-request"):
                run_id = path[len("/api/runs/") : -len("/report-request")]
                return self._request_run_report(run_id)
            if path.startswith("/api/runs/") and path.endswith("/cancel"):
                run_id = path[len("/api/runs/") : -len("/cancel")]
                return self._cancel_run(run_id)
            if path == "/api/runs/drain":
                return self._drain_runs(config, payload)
            if path.startswith("/api/intake/") and path.endswith("/approve"):
                name = unquote(path[len("/api/intake/") : -len("/approve")])
                return self._approve_intake(name)
            if path.startswith("/api/runs/") and path.endswith("/approve-staged"):
                run_id = path[len("/api/runs/") : -len("/approve-staged")]
                return self._approve_run_staged(config, run_id, payload)
        except (StoreError, ValueError) as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        return self._send_json({"ok": False, "error": "Unknown endpoint"}, status=404)

    def _send_settings(self, config: DashboardConfig) -> None:
        self._send_json(
            {
                "ok": True,
                "supervision": config.supervision,
                "mail_configured": mail_configured(root=self.repo_root),
            }
        )

    def _save_settings(self, payload: dict) -> None:
        supervision = payload.get("supervision")
        if not isinstance(supervision, str):
            return self._send_json(
                {"ok": False, "error": "supervision must be a string"}, status=400
            )
        try:
            saved = save_supervision(self.config_path, supervision)
        except ValueError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        self._send_json(
            {
                "ok": True,
                "supervision": saved,
                "mail_configured": mail_configured(root=self.repo_root),
            }
        )

    def _status(self, config: DashboardConfig) -> dict[str, Any]:
        stores = self._stores()
        evidence = evidence_snapshot(self.repo_root)
        plans, plan_total = stores.plans.list(limit=1)
        runs, _run_total = stores.runs.list(limit=3)
        current_plan = plans[0] if plans else None
        scheduler = self.drain_scheduler
        return {
            "title": config.title,
            "provider": config.provider,
            "model": config.model,
            "open_inbox": stores.open_inbox_count(),
            "new_ideas": stores.new_idea_count(),
            "open_backlog": stores.open_backlog_count(),
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
            "drain_scheduler": {
                "started": bool(scheduler is not None and scheduler.started),
                "interval_seconds": config.drain_interval_seconds,
                "ticks": scheduler.ticks if scheduler is not None else 0,
                "errors": scheduler.errors if scheduler is not None else 0,
                "last_error": scheduler.last_error if scheduler is not None else None,
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
                        "metadata": message.metadata or {},
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
        language = payload.get("language", "en")
        if not isinstance(language, str):
            return self._send_json({"ok": False, "error": "Language must be a string"}, status=400)
        try:
            outcome = self._chat(config).send(
                session_id, text, language=language, translator=self.chat_translator
            )
        except TranslationError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=exc.status)
        except ValueError as exc:
            message = str(exc).lower()
            code = 404 if ("not found" in message or "unavailable" in message) else 400
            return self._send_json({"ok": False, "error": str(exc)}, status=code)
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

    def _draft_plan_from_chat(
        self, config: DashboardConfig, session_id: str, payload: dict
    ) -> None:
        title = payload.get("title")
        if title is not None and not isinstance(title, str):
            return self._send_json({"ok": False, "error": "Title must be a string"}, status=400)
        try:
            plan = self._chat(config).draft_plan(session_id, stores=self._stores(), title=title)
        except StoreError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        except ValueError as exc:
            if "not found" in str(exc).lower():
                return self._send_json({"ok": False, "error": str(exc)}, status=404)
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        self._send_json({"ok": True, "plan": plan})

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
        plan = payload.get("plan")
        if plan is not None and (not isinstance(plan, str) or not plan.strip()):
            return self._send_json({"ok": False, "error": "Plan must be a plan id"}, status=400)
        try:
            receipt = self._chat(config).request_run(
                session_id,
                text,
                stores=self._stores(),
                title=title or None,
                project=project_id,
                plan=plan,
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
        self,
        collection,
        query: str,
        *,
        enrich: Callable[[dict], dict] | None = None,
        filterable: tuple[str, ...] = (),
    ) -> None:
        params = parse_qs(query)
        try:
            limit = min(max(int(params.get("limit", ["20"])[0]), 1), 100)
            offset = max(int(params.get("offset", ["0"])[0]), 0)
        except ValueError:
            return self._send_json({"ok": False, "error": "Invalid limit or offset"}, status=400)
        items, total = collection.list(limit=limit, offset=offset)
        for field in filterable:
            wanted = params.get(field, [None])[0]
            if wanted is not None:
                # Post-list filter: collections here are tiny (tens of rows),
                # so page-then-filter stays honest via the filtered total.
                items = [item for item in items if item.get(field) == wanted]
        if any(params.get(field, [None])[0] is not None for field in filterable):
            total = len(items)
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
        for_agent = params.get("assignee", [None])[0]
        if for_agent is not None and for_agent not in {"owner", "agent"}:
            return self._send_json({"ok": False, "error": "Invalid assignee filter"}, status=400)
        items, _total = self._stores().inbox.list(limit=100)
        if wanted is not None:
            items = [item for item in items if item.get("status") == wanted]
        if for_agent is not None:
            items = [item for item in items if item.get("assignee") == for_agent]
        project_id = params.get("project_id", [None])[0]
        if project_id is not None:
            runs, _total = self._stores().runs.list(limit=100)
            project_runs = {run.get("id") for run in runs if run.get("project_id") == project_id}
            items = [item for item in items if self._inbox_item_in_project(item, project_runs)]
        self._send_json({"ok": True, "items": items, "total": len(items)})

    @staticmethod
    def _inbox_item_in_project(item: dict, project_runs: set) -> bool:
        """Match an inbox item to a project via its linked run, if any."""
        if item.get("task_id") in project_runs:
            return True
        refs = item.get("context_refs") or []
        if not isinstance(refs, list):
            return False
        return any(
            isinstance(ref, str) and ref.startswith("run:") and ref[len("run:") :] in project_runs
            for ref in refs
        )

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
        created_by = payload.get("created_by", "supervisor")
        assignee = payload.get("assignee", "owner")
        if not all(isinstance(value, str) for value in (created_by, assignee)):
            return self._send_json(
                {"ok": False, "error": "created_by and assignee must be strings"},
                status=400,
            )
        record = stores.create_inbox_task(
            title=title,
            body=body,
            task_type=task_type,
            created_by=created_by,
            assignee=assignee,
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
        scheduled_run = self._maybe_schedule_nl_run(record)
        self._send_json(
            {
                "ok": True,
                "id": record["id"],
                "status": record["status"],
                "scheduled_run": scheduled_run,
            }
        )

    def _maybe_schedule_nl_run(self, record: dict) -> str | None:
        """Queue the run for an approved NL proposal order (sched A).

        Returns the run id when a run was queued (or already existed),
        else None. Scheduling never fails the recorded answer: a
        malformed proposal is reported server-side and skipped.
        """
        metadata = record.get("metadata") or {}
        proposal = metadata.get("nl_proposal")
        if not isinstance(proposal, dict) or record.get("answer") != SCHEDULE_ANSWER:
            return None
        try:
            run = scheduled_run_record(proposal, record["id"])
        except ValueError as exc:
            print(f"Workbench dashboard: skip NL scheduling: {exc}")
            return None
        stores = self._stores()
        try:
            if stores.runs.get(run["id"]) is not None:
                return run["id"]
            stores.runs.put(run["id"], run)
        except StoreError as exc:
            print(f"Workbench dashboard: skip NL scheduling: {exc}")
            return None
        return run["id"]

    def _close_inbox_task(self, item_id: str, payload: dict) -> None:
        resolution = payload.get("resolution", "")
        if not isinstance(resolution, str):
            return self._send_json({"ok": False, "error": "Invalid resolution payload"}, status=400)
        kind = payload.get("resolution_kind", "final")
        if not isinstance(kind, str):
            return self._send_json({"ok": False, "error": "Invalid resolution kind"}, status=400)
        try:
            record = self._stores().close_inbox_task(
                item_id, resolution=resolution, resolution_kind=kind
            )
        except StoreError as exc:
            status = 404 if "not found" in str(exc).lower() else 400
            return self._send_json({"ok": False, "error": str(exc)}, status=status)
        self._send_json({"ok": True, "id": record["id"], "status": record["status"]})

    def _reopen_inbox_task(self, item_id: str) -> None:
        try:
            record = self._stores().reopen_inbox_task(item_id)
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

    def _send_backlog(self, query: str) -> None:
        from dashboard_stores import BACKLOG_SOURCES, BACKLOG_STATUSES

        params = parse_qs(query)
        wanted_status = params.get("status", [None])[0]
        wanted_source = params.get("source", [None])[0]
        if wanted_status is not None and wanted_status not in BACKLOG_STATUSES:
            return self._send_json({"ok": False, "error": "Invalid status filter"}, status=400)
        if wanted_source is not None and wanted_source not in BACKLOG_SOURCES:
            return self._send_json({"ok": False, "error": "Invalid source filter"}, status=400)
        items, _total = self._stores().backlog.list(limit=100)
        if wanted_status is not None:
            items = [item for item in items if item.get("status") == wanted_status]
        if wanted_source is not None:
            items = [item for item in items if item.get("source") == wanted_source]
        self._send_json({"ok": True, "items": items, "total": len(items)})

    def _create_backlog_item(self, payload: dict) -> None:
        title = payload.get("title", "")
        body = payload.get("body", "")
        source = payload.get("source", "owner")
        ref = payload.get("ref")
        if not all(isinstance(value, str) for value in (title, body, source)):
            return self._send_json(
                {"ok": False, "error": "title, body, and source must be strings"}, status=400
            )
        if ref is not None and not isinstance(ref, str):
            return self._send_json({"ok": False, "error": "ref must be a string"}, status=400)
        try:
            record = self._stores().create_backlog_item(
                title=title, body=body, source=source, ref=ref
            )
        except StoreError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        self._send_json({"ok": True, "id": record["id"]})

    def _review_backlog_item(self, item_id: str, payload: dict) -> None:
        status = payload.get("status", "")
        decision = payload.get("decision", "")
        if not isinstance(status, str) or not isinstance(decision, str):
            return self._send_json({"ok": False, "error": "Invalid review payload"}, status=400)
        try:
            record = self._stores().set_backlog_status(item_id, status=status, decision=decision)
        except StoreError as exc:
            code = 404 if "not found" in str(exc).lower() else 400
            return self._send_json({"ok": False, "error": str(exc)}, status=code)
        self._send_json({"ok": True, "id": record["id"], "status": record["status"]})

    def _promote_backlog_item(self, item_id: str, payload: dict) -> None:
        created_by = payload.get("created_by", "supervisor")
        if not isinstance(created_by, str):
            return self._send_json({"ok": False, "error": "Invalid promote payload"}, status=400)
        try:
            result = self._stores().promote_backlog_item(item_id, created_by=created_by)
        except StoreError as exc:
            code = 404 if "not found" in str(exc).lower() else 400
            return self._send_json({"ok": False, "error": str(exc)}, status=code)
        self._send_json({"ok": True, "id": result["item"]["id"], "inbox_id": result["inbox"]["id"]})

    def _review_idea(self, item_id: str, payload: dict) -> None:
        status = payload.get("status", "")
        decision = payload.get("decision", "")
        plan_id = payload.get("plan_id")
        if not isinstance(status, str) or not isinstance(decision, str):
            return self._send_json({"ok": False, "error": "Invalid review payload"}, status=400)
        if plan_id is not None and not isinstance(plan_id, str):
            return self._send_json({"ok": False, "error": "plan_id must be a string"}, status=400)
        try:
            record = self._stores().set_idea_status(
                item_id, status=status, decision=decision, plan_id=plan_id
            )
        except StoreError as exc:
            code = 404 if "not found" in str(exc).lower() else 400
            return self._send_json({"ok": False, "error": str(exc)}, status=code)
        self._send_json({"ok": True, "id": record["id"], "status": record["status"]})

    def _restrictions_with_toggles(self) -> None:
        from restrictions import describe_toggles, load_toggles

        status = restrictions_status(self._stores())
        status["toggles"] = describe_toggles(load_toggles(self.data_dir))
        self._send_json(status)

    def _set_restriction_toggle(self, payload: dict) -> None:
        from restrictions import describe_toggles, save_toggle

        name = payload.get("name")
        enabled = payload.get("enabled")
        if not isinstance(name, str) or not isinstance(enabled, bool):
            return self._send_json(
                {"ok": False, "error": "name must be a string and enabled a boolean"},
                status=400,
            )
        try:
            toggles = save_toggle(self.data_dir, name, enabled)
        except ValueError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        self._send_json({"ok": True, "toggles": describe_toggles(toggles)})

    def _bridge_inbox_runs(self) -> None:
        from inbox_bridge import bridge_agent_queue

        try:
            receipts = bridge_agent_queue(self._stores())
        except Exception as exc:  # noqa: BLE001 - report, never 500 blindly
            return self._send_json({"ok": False, "error": str(exc)}, status=500)
        self._send_json({"ok": True, "bridged": receipts})

    def _propose_task(self, payload: dict) -> None:
        """File free text as an approval-gated scheduled-task proposal."""
        text = payload.get("text", "")
        if not isinstance(text, str):
            return self._send_json({"ok": False, "error": "text must be a string"}, status=400)
        try:
            proposal = propose_task(text)
        except ValueError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        try:
            record = self._stores().create_inbox_task(
                title=f"Scheduled task proposal: {proposal['task_id']}",
                body=(
                    f"Model: {proposal['model']}; budget: {proposal['required_seconds']}s.\n"
                    f"Prompt: {proposal['prompt']}\n"
                    "Schedule it to queue the run; it executes on the next drain tick."
                ),
                task_type="order",
                options=ORDER_OPTIONS,
                metadata={"nl_proposal": proposal},
            )
        except StoreError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        self._send_json({"ok": True, "id": record["id"], "proposal": proposal})

    def _send_project(self, project_id: str) -> None:
        try:
            project = get_project(self.data_dir, project_id)
        except StagedEditError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=500)
        if project is None:
            return self._send_json({"ok": False, "error": "Not found"}, status=404)
        self._send_json({"ok": True, "project": project})

    def _create_project(self, payload: dict) -> None:
        name = payload.get("name")
        root = payload.get("root")
        description = payload.get("description", "")
        if not isinstance(name, str) or not isinstance(root, str):
            return self._send_json(
                {"ok": False, "error": "name and root must be strings"}, status=400
            )
        if not isinstance(description, str):
            return self._send_json(
                {"ok": False, "error": "description must be a string"}, status=400
            )
        try:
            project = create_project(self.data_dir, name=name, root=root, description=description)
        except StagedEditError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        self._send_json({"ok": True, "project": project})

    def _approve_intake(self, name: str) -> None:
        try:
            plan = approve_intake(self.repo_root, self.data_dir, name)
        except (ValueError, StoreError) as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        self._send_json({"ok": True, "plan": plan})

    def _drain_runs(self, config: DashboardConfig, payload: dict) -> None:
        """Execute approved queued runs; default one run per call."""
        max_runs = payload.get("max_runs", 1)
        if isinstance(max_runs, bool) or not isinstance(max_runs, int) or not 1 <= max_runs <= 100:
            return self._send_json(
                {"ok": False, "error": "max_runs must be an integer between 1 and 100"},
                status=400,
            )
        stores = self._stores()
        # Plain factory, not a method: tests inject staticmethod(fake_factory).
        factory = self.drain_executor_factory  # pyright: ignore[reportAttributeAccessIssue]
        try:
            drain = build_run_drain(
                config,
                self.data_dir,
                self.repo_root,
                stores,
                executor_factory=factory,
            )
        except StagedEditError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        outcomes = drain.drain(max_runs=max_runs)
        self._send_json({"ok": True, "outcomes": outcomes})

    def _cancel_run(self, run_id: str) -> None:
        try:
            run = self._stores().runs.get(run_id)
        except StoreError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if run is None:
            return self._send_json({"ok": False, "error": "Not found"}, status=404)
        try:
            request_run_cancel(run)
            self._stores().runs.put(run_id, run)
        except (StoreError, ValueError) as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        self._send_json({"ok": True, "run": with_fanout_policy(run)})

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

    def _send_document(self, doc_id: str, query: str) -> None:
        try:
            entry = self._library().get(doc_id)
        except KeyError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=404)
        except ValueError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        payload: dict = {
            "ok": True,
            "entry": {
                "id": entry.id,
                "root": entry.root,
                "relpath": entry.relpath,
                "title": entry.title,
                "tags": list(entry.tags),
                "project": entry.project,
                "size": entry.size,
                "modified_utc": entry.modified_utc,
                "sensitivity": entry.sensitivity,
                "renderable": entry.renderable,
            },
        }
        if parse_qs(query).get("content", ["0"])[0] == "1":
            if not entry.renderable:
                return self._send_json(
                    {"ok": False, "error": "Document is not renderable"}, status=400
                )
            try:
                body, truncated = self._library().read_text(doc_id)
            except (KeyError, ValueError) as exc:
                code = 404 if isinstance(exc, KeyError) else 400
                return self._send_json({"ok": False, "error": str(exc)}, status=code)
            payload["content"] = body
            payload["truncated"] = truncated
        self._send_json(payload)

    def _send_document_file(self, doc_id: str) -> None:
        try:
            data, content_type = self._library().read_bytes(doc_id)
        except KeyError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=404)
        except ValueError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if content_type in _ACTIVE_CONTENT_TYPES:
            content_type = "text/plain"
        name = doc_id.rsplit("/", 1)[-1]
        ascii_name = "".join(char if ord(char) < 128 else "_" for char in name)
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Disposition",
            f"inline; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}",
        )
        self.end_headers()
        self.wfile.write(data)

    def _transcribe_meeting(self) -> None:
        """Slice 1: chunked meeting transcription with consent + retention."""
        try:
            body = self._read_body_bytes(MEETING_BODY_MAX_BYTES)
        except InvalidRequest as exc:
            self.close_connection = True
            return self._send_json({"ok": False, "error": str(exc)}, status=exc.status)
        content_type = self.headers.get("Content-Type", "")
        try:
            audio, language, consent, retention = parse_meeting_form(content_type, body)
        except ValueError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=422)
        if not consent:
            return self._send_json(
                {"ok": False, "error": "client consent attestation is required"},
                status=409,
            )
        if self.stt_engine_factory is None or self.stt_metering is None:
            return self._send_json(
                {
                    "ok": False,
                    "error": "Transcription unavailable: no speech engine configured.",
                },
                status=409,
            )
        try:
            clips = split_wav_clips(audio)
        except ValueError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=422)
        engine = self.stt_engine_factory()
        segments: list[dict] = []
        try:
            for offset, clip in clips:
                out = transcribe_audio(
                    engine=engine,
                    metering=self.stt_metering,
                    audio_bytes=clip,
                    content_type="audio/wav",
                    language=language,
                )
                segments.append({"start_s": offset, "text": str(out.get("text", ""))})
        except SttFailure as exc:
            payload: dict = {
                "ok": False,
                "error": str(exc),
                "clips_done": len(segments),
            }
            if exc.retry_after:
                payload["retry_after"] = exc.retry_after
            return self._send_json(payload, status=exc.http_status)
        transcript = assemble_transcript(segments)
        try:
            meta = store_meeting(
                self.data_dir,
                transcript=transcript,
                segments=segments,
                consent=consent,
                retention_days=retention,
                engine_id=getattr(engine, "id", "unknown"),
                source_name="upload.wav",
            )
        except ValueError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=409)
        self._send_json(
            {
                "ok": True,
                "id": meta["id"],
                "clips": len(segments),
                "transcript": transcript,
                "purge_after_utc": meta["purge_after_utc"],
            }
        )

    def _transcribe_audio(self) -> None:
        try:
            body = self._read_body_bytes(STT_BODY_MAX_BYTES)
        except InvalidRequest as exc:
            self.close_connection = True
            return self._send_json({"ok": False, "error": str(exc)}, status=exc.status)
        content_type = self.headers.get("Content-Type", "")
        try:
            audio, audio_type, language = parse_transcribe_form(content_type, body)
        except SttFailure as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=exc.http_status)
        if self.stt_engine_factory is None or self.stt_metering is None:
            return self._send_json(
                {
                    "ok": False,
                    "error": "Transcription unavailable: no speech engine configured.",
                },
                status=409,
            )
        try:
            result = transcribe_audio(
                engine=self.stt_engine_factory(),
                metering=self.stt_metering,
                audio_bytes=audio,
                content_type=audio_type,
                language=language,
            )
        except SttFailure as exc:
            payload: dict = {"ok": False, "error": str(exc)}
            if exc.retry_after:
                payload["retry_after"] = exc.retry_after
            return self._send_json(payload, status=exc.http_status)
        except ValueError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=409)
        self._send_json({"ok": True, **result})

    def _send_json(self, payload: dict | list, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_body_bytes(self, max_bytes: int) -> bytes:
        lengths = self.headers.get_all("Content-Length", [])
        if self.headers.get("Transfer-Encoding") or len(lengths) != 1:
            raise InvalidRequest(400, "One Content-Length is required")
        try:
            length = int(lengths[0])
        except ValueError:
            raise InvalidRequest(400, "Invalid Content-Length") from None
        if not 0 < length <= max_bytes:
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
            return raw
        except OSError:
            raise InvalidRequest(408, "Request body timed out") from None
        finally:
            timer.cancel()
            timer.join(timeout=1)

    def _read_json_body(self) -> dict:
        media_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if media_type != "application/json":
            raise InvalidRequest(415, "Content-Type must be application/json")
        try:
            payload = json.loads(self._read_body_bytes(MAX_REQUEST_BYTES))
        except (ValueError, UnicodeError) as exc:
            if isinstance(exc, InvalidRequest):
                raise
            raise InvalidRequest(400, "Invalid JSON body") from None
        if not isinstance(payload, dict):
            raise InvalidRequest(400, "JSON body must be an object")
        return payload


DRAIN_SCHEDULER_MIN_INTERVAL_SECONDS = 60
SCHEDULER_DRAIN_MAX_RUNS = 1


def should_start_drain_scheduler(config: DashboardConfig) -> bool:
    """Return True when the config enables periodic run drains."""
    return config.drain_interval_seconds >= DRAIN_SCHEDULER_MIN_INTERVAL_SECONDS


def build_run_drain(
    config: DashboardConfig,
    data_dir: Path,
    repo_root: Path,
    stores: DashboardStores,
    executor_factory: Callable[[], Executor] | None = None,
) -> RunDrain:
    """Build the approved-runs drain shared by manual and scheduled drains."""
    roots = ProjectRoots(
        config.work_roots,
        protected_dirs=(
            data_dir,
            repo_root / ".venv",
            repo_root / ".git",
        ),
    )
    if executor_factory is not None:
        executor = executor_factory()
    else:
        from restrictions import load_toggles

        executor = build_executor(
            config,
            roots,
            repo_root,
            inbox_create=stores.create_inbox_task,
            restrictions=load_toggles(data_dir),
        )
    return RunDrain(
        runs_dir=data_dir / "runs",
        get_inbox=lambda inbox_id: stores.inbox.get(inbox_id),
        executor=executor,
    )


def maybe_start_drain_scheduler(config_path: Path, data_dir: Path) -> DrainScheduler | None:
    """Start periodic drains when configured; never raises."""
    try:
        config = load_config(config_path)
    except ValueError as exc:
        print(f"Workbench dashboard: drain scheduler off (config: {exc})")
        return None
    if not should_start_drain_scheduler(config):
        return None
    stores = DashboardStores(data_dir)

    def tick() -> None:
        from inbox_bridge import bridge_agent_queue

        try:
            bridged = bridge_agent_queue(stores)
        except Exception as exc:  # noqa: BLE001 - tick failures are never fatal
            print(f"Workbench dashboard: inbox bridge failed: {exc}")
            bridged = []
        if bridged:
            print(f"Workbench dashboard: bridged {len(bridged)} inbox tasks to runs")
        drain = build_run_drain(config, data_dir, REPO_ROOT, stores)
        outcomes = drain.drain(max_runs=SCHEDULER_DRAIN_MAX_RUNS)
        print(f"Workbench dashboard: scheduled drain: {outcomes}")

    scheduler = DrainScheduler(tick, config.drain_interval_seconds)
    scheduler.start()
    print(f"Workbench dashboard: drain scheduler every {config.drain_interval_seconds}s")
    return scheduler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Workbench dashboard UI.")
    parser.add_argument("--host", default="127.0.0.1", choices=("127.0.0.1", "localhost"))
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    from ai_provider.secrets import load_dotenv

    loaded = load_dotenv(REPO_ROOT)
    if loaded:
        print(f"Workbench dashboard: secret store loaded ({len(loaded)} keys by name)")
    DashboardRequestHandler.config_path = args.config
    DashboardRequestHandler.data_dir = args.data_dir
    try:
        DashboardRequestHandler.drain_scheduler = maybe_start_drain_scheduler(
            args.config, args.data_dir
        )
    except Exception as exc:  # noqa: BLE001 - scheduler must never block serving
        print(f"Workbench dashboard: drain scheduler failed to start: {exc}")
    try:
        DashboardRequestHandler.spend_ledger = load_spend_ledger(args.data_dir)
    except ValueError as exc:
        print(f"Workbench dashboard: spend grants invalid, STT metering off: {exc}")
    stt_key = meta_stt_key()
    if stt_key is not None and DashboardRequestHandler.spend_ledger is not None:

        def _meta_engine() -> MetaAsrEngine:
            return MetaAsrEngine(stt_key)

        # staticmethod keeps instance access unbound (same seam as the tests).
        DashboardRequestHandler.stt_engine_factory = staticmethod(_meta_engine)  # pyright: ignore[reportAttributeAccessIssue]
        DashboardRequestHandler.stt_metering = LedgerSttMetering(
            DashboardRequestHandler.spend_ledger
        )
        print("Workbench dashboard: Meta STT engine wired (shared spend bucket)")
    else:
        print("Workbench dashboard: STT engine unwired (no key or no ledger)")
    server = ThreadingHTTPServer((args.host, args.port), DashboardRequestHandler)
    print(f"Workbench dashboard: http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
