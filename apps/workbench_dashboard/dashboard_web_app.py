"""Workbench dashboard: local status, chat, plans, runs, and owner inbox."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar, cast
from urllib.parse import parse_qs, quote, unquote, urlparse

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
    policy_rules_from_doc,
)
from ai_provider.adapters.meta_asr import MetaAsrEngine
from ai_provider.chat_transcripts import SQLiteChatTranscriptStore
from ai_provider.errors import ProviderError
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
    save_modules,
    save_supervision,
)
from dashboard_modules import CORE_VIEWS, MODULES, module_for_path
from dashboard_projects import (
    book_check_task,
    create_project,
    get_project,
    list_goals,
    list_plan_attention,
    list_projects,
    set_project_manuscript,
)
from dashboard_stores import DashboardStores, StoreError, effective_fanout_policy
from document_library import DocumentLibrary
from drain_scheduler import DrainScheduler
from nl_tasks import ORDER_OPTIONS, SCHEDULE_ANSWER, propose_task, scheduled_run_record
from owner_mail import mail_configured
from owner_sleep import (
    cancel_owner_sleep,
    last_outcome,
    read_lastwake_text,
    schedule_owner_sleep,
    timer_state,
)
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
SUBMIT_AUTOCHECK_BUDGET_SECONDS = 300.0

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
    ledger = SpendLedger(data_dir / "spend_ledger.sqlite3", rules=rules)
    grants_dir = data_dir / "spend" / "grants"
    if grants_dir.is_dir():
        from ai_orchestrator.spend_ledger import allowance_fingerprint

        for path in sorted(grants_dir.glob("*.json")):
            try:
                grant = allowance_from_file(path)
            except ValueError as exc:
                raise ValueError(f"spend grant {path.name}: {exc}") from exc
            try:
                existing = ledger.get_allowance(grant.id)
            except KeyError:
                ledger.add_allowance(grant)
                continue
            if allowance_fingerprint(existing) != allowance_fingerprint(grant):
                raise ValueError(
                    f"spend grant {path.name}: file changed since bootstrap; "
                    "delete spend_ledger.sqlite3 to re-bootstrap deliberately"
                )
    return ledger


def spend_status(data_dir: Path, ledger: SpendLedger | None = None) -> dict[str, Any]:
    """Return the ledger dashboard view, shared when the server holds one.

    A passed ledger keeps STT spend and the spend view on the same buckets;
    None loads a fresh view (tests, unconfigured servers).
    """
    from providers_view import route_ids

    view = (ledger or load_spend_ledger(data_dir)).status()
    view["configured"] = bool(view["buckets"])
    view["policy_scopes"] = ["global", *route_ids()]
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
    "WorkbenchDashboardSupervisor",
    "MsiUdpWatchdog",
    "UDPPortExhaustionTrap",
    "CloneScan",
    "WakeSelfTest",
    "PrivateBackup",
    "WorkbenchWeeklyDigest",
    "WorkbenchAllowanceCheck",
    "OpeningsWeb",
    "OpeningsCollect",
)
FLEET_TERMINAL_RUN_STATUSES = frozenset({"completed", "failed", "cancelled", "canceled", "merged"})
MAINTENANCE_FILENAME = "maintenance.json"


SERVE_VERSION_FILENAME = "serve-version.json"


def _with_tier(info: dict[str, Any], config_path: Path | None) -> dict[str, Any]:
    if config_path is not None:
        try:
            config = load_config(config_path)
        except (ValueError, OSError):
            pass
        else:
            info["tier"] = config.product_tier
            info["serve_branch"] = config.serve_branch
    try:
        import ai_agent

        info["packages_root"] = str(Path(ai_agent.__file__).resolve().parent.parent)
    except (ImportError, AttributeError, TypeError, OSError):
        pass
    return info


def capture_server_version(
    repo_root: Path, *, config_path: Path | None = None, data_dir: Path | None = None
) -> dict[str, Any]:
    """Best-effort served-commit snapshot for /api/version (never raises).

    Prefers the supervisor-written version file; falls back to git on the
    code checkout (detached serve worktrees report their commit with an
    unknown branch, corrected by the file when present).
    """
    info: dict[str, Any] = {
        "branch": "unknown",
        "commit": "unknown",
        "commit_utc": None,
        "started_utc": datetime.now(UTC).isoformat(),
        "tier": "tooling",
        "serve_branch": "develop",
    }
    if data_dir is not None:
        try:
            filed = json.loads(
                (Path(data_dir) / SERVE_VERSION_FILENAME).read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            filed = None
        if isinstance(filed, dict):
            if isinstance(filed.get("branch"), str) and filed["branch"]:
                info["branch"] = filed["branch"]
            if isinstance(filed.get("commit"), str) and filed["commit"]:
                info["commit"] = filed["commit"]
            if isinstance(filed.get("commit_utc"), str) and filed["commit_utc"]:
                info["commit_utc"] = filed["commit_utc"]
            return _with_tier(info, config_path)
    try:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        stamped = subprocess.run(
            ["git", "show", "-s", "--format=%cI", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        pass
    else:
        if branch.returncode == 0 and branch.stdout.strip():
            info["branch"] = branch.stdout.strip()
        if commit.returncode == 0 and commit.stdout.strip():
            info["commit"] = commit.stdout.strip()
        if stamped.returncode == 0 and stamped.stdout.strip():
            info["commit_utc"] = stamped.stdout.strip()
    return _with_tier(info, config_path)


def read_maintenance(data_dir: Path) -> dict[str, Any]:
    """Maintenance banner state written by the supervisor (fail-soft)."""
    try:
        payload = json.loads((Path(data_dir) / MAINTENANCE_FILENAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"active": False}
    if not isinstance(payload, dict):
        return {"active": False}
    return {
        "active": bool(payload.get("active")),
        "message": str(payload.get("message") or ""),
        "since_utc": payload.get("since_utc"),
    }


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


_FLEET_TASKS_TTL_SECONDS = 60.0
_fleet_tasks_cache: tuple[float, list[dict[str, Any]]] | None = None
_fleet_tasks_lock = threading.Lock()


def _reset_fleet_tasks_cache() -> None:
    """Drop the cached task probe (tests only)."""
    global _fleet_tasks_cache
    with _fleet_tasks_lock:
        _fleet_tasks_cache = None


def fleet_tasks(runner=None) -> list[dict[str, Any]]:
    """Probe owned Windows scheduled tasks; fail-soft (a gap is data).

    Live probes are cached for 60s: the COM query costs ~4s and task
    states move on minute scale. Callers mutate rows, so the cache
    hands out copies. An explicit runner always probes fresh.
    """
    global _fleet_tasks_cache
    if runner is None:
        with _fleet_tasks_lock:
            cached = _fleet_tasks_cache
        if cached is not None:
            probed_at, rows = cached
            if time.monotonic() - probed_at < _FLEET_TASKS_TTL_SECONDS:
                return [dict(row) for row in rows]
    rows = _probe_fleet_tasks(runner)
    if runner is None:
        with _fleet_tasks_lock:
            _fleet_tasks_cache = (time.monotonic(), [dict(row) for row in rows])
    return rows


def _probe_fleet_tasks(runner=None) -> list[dict[str, Any]]:
    """Run one task probe (see fleet_tasks for the cached entry point)."""

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


SUPERVISION_STUCK_MINUTES = 30
SUPERVISION_PARKED_MINUTES = 60
SUPERVISION_BROKEN_HOURS = 24
SUPERVISION_TERMINAL = frozenset({"completed", "cancelled", "canceled", "merged"})


def _run_age_minutes(run: dict[str, Any], now: datetime) -> float | None:
    raw = run.get("updated_at_utc")
    if not isinstance(raw, str):
        return None
    try:
        updated = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=UTC)
    return (now - updated).total_seconds() / 60


def _run_failure_class(run: dict[str, Any]) -> str:
    receipts = run.get("receipts")
    if isinstance(receipts, list):
        for receipt in reversed(receipts):
            if isinstance(receipt, dict) and receipt.get("failure_class"):
                return str(receipt["failure_class"])
    return "unknown"


def fleet_agents(stores, *, now: datetime | None = None) -> dict[str, Any]:
    """Supervision verdicts over runs: stuck, broken, dead-end, parked, ok.

    Failed runs stay visible while fresh; running runs older than
    SUPERVISION_STUCK_MINUTES without an update are stuck; old queued
    runs are parked. A fresh failed run with no triage task is a
    dead-end: terminal without follow-up. Fail-soft like every other
    Fleet probe.
    """
    try:
        items, _total = stores.runs.list(limit=100)
    except Exception:  # noqa: BLE001 - health board never raises
        return {"runs": [], "stuck": 0, "broken": 0, "dead_end": 0, "attention": False}
    moment = now or datetime.now(UTC)
    verdicts: list[dict[str, Any]] = []
    for run in items:
        if not isinstance(run, dict):
            continue
        status = run.get("status") or ""
        if status in SUPERVISION_TERMINAL:
            continue
        age = _run_age_minutes(run, moment)
        verdict = "ok"
        reason = ""
        if status == "failed":
            if age is None or age <= SUPERVISION_BROKEN_HOURS * 60:
                if _run_has_triage(stores, str(run.get("id") or "")):
                    verdict = "broken"
                    reason = _run_failure_class(run)
                else:
                    verdict = "dead-end"
                    failure = _run_failure_class(run)
                    reason = f"{failure}; no triage task" if failure else "no triage task"
            else:
                continue
        elif status == "running" and age is not None and age > SUPERVISION_STUCK_MINUTES:
            verdict = "stuck"
            reason = f"no update for {age:.0f} min"
        elif status == "queued" and age is not None and age > SUPERVISION_PARKED_MINUTES:
            verdict = "parked"
            reason = f"queued for {age:.0f} min"
        verdicts.append(
            {
                "id": run.get("id"),
                "title": run.get("title") or run.get("id"),
                "status": status,
                "verdict": verdict,
                "reason": reason,
                "updated": run.get("updated_at_utc"),
            }
        )
    stuck = sum(1 for item in verdicts if item["verdict"] == "stuck")
    broken = sum(1 for item in verdicts if item["verdict"] == "broken")
    dead_end = sum(1 for item in verdicts if item["verdict"] == "dead-end")
    return {
        "runs": verdicts,
        "stuck": stuck,
        "broken": broken,
        "dead_end": dead_end,
        "attention": bool(stuck or broken or dead_end),
    }


def _run_has_triage(stores, run_id: str) -> bool:
    """True when an open triage task tracks this run (frozen T1 key)."""
    if not run_id:
        return False
    try:
        items, _total = stores.inbox.list(limit=1000)
    except Exception:  # noqa: BLE001 - probe stays fail-soft
        return True  # unknown: keep the established broken verdict
    return any(
        isinstance(item, dict)
        and item.get("status") == "open"
        and str((item.get("metadata") or {}).get("triage_for", "")) == run_id
        for item in items
    )


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


def _resolve_analysis_client(config, repo_root: Path):
    """Forced auto-route client for meeting analysis (owner inbox decision B).

    Always routes through the orchestrator with EXTERNAL_ALLOWED privacy and
    the allowances tier; never silently falls back to local. Raises
    ValueError with the reason when no allowance route is available.
    """
    from ai_orchestrator import CostPolicyTier, load_model_catalog, prepare_execution
    from ai_orchestrator.models import PrivacyClass as OrchestratorPrivacy
    from ai_orchestrator.models import TaskProfile, TaskType
    from ai_orchestrator.route_outcomes import OUTCOMES_FILENAME, load_quality_adjustments
    from ai_provider.config import BackendConfig, ProviderKind
    from ai_provider.factory import create_chat_client
    from ai_provider.user_config import active_cost_exemptions, load_user_config

    try:
        catalog_path = (
            Path(config.catalog_path)
            if config.catalog_path
            else repo_root / "packages/ai_orchestrator/examples/model_catalog.toml"
        )
        catalog = load_model_catalog(catalog_path)
        user_config = load_user_config(repo_root / "user-config.toml")
        profile = TaskProfile(
            task_type=TaskType.EXTRACTION,
            privacy_class=OrchestratorPrivacy.EXTERNAL_ALLOWED,
            cost_policy_tier=CostPolicyTier.ALLOWANCES_ALLOWED,
        )
        result = prepare_execution(
            "meeting action-item analysis",
            profile,
            catalog,
            review_prompt=False,
            cost_exemptions=active_cost_exemptions(user_config),
            quality_adjustments=load_quality_adjustments(
                repo_root / "artifacts" / OUTCOMES_FILENAME
            ),
        )
        if result.execution_plan is None:
            raise ValueError(result.failure_reason or "no execution plan")
        target = result.execution_plan.target
        client = create_chat_client(
            BackendConfig(provider=ProviderKind(target.provider), model=target.model)
        )
    except (ValueError, ProviderError) as exc:
        raise ValueError(f"allowance route unavailable: {exc}") from exc
    return client, target.model, target.route_id


def _tcp_up(host: str, port: int) -> bool:
    """True when a TCP connect succeeds (fail-soft, ~1s budget)."""
    import socket

    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def _dir_version(path: Path) -> str:
    """Short HEAD of a checkout, or 'unknown' (fail-soft)."""
    if not (path / ".git").exists():
        return "unknown"
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


BUNDLED_SERVICES = {
    "relay mailbox/mediator": "apps/workbench_dashboard/relay_mailbox.py",
    "owner digest": "apps/workbench_dashboard/owner_digest.py",
    "verify-report/last_outcome": "apps/workbench_dashboard/owner_sleep.py",
    "eval ladder/grades": "scripts/l3_ladder.py",
}


def bundled_services(repo_root: Path, version: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Describe landed components without starting or probing their workflows."""
    explanations = fleet_explain(repo_root)
    served = version or {}
    return [
        {
            "name": name,
            "kind": "bundled",
            "version": f"{served.get('branch', '?')}@{served.get('commit', '?')}",
            "commit_utc": served.get("commit_utc"),
            "explain": explanations.get(name, ""),
        }
        for name, source in BUNDLED_SERVICES.items()
        if (repo_root / source).is_file()
    ]


def fleet_services(repo_root: Path, version: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Kept-service versions; every probe is fail-soft."""
    services: list[dict[str, Any]] = []
    if isinstance(version, dict):
        services.append(
            {
                "name": "dashboard",
                "up": True,
                "version": f"{version.get('branch', '?')}@{version.get('commit', '?')}",
                "commit_utc": version.get("commit_utc"),
                "started_utc": version.get("started_utc"),
            }
        )
    openings = repo_root / "apps" / "job_search" / "openings-svc"
    if openings.is_dir():
        services.append(
            {
                "name": "openings",
                "up": _tcp_up("127.0.0.1", 8501),
                "version": _dir_version(openings / "upstream"),
                "port": 8501,
            }
        )
    return services + bundled_services(repo_root, version)


def fleet_status(repo_root: Path, stores, version: dict[str, Any] | None = None) -> dict[str, Any]:
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
    agents: dict[str, Any] = fleet_agents(stores)
    if explain.get("agents"):
        agents["explain"] = explain["agents"]
    return {
        "dashboard": dashboard,
        "ollama": ollama,
        "tasks": tasks,
        "sleep": sleep,
        "runs": fleet_runs(stores),
        "agents": agents,
        "services": fleet_services(repo_root, version),
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
    # Owner-sleep launcher seam. None means the real hidden helper spawn;
    # tests inject a fake that writes a receipt instead.
    sleep_launcher = None
    # Meeting-analysis client seam. None means production auto-route
    # resolution per request; tests inject a fake returning
    # (client, model_id, route_id).
    analysis_client_factory: Callable[[], tuple[Any, str, str]] | None = None
    spend_ledger: ClassVar[SpendLedger | None] = None
    chat_translator: Translator | None = None
    drain_executor_factory: ClassVar[Callable[[], Executor] | None] = None
    # Live scheduler handle (None when off). Set once in main(); read by _status.
    drain_scheduler: ClassVar[DrainScheduler | None] = None
    # Served-commit snapshot. Set once in main(); tests inject directly.
    # Named served_* to avoid BaseHTTPRequestHandler.server_version.
    served_version: ClassVar[dict[str, Any] | None] = None

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
        if self._module_disabled(path, config):
            return
        try:
            if path == "/api/overview":
                if "overview" not in config.activated_modules:
                    return self._send_json(
                        {"ok": False, "error": "Overview is disabled"}, status=409
                    )
                return self._send_overview()
            if path == "/api/modules":
                return self._send_modules(config)
            if path == "/api/status":
                return self._send_json({"ok": True, **self._status(config)})
            if path == "/api/evidence":
                return self._send_json({"ok": True, **evidence_snapshot(self.repo_root)})
            if path == "/api/orchestrator/routes":
                return self._send_orchestrator_routes(parsed.query)
            if path == "/api/spend":
                return self._send_json(
                    {"ok": True, "spend": spend_status(self.data_dir, self.spend_ledger)}
                )
            if path == "/api/restrictions":
                return self._restrictions_with_toggles(config)
            if path == "/api/knowme":
                return self._send_knowme(parsed.query)
            if path == "/api/providers":
                return self._send_json(
                    providers_status(
                        self.data_dir, self.repo_root, catalog_path=config.catalog_path
                    )
                )
            if path == "/api/fleet":
                return self._send_json(
                    {
                        "ok": True,
                        "fleet": fleet_status(
                            self.repo_root,
                            self._stores(),
                            version=type(self).served_version,
                        ),
                    }
                )
            if path == "/api/work-roots":
                return self._send_work_roots(config)
            if path == "/api/settings":
                return self._send_settings(config)
            if path == "/api/agent-status":
                return self._send_json({"ok": True, **load_window_status(self.repo_root)})
            if path == "/api/intake":
                from p7_intake import list_intake

                return self._send_json({"ok": True, "files": list_intake(self.repo_root)})
            if path == "/api/chat/sessions":
                return self._send_chat_sessions(config)
            if path == "/api/chat/agent-config":
                return self._send_json(
                    {
                        "ok": True,
                        "enabled": config.chat_agent_enabled,
                        "approval": config.chat_agent_approval,
                    }
                )
            if path.startswith("/api/chat/sessions/") and path.endswith("/progress"):
                session_id = path[len("/api/chat/sessions/") : -len("/progress")]
                message_id = parse_qs(parsed.query).get("message_id", [""])[0]
                return self._send_chat_progress(config, session_id, message_id)
            if path.startswith("/api/chat/sessions/") and path.endswith("/messages"):
                session_id = path[len("/api/chat/sessions/") : -len("/messages")]
                return self._send_chat_messages(config, session_id)
            if path.startswith("/api/chat/sessions/") and path.endswith("/staged"):
                session_id = path[len("/api/chat/sessions/") : -len("/staged")]
                return self._send_chat_staged(session_id)
            if path == "/api/plans":
                return self._send_collection(
                    self._stores().plans,
                    parsed.query,
                    filterable=("project_id", "kind", "parent_plan_id"),
                )
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
                return self._send_documents()
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
            if path == "/api/invoices":
                return self._list_invoices()
            if path == "/api/workflows":
                return self._send_workflows(parsed.query)
            if path == "/api/workflows/options":
                return self._send_workflow_options()
            if path == "/api/projects":
                try:
                    projects = list_projects(self.data_dir)
                except StagedEditError as exc:
                    return self._send_json({"ok": False, "error": str(exc)}, status=500)
                return self._send_json(
                    {
                        "ok": True,
                        "projects": projects,
                        "goals": list_goals(self.repo_root),
                        "attention": list_plan_attention(self.repo_root),
                        "services": bundled_services(self.repo_root, type(self).served_version),
                    }
                )
            if path.startswith("/api/projects/"):
                return self._send_project(path[len("/api/projects/") :])
            if path.startswith("/api/inbox/"):
                return self._send_item(self._stores().inbox, path[len("/api/inbox/") :])
            if path.startswith("/api/resolve/"):
                token = unquote(path[len("/api/resolve/") :])
                return self._send_json({"ok": True, "matches": self._stores().resolve_id(token)})
            if path.startswith("/api/ideas/"):
                return self._send_item(self._stores().ideas, path[len("/api/ideas/") :])
            if path.startswith("/api/backlog/"):
                return self._send_item(self._stores().backlog, path[len("/api/backlog/") :])
            if path.startswith("/api/invoices/"):
                return self._get_invoice(path[len("/api/invoices/") :])
            if path.startswith("/api/workflows/"):
                return self._send_item(self._stores().workflows, path[len("/api/workflows/") :])
            if path == "/api/e2e/tasks":
                return self._send_e2e_tasks(parsed.query)
            if path == "/api/e2e/reports":
                return self._send_e2e_reports()
            if path == "/api/e2e/by-view":
                return self._send_e2e_by_view(parsed.query)
            if path.startswith("/api/e2e/tasks/"):
                task_id = path[len("/api/e2e/tasks/") :]
                if "/" in task_id:
                    return self._send_item(self._stores().e2e_tasks, task_id)
                return self._send_e2e_task(task_id)
            if path.startswith("/api/e2e/reports/"):
                return self._send_item(self._stores().e2e_reports, path[len("/api/e2e/reports/") :])
            if path == "/api/sleep":
                state = timer_state(self.repo_root)
                state["last_outcome"] = last_outcome(
                    self.repo_root, lastwake_text=read_lastwake_text()
                )
                return self._send_json({"ok": True, **state})
            if path == "/api/version":
                version = dict(type(self).served_version or {})
                version.setdefault("branch", "unknown")
                version.setdefault("commit", "unknown")
                return self._send_json({"ok": True, **version})
            if path == "/api/maintenance":
                return self._send_json({"ok": True, **read_maintenance(self.data_dir)})
            if path == "/api/meetings":
                from meeting_notes import list_meetings, purge_expired_meetings

                purge_expired_meetings(self.data_dir)
                return self._send_json({"ok": True, "items": list_meetings(self.data_dir)})
            if path.startswith("/api/meetings/"):
                return self._send_meeting(path[len("/api/meetings/") :])
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
            activation_config = load_config(self.config_path)
        except ValueError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=500)
        if self._module_disabled(path, activation_config):
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
            if path == "/api/modules":
                try:
                    save_modules(
                        self.config_path,
                        payload.get("activated_modules"),
                        payload.get("landing_page"),
                    )
                except ValueError as exc:
                    return self._send_json({"ok": False, "error": str(exc)}, status=400)
                return self._send_modules(load_config(self.config_path))
            if path == "/api/sleep":
                return self._schedule_sleep(payload)
            if path == "/api/jobs/review":
                return self._review_job_vacancy(payload)
            if path == "/api/sleep/cancel":
                return self._send_json({"ok": True, **cancel_owner_sleep(self.repo_root)})
            if path.startswith("/api/meetings/") and path.endswith("/analyze"):
                meeting_id = path[len("/api/meetings/") : -len("/analyze")]
                return self._analyze_meeting_endpoint(config, meeting_id, payload)
            if path == "/api/chat/sessions":
                return self._create_chat_session(config, payload)
            if path == "/api/chat/agent-config":
                return self._save_chat_agent_config(payload)
            if path.startswith("/api/chat/sessions/") and path.endswith("/messages"):
                session_id = path[len("/api/chat/sessions/") : -len("/messages")]
                return self._post_chat_message(config, session_id, payload)
            if path.startswith("/api/chat/sessions/") and path.endswith("/rename"):
                session_id = path[len("/api/chat/sessions/") : -len("/rename")]
                return self._rename_chat_session(config, session_id, payload)
            if path.startswith("/api/chat/sessions/") and path.endswith("/mode"):
                session_id = path[len("/api/chat/sessions/") : -len("/mode")]
                return self._set_chat_mode(config, session_id, payload)
            if path.startswith("/api/chat/sessions/") and path.endswith("/apply"):
                session_id = path[len("/api/chat/sessions/") : -len("/apply")]
                return self._apply_chat_staged(session_id, payload)
            if path.startswith("/api/chat/sessions/") and path.endswith("/heartbeat"):
                session_id = path[len("/api/chat/sessions/") : -len("/heartbeat")]
                return self._heartbeat_chat_session(session_id)
            if path.startswith("/api/chat/sessions/") and path.endswith("/approve"):
                session_id = path[len("/api/chat/sessions/") : -len("/approve")]
                return self._approve_chat_turn(config, session_id)
            if path.startswith("/api/chat/sessions/") and path.endswith("/reject"):
                session_id = path[len("/api/chat/sessions/") : -len("/reject")]
                return self._reject_chat_turn(session_id)
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
                return self._send_json(
                    refresh_provider_status(
                        self.data_dir, self.repo_root, catalog_path=config.catalog_path
                    )
                )
            if path == "/api/spend/policy":
                return self._save_spend_policy(payload)
            if path == "/api/spend/adjust":
                return self._adjust_spend_balance(payload)
            if path == "/api/inbox":
                return self._create_inbox_task(payload)
            if path == "/api/e2e/tasks":
                return self._create_e2e_task(payload)
            if path.startswith("/api/e2e/tasks/") and path.endswith("/submit"):
                task_id = path[len("/api/e2e/tasks/") : -len("/submit")]
                return self._submit_e2e_task(task_id, payload)
            if path.startswith("/api/e2e/tasks/") and path.endswith("/notes"):
                task_id = path[len("/api/e2e/tasks/") : -len("/notes")]
                return self._save_e2e_notes(task_id, payload)
            if path.startswith("/api/e2e/tasks/") and path.endswith("/finalize"):
                task_id = path[len("/api/e2e/tasks/") : -len("/finalize")]
                return self._finalize_e2e_task(task_id, payload)
            if path.startswith("/api/e2e/tasks/") and path.endswith("/agent-check"):
                task_id = path[len("/api/e2e/tasks/") : -len("/agent-check")]
                return self._run_agent_check(task_id, payload)
            if path == "/api/documents/pins":
                return self._set_document_pin(payload)
            if path == "/api/ideas":
                return self._create_idea(payload)
            if path == "/api/backlog":
                return self._create_backlog_item(payload)
            if path == "/api/invoices":
                return self._create_invoice(config, payload)
            if path == "/api/workflows":
                return self._create_workflow(payload)
            if path == "/api/workflows/validate":
                return self._validate_workflow(payload)
            if path == "/api/tasks/propose":
                return self._propose_task(payload)
            if path == "/api/projects":
                if payload.get("type") == "book" and "books" not in config.activated_modules:
                    return self._send_json(
                        {"ok": False, "error": "Module books is disabled"}, status=409
                    )
                return self._create_project(payload)
            if path.startswith("/api/projects/") and path.endswith("/manuscript"):
                project_id = path[len("/api/projects/") : -len("/manuscript")]
                return self._set_project_manuscript(project_id, payload)
            if path.startswith("/api/projects/") and path.endswith("/check"):
                project_id = path[len("/api/projects/") : -len("/check")]
                return self._request_book_check(project_id, payload)
            if path == "/api/settings":
                return self._save_settings(payload)
            if path == "/api/restrictions/toggles":
                return self._set_restriction_toggle(payload)
            if path == "/api/restrictions/fanout":
                return self._set_fanout_default(payload)
            if path.startswith("/api/inbox/") and path.endswith("/answer"):
                item_id = path[len("/api/inbox/") : -len("/answer")]
                return self._answer_inbox_task(item_id, payload)
            if path.startswith("/api/inbox/") and path.endswith("/close"):
                item_id = path[len("/api/inbox/") : -len("/close")]
                return self._close_inbox_task(item_id, payload)
            if path.startswith("/api/inbox/") and path.endswith("/acknowledge"):
                item_id = path[len("/api/inbox/") : -len("/acknowledge")]
                return self._acknowledge_report(item_id)
            if path.startswith("/api/inbox/") and path.endswith("/supersede"):
                item_id = path[len("/api/inbox/") : -len("/supersede")]
                return self._supersede_report(item_id, payload)
            if path.startswith("/api/inbox/") and path.endswith("/reopen"):
                item_id = path[len("/api/inbox/") : -len("/reopen")]
                return self._reopen_inbox_task(item_id)
            if path.startswith("/api/inbox/") and path.endswith("/delete"):
                item_id = path[len("/api/inbox/") : -len("/delete")]
                return self._delete_inbox_task(item_id)
            if path.startswith("/api/inbox/") and path.endswith("/claim"):
                item_id = path[len("/api/inbox/") : -len("/claim")]
                return self._claim_inbox_task(item_id, payload)
            if path.startswith("/api/inbox/") and path.endswith("/reassign"):
                item_id = path[len("/api/inbox/") : -len("/reassign")]
                return self._reassign_inbox_task(item_id, payload)
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
            if path.startswith("/api/backlog/") and path.endswith("/to-task"):
                item_id = path[len("/api/backlog/") : -len("/to-task")]
                return self._promote_backlog_to_task(item_id)
            if path.startswith("/api/invoices/") and path.endswith("/review"):
                item_id = path[len("/api/invoices/") : -len("/review")]
                return self._review_invoice(item_id, payload)
            if path.startswith("/api/invoices/"):
                item_id = path[len("/api/invoices/") :]
                return self._revise_invoice(item_id, payload)
            if path.startswith("/api/workflows/") and path.endswith("/status"):
                item_id = path[len("/api/workflows/") : -len("/status")]
                return self._set_workflow_status(item_id, payload)
            if path.startswith("/api/runs/") and path.endswith("/report-request"):
                run_id = path[len("/api/runs/") : -len("/report-request")]
                return self._request_run_report(run_id)
            if path.startswith("/api/runs/") and path.endswith("/cancel"):
                run_id = path[len("/api/runs/") : -len("/cancel")]
                return self._cancel_run(run_id)
            if path.startswith("/api/runs/") and path.endswith("/fanout"):
                run_id = path[len("/api/runs/") : -len("/fanout")]
                return self._set_run_fanout(run_id, payload)
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

    def _module_disabled(self, path: str, config: DashboardConfig) -> bool:
        module = module_for_path(path)
        if module and module not in config.activated_modules:
            self._send_json({"ok": False, "error": f"Module {module} is disabled"}, status=409)
            return True
        return False

    def _send_overview(self) -> None:
        stores = self._stores()
        # Filter the complete local records before bounding the visible snapshot.
        _, run_total = stores.runs.list(limit=0)
        _, inbox_total = stores.inbox.list(limit=0)
        runs, _ = stores.runs.list(limit=run_total)
        inbox, _ = stores.inbox.list(limit=inbox_total)
        pending = [item for item in inbox if item.get("status") == "open"]
        active = [
            item
            for item in runs
            if item.get("status")
            in {"running", "queued", "paused", "waiting", "waiting_owner", "approved"}
        ]
        failed = [item for item in runs if item.get("status") == "failed"]

        def summary(items: list[dict]) -> list[dict]:
            return [
                {key: item.get(key) for key in ("id", "title", "status")} for item in items[:20]
            ]

        self._send_json(
            {
                "ok": True,
                "pending": summary(pending),
                "active": summary(active),
                "failed": summary(failed),
                "pending_total": len(pending),
                "active_total": len(active),
                "failed_total": len(failed),
            }
        )

    def _send_modules(self, config: DashboardConfig) -> None:
        self._send_json(
            {
                "ok": True,
                "modules": [
                    {"id": key, **value, "activated": key in config.activated_modules}
                    for key, value in MODULES.items()
                ],
                "landing_page": config.landing_page,
                "core_views": CORE_VIEWS,
            }
        )

    def _send_orchestrator_routes(self, query: str) -> None:
        from orchestrator_view import query_routes

        params = parse_qs(query)
        config = load_config(self.config_path)
        catalog_path = (
            Path(config.catalog_path)
            if config.catalog_path
            else self.repo_root / "packages/ai_orchestrator/examples/model_catalog.toml"
        )
        try:
            result = query_routes(
                catalog_path,
                capabilities=params.get("capability") or None,
                search=params.get("search", [""])[0],
                cost_tier=params.get("cost_tier", ["prepaid_credits_allowed"])[0],
                privacy=params.get("privacy", ["external_allowed"])[0],
            )
        except (ValueError, FileNotFoundError) as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        self._send_json({"ok": True, **result})

    def _review_job_vacancy(self, payload: dict) -> None:
        from jobs_view import review_vacancy

        try:
            result = review_vacancy(payload, self.repo_root)
        except ValueError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        except FileNotFoundError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=409)
        self._send_json({"ok": True, **result})

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
            from wake_idle import cancel_pending, interlock

            with interlock(self.data_dir):
                cancel_pending(self.data_dir)
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
            "open_e2e": stores.open_e2e_count(),
            "attention_inbox": stores.attention_inbox_count(),
            "attention_e2e": stores.attention_e2e_count(),
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
        stores = self._stores()
        self._send_json(
            {
                "ok": True,
                "agent_enabled": config.chat_agent_enabled,
                "sessions": [
                    {
                        "id": record.session_id,
                        "title": record.title,
                        "updated_at_utc": record.updated_at_utc,
                        "privacy_class": record.privacy_class,
                        "mode": stores.get_chat_mode(record.session_id).get("mode", "ask"),
                    }
                    for record in sessions
                ],
            }
        )

    def _send_chat_progress(
        self, config: DashboardConfig, session_id: str, message_id: str
    ) -> None:
        """Read activity and existing scratch status; never create a worktree."""
        from chat_agent import CHAT_WORKTREE_DIRNAME, progress_path, read_progress, staged_files

        result = {"ok": True, "lines": [], "staged": []}
        try:
            record = self._stores().get_chat_mode(session_id)
            if config.chat_agent_enabled and record.get("mode") == "agent":
                activity = progress_path(self.data_dir, session_id, message_id)
                short = "".join(ch for ch in session_id if ch.isalnum())[:12]
                worktree = self.repo_root / CHAT_WORKTREE_DIRNAME / short
                if worktree.is_dir():
                    result["lines"] = read_progress(activity)
                    result["staged"] = staged_files(worktree)
        except Exception:  # noqa: BLE001 - progress must never break chat
            pass
        self._send_json(result)

    def _send_chat_staged(self, session_id: str) -> None:
        from chat_agent import ChatAgentError, ensure_chat_worktree, staged_files

        record = self._stores().get_chat_mode(session_id)
        if record.get("mode") != "agent":
            return self._send_json({"ok": True, "files": []})
        try:
            worktree = ensure_chat_worktree(self.repo_root, session_id)
        except ChatAgentError:
            return self._send_json({"ok": True, "files": []})
        try:
            files = staged_files(worktree.path)
        except ChatAgentError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        self._send_json({"ok": True, "files": files})

    def _set_chat_mode(self, config: DashboardConfig, session_id: str, payload: dict) -> None:
        mode = payload.get("mode", "")
        if mode == "agent" and not config.chat_agent_enabled:
            return self._send_json(
                {"ok": False, "error": "Agent mode is disabled (chat_agent_enabled is off)"},
                status=403,
            )
        try:
            record = self._stores().set_chat_mode(session_id, mode=mode)
        except StoreError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        self._send_json({"ok": True, "id": session_id, "mode": record["mode"]})

    def _save_chat_agent_config(self, payload: dict) -> None:
        from dashboard_config import save_chat_agent

        try:
            saved = save_chat_agent(
                self.config_path, payload.get("enabled"), payload.get("approval")
            )
        except ValueError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        self._send_json({"ok": True, **saved})

    def _apply_chat_staged(self, session_id: str, payload: dict) -> None:
        from chat_agent import ChatAgentError, apply_staged, ensure_chat_worktree

        paths = payload.get("paths", [])
        if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
            return self._send_json(
                {"ok": False, "error": "paths must be a string array"}, status=400
            )
        try:
            worktree = ensure_chat_worktree(self.repo_root, session_id)
            outcome = apply_staged(self.repo_root, worktree, paths)
        except ChatAgentError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        self._send_json({"ok": True, **outcome})

    def _heartbeat_chat_session(self, session_id: str) -> None:
        try:
            record = self._stores().touch_chat_heartbeat(session_id)
        except StoreError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        self._send_json({"ok": True, "id": session_id, "last_seen_at": record.get("last_seen_at")})

    def _approve_chat_turn(self, config: DashboardConfig, session_id: str) -> None:
        try:
            pending = self._stores().take_parked_turn(session_id)
        except StoreError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        try:
            outcome = self._chat(config).send(
                session_id,
                str(pending.get("text", "")),
                stores=self._stores(),
                approved=True,
            )
        except ValueError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        self._send_json(
            {
                "ok": outcome.execution_status == "completed",
                "response_text": outcome.response_text,
                "execution_status": outcome.execution_status,
                "failure_reason": outcome.failure_reason,
            }
        )

    def _reject_chat_turn(self, session_id: str) -> None:
        try:
            self._stores().take_parked_turn(session_id)
        except StoreError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        self._send_json({"ok": True, "id": session_id, "rejected": True})

    def _mail_if_away(self, session_id: str, text: str) -> None:
        """Mail a parked-turn ping when the owner has no recent heartbeat."""
        from datetime import datetime

        try:
            from dashboard_config import load_config

            # Owner decision 2026-11-18: mail only during unattended sessions.
            if load_config(self.config_path).supervision != "unattended":
                return
            record = self._stores().get_chat_mode(session_id)
            last_seen = record.get("last_seen_at") or ""
            seen = datetime.fromisoformat(str(last_seen)) if last_seen else None
            if seen is not None and (datetime.now(seen.tzinfo) - seen).total_seconds() < 300:
                return
            from owner_mail import load_smtp_config, send_owner_mail

            mail_config = load_smtp_config(root=self.repo_root)
            send_owner_mail(
                to=mail_config["owner"],
                subject=f"Agent turn parked in chat {session_id[:8]}",
                body=(
                    "An agent turn parked for approval (ask-always policy):\n\n"
                    f"{text[:2000]}\n\nApprove in the chat thread to run it."
                ),
                config=mail_config,
                dry_run=False,
                receipts_dir=self.data_dir / "mail-receipts",
                data_dir=self.data_dir,
                supervision="unattended",
                blocker=True,
                dedupe_key=f"chat-parked:{session_id}:{text[:2000]}",
            )
        except Exception:  # noqa: BLE001 - mail is best-effort; parked state is the record
            pass

    def _send_chat_messages(self, config: DashboardConfig, session_id: str) -> None:
        try:
            messages = self._chat(config).list_messages(session_id)
        except ValueError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=404)
        pending = self._stores().get_chat_mode(session_id).get("pending_turn")
        from chat_agent import split_agent_transcript

        wire = []
        for message in messages:
            entry: dict = {
                "id": message.message_id,
                "order": message.message_order,
                "role": message.role,
                "content": message.content,
                "provider": message.provider,
                "model": message.model,
                "metadata": message.metadata or {},
            }
            if message.role == "assistant":
                try:
                    view = split_agent_transcript(message.content or "")
                except Exception:  # noqa: BLE001 - a bad transcript must not break chat
                    view = None
                if view is not None and view.has_agent_markers:
                    entry["agent_turn"] = {
                        "report": view.report,
                        "commands": list(view.commands),
                    }
            wire.append(entry)
        self._send_json(
            {
                "ok": True,
                "pending_turn": pending if isinstance(pending, dict) else None,
                "messages": wire,
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
        mode = payload.get("mode")
        if mode is not None and mode not in ("ask", "agent"):
            return self._send_json({"ok": False, "error": "mode must be ask or agent"}, status=400)
        try:
            outcome = self._chat(config).send(
                session_id,
                text,
                language=language,
                translator=self.chat_translator,
                mode=mode,
                stores=self._stores(),
            )
        except TranslationError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=exc.status)
        except ValueError as exc:
            message = str(exc).lower()
            code = 404 if ("not found" in message or "unavailable" in message) else 400
            return self._send_json({"ok": False, "error": str(exc)}, status=code)
        if outcome.execution_status == "parked":
            self._mail_if_away(session_id, text)
        self._send_json(
            {
                "ok": outcome.execution_status in ("completed", "parked"),
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
            seen = {item.get("id") for item in items}
            items = items + [
                item
                for item in self._stores().attention_inbox_items()
                if item.get("id") not in seen and self._stores().project_of(item) == project_id
            ]
        elif wanted is None and for_agent is None:
            seen = {item.get("id") for item in items}
            items = items + [
                item
                for item in self._stores().attention_inbox_items()
                if item.get("id") not in seen
            ]
        runs, _total = self._stores().runs.list(limit=1000)
        latest: dict[str, str] = {}
        for run in runs:
            if not isinstance(run, dict):
                continue
            key = run.get("bridged_from") or run.get("inbox_id")
            if key and key not in latest:
                latest[key] = str(run.get("status") or "")
        for item in items:
            if isinstance(item, dict):
                item["run_status"] = latest.get(item.get("id", "")) or None
        attention_ids = [
            item.get("id")
            for item in self._stores().attention_inbox_items()
            if isinstance(item, dict) and item.get("id")
        ]
        self._send_json(
            {"ok": True, "items": items, "total": len(items), "attention_ids": attention_ids}
        )

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
        metadata = payload.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            return self._send_json({"ok": False, "error": "metadata must be an object"}, status=400)
        project_id = payload.get("project_id")
        if project_id is not None and not isinstance(project_id, str):
            return self._send_json(
                {"ok": False, "error": "project_id must be a string"}, status=400
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
            metadata=metadata,
            project_id=project_id,
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

    def _send_e2e_task(self, task_id: str) -> None:
        record = self._stores().e2e_tasks.get(task_id)
        if record is None:
            return self._send_json({"ok": False, "error": "E2E task not found"}, status=404)
        enriched = dict(record)
        enriched["items"] = [
            (
                {**item, "history": self._stores().history_for_area(str(item.get("area", "")))}
                if isinstance(item, dict)
                else item
            )
            for item in record.get("items", [])
        ]
        self._send_json({"ok": True, "item": enriched})

    def _finalize_e2e_task(self, task_id: str, payload: dict) -> None:
        stores = self._stores()
        if not stores.check_supervisor_token(self.headers.get("X-Supervisor-Token")):
            return self._send_json({"ok": False, "error": "Supervisor token required"}, status=403)
        steps = payload.get("steps")
        if not isinstance(steps, dict):
            return self._send_json(
                {"ok": False, "error": "steps must map item ids to step lists"}, status=400
            )
        try:
            record = stores.finalize_e2e_task(task_id, steps)
        except StoreError as exc:
            status = 404 if "not found" in str(exc).lower() else 400
            return self._send_json({"ok": False, "error": str(exc)}, status=status)
        self._send_json({"ok": True, "id": record["id"], "status": record["status"]})

    def _attach_step_evidence(
        self, steps: list, index: int, timeout_seconds: float
    ) -> dict[str, object]:
        """Run one agent-runnable step and stamp its evidence; may raise ValueError."""
        from e2e_agent_checks import execute_check

        result = execute_check(
            str(steps[index].get("action") or ""),
            self.repo_root,
            timeout_seconds=timeout_seconds,
        )
        steps[index]["evidence"] = result["output"]
        steps[index]["evidence_utc"] = datetime.now(UTC).isoformat()
        steps[index]["evidence_exit"] = result["exit_code"]
        return steps[index]

    def _run_agent_check(self, task_id: str, payload: dict) -> None:
        from e2e_agent_checks import CHECK_TIMEOUT_SECONDS

        stores = self._stores()
        record = stores.e2e_tasks.get(task_id)
        if record is None:
            return self._send_json({"ok": False, "error": "E2E task not found"}, status=404)
        if record.get("status") != "open":
            return self._send_json(
                {"ok": False, "error": "Agent checks run only on open checklists"}, status=409
            )
        item = next(
            (
                entry
                for entry in record.get("items", [])
                if entry.get("id") == payload.get("item_id")
            ),
            None,
        )
        index = payload.get("step_index")
        steps = (item or {}).get("steps") or []
        if (
            item is None
            or type(index) is not int
            or not (0 <= index < len(steps))
            or not steps[index].get("agent_runnable")
        ):
            return self._send_json({"ok": False, "error": "Step is not agent-runnable"}, status=422)
        try:
            step = self._attach_step_evidence(steps, index, CHECK_TIMEOUT_SECONDS)
        except ValueError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=422)
        stores.e2e_tasks.put(task_id, record)
        self._send_json({"ok": True, "evidence": step})

    def _auto_run_pending_checks(self, task_id: str) -> None:
        """Run evidence-less agent steps before submit (brief 24b004b6-A).

        Bounded by SUBMIT_AUTOCHECK_BUDGET_SECONDS across all steps; never
        raises (submit must not fail because evidence gathering hiccuped).
        """
        from e2e_agent_checks import CHECK_TIMEOUT_SECONDS

        try:
            stores = self._stores()
            record = stores.e2e_tasks.get(task_id)
            if record is None or record.get("status") != "open":
                return
            started = time.monotonic()
            touched = False
            for item in record.get("items", []):
                if not isinstance(item, dict):
                    continue
                for index, step in enumerate(item.get("steps") or []):
                    if not isinstance(step, dict):
                        continue
                    if not step.get("agent_runnable") or step.get("evidence"):
                        continue
                    remaining = SUBMIT_AUTOCHECK_BUDGET_SECONDS - (time.monotonic() - started)
                    if remaining <= 0:
                        step["evidence"] = "[auto-check skipped: submit time budget spent]"
                        step["evidence_utc"] = datetime.now(UTC).isoformat()
                        step["evidence_exit"] = None
                        touched = True
                        continue
                    try:
                        self._attach_step_evidence(
                            item["steps"], index, min(remaining, CHECK_TIMEOUT_SECONDS)
                        )
                    except ValueError as exc:
                        step["evidence"] = f"[auto-check failed: {exc}]"
                        step["evidence_utc"] = datetime.now(UTC).isoformat()
                        step["evidence_exit"] = None
                    touched = True
            if touched:
                stores.e2e_tasks.put(task_id, record)
        except Exception as exc:  # noqa: BLE001 - evidence never breaks submit
            print(f"Workbench dashboard: submit auto-checks skipped: {exc}")

    def _send_e2e_tasks(self, query: str) -> None:
        params = parse_qs(query)
        wanted = params.get("status", [None])[0]
        if wanted is not None and wanted not in {"open", "submitted", "draft"}:
            return self._send_json({"ok": False, "error": "Invalid status filter"}, status=400)
        items, _total = self._stores().e2e_tasks.list(limit=100)
        if wanted is not None:
            items = [item for item in items if item.get("status") == wanted]
        self._send_json({"ok": True, "items": items, "total": len(items)})

    def _send_e2e_reports(self) -> None:
        items, total = self._stores().e2e_reports.list(limit=100)
        self._send_json({"ok": True, "items": items, "total": total})

    def _send_e2e_by_view(self, query: str) -> None:
        from e2e_promotion import views_for_area

        params = parse_qs(query)
        view = (params.get("view", [""])[0] or "").strip()
        if not view:
            return self._send_json({"ok": False, "error": "view is required"}, status=400)
        items, _total = self._stores().e2e_tasks.list(limit=100)
        matches: list[dict] = []
        for task in items:
            if not isinstance(task, dict) or task.get("status") != "open":
                continue
            for entry in task.get("items", []):
                if (
                    not isinstance(entry, dict)
                    or entry.get("status") == "auto-pass"
                    or view not in views_for_area(str(entry.get("area", "")))
                ):
                    continue
                matches.append(
                    {
                        "task_id": task.get("id"),
                        "task_title": task.get("title"),
                        "item_id": entry.get("id"),
                        "behavior": entry.get("behavior"),
                        # Live steps, same source the checklist renders — never
                        # a second copy. Legacy how/expected stay as fallback
                        # for stepless items only.
                        "steps": entry.get("steps", []),
                        "how": entry.get("how", []),
                        "expected": entry.get("expected", ""),
                        "draft_notes": entry.get("draft_notes", ""),
                    }
                )
        self._send_json({"ok": True, "view": view, "items": matches})

    def _save_e2e_notes(self, task_id: str, payload: dict) -> None:
        item_id = payload.get("item_id", "")
        notes = payload.get("notes", "")
        if not isinstance(item_id, str) or not item_id.strip():
            return self._send_json({"ok": False, "error": "item_id is required"}, status=400)
        if not isinstance(notes, str):
            return self._send_json({"ok": False, "error": "notes must be a string"}, status=400)
        try:
            self._stores().save_e2e_draft_notes(task_id, item_id, notes)
        except StoreError as exc:
            status = 404 if "not found" in str(exc).lower() else 400
            return self._send_json({"ok": False, "error": str(exc)}, status=status)
        self._send_json({"ok": True, "id": task_id, "item_id": item_id})

    def _create_e2e_task(self, payload: dict) -> None:
        stores = self._stores()
        if not stores.check_supervisor_token(self.headers.get("X-Supervisor-Token")):
            return self._send_json({"ok": False, "error": "Supervisor token required"}, status=403)
        merge_commit = payload.get("merge_commit", "")
        title = payload.get("title", "")
        items = payload.get("items")
        if not isinstance(merge_commit, str) or not isinstance(title, str):
            return self._send_json(
                {"ok": False, "error": "merge_commit and title must be strings"}, status=400
            )
        if not isinstance(items, list):
            return self._send_json(
                {"ok": False, "error": "items must be a checklist array"}, status=400
            )
        created_by = payload.get("created_by", "supervisor")
        if not isinstance(created_by, str):
            return self._send_json(
                {"ok": False, "error": "created_by must be a string"}, status=400
            )
        range_base = payload.get("range_base")
        if range_base is not None and not isinstance(range_base, str):
            return self._send_json(
                {"ok": False, "error": "range_base must be a string"}, status=400
            )
        draft = payload.get("draft", False)
        if not isinstance(draft, bool):
            return self._send_json({"ok": False, "error": "draft must be a boolean"}, status=400)
        try:
            record = stores.create_e2e_task(
                merge_commit=merge_commit,
                title=title,
                items=items,
                created_by=created_by,
                range_base=range_base,
                draft=draft,
            )
        except StoreError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        self._send_json({"ok": True, "id": record["id"]})

    def _submit_e2e_task(self, task_id: str, payload: dict) -> None:
        results = payload.get("results")
        if not isinstance(results, list):
            return self._send_json({"ok": False, "error": "Invalid submit payload"}, status=400)
        verdict_by = payload.get("verdict_by", "owner")
        if verdict_by not in ("owner", "agent"):
            return self._send_json(
                {"ok": False, "error": "verdict_by must be owner or agent"}, status=400
            )
        self._auto_run_pending_checks(task_id)
        try:
            outcome = self._stores().submit_e2e_task(task_id, results, verdict_by=verdict_by)
        except StoreError as exc:
            status = 404 if "not found" in str(exc).lower() else 400
            return self._send_json({"ok": False, "error": str(exc)}, status=status)
        self._send_json(
            {
                "ok": True,
                "id": outcome["task"]["id"],
                "status": outcome["task"]["status"],
                "report_id": outcome["report"]["id"],
                "overall": outcome["report"]["overall"],
                "followup_id": outcome.get("followup_id"),
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
        run["project_id"] = record.get("project_id") or self._stores().default_project_id()
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
        waiting_on = payload.get("waiting_on")
        if waiting_on is not None and waiting_on not in ("owner", "agent"):
            return self._send_json({"ok": False, "error": "Invalid waiting_on"}, status=400)
        try:
            record = self._stores().close_inbox_task(
                item_id,
                resolution=resolution,
                resolution_kind=kind,
                waiting_on=waiting_on,
            )
        except StoreError as exc:
            status = 404 if "not found" in str(exc).lower() else 400
            return self._send_json({"ok": False, "error": str(exc)}, status=status)
        self._send_json({"ok": True, "id": record["id"], "status": record["status"]})

    def _acknowledge_report(self, item_id: str) -> None:
        try:
            record = self._stores().acknowledge_report(item_id)
        except StoreError as exc:
            status = 404 if "not found" in str(exc).lower() else 400
            return self._send_json({"ok": False, "error": str(exc)}, status=status)
        self._send_json({"ok": True, "id": record["id"], "status": record["status"]})

    def _supersede_report(self, item_id: str, payload: dict) -> None:
        by_id = payload.get("by_id", "")
        if not isinstance(by_id, str) or not by_id.strip():
            return self._send_json({"ok": False, "error": "by_id is required"}, status=400)
        try:
            record = self._stores().supersede_report(item_id, by_id=by_id.strip())
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

    def _reassign_inbox_task(self, item_id: str, payload: dict) -> None:
        assignee = payload.get("assignee")
        if assignee not in ("owner", "agent"):
            return self._send_json({"ok": False, "error": "Invalid assignee"}, status=400)
        try:
            record = self._stores().reassign_inbox_task(item_id, assignee)
        except StoreError as exc:
            lowered = str(exc).lower()
            status = 404 if "not found" in lowered else 400
            return self._send_json({"ok": False, "error": str(exc)}, status=status)
        self._send_json({"ok": True, "id": record["id"], "assignee": record["assignee"]})

    def _claim_inbox_task(self, item_id: str, payload: dict) -> None:
        by = payload.get("by")
        if by is not None and (not isinstance(by, str) or not by.strip()):
            return self._send_json({"ok": False, "error": "Invalid claim payload"}, status=400)
        try:
            record = self._stores().claim_inbox_task(item_id, by.strip() if by else None)
        except StoreError as exc:
            status = 404 if "not found" in str(exc).lower() else 400
            return self._send_json({"ok": False, "error": str(exc)}, status=status)
        self._send_json(
            {
                "ok": True,
                "id": record["id"],
                "claimed_by": (record.get("metadata") or {}).get("claimed_by"),
            }
        )

    def _delete_inbox_task(self, item_id: str) -> None:
        try:
            removed = self._stores().inbox.delete(item_id)
        except StoreError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if not removed:
            return self._send_json({"ok": False, "error": "Inbox task not found"}, status=404)
        self._send_json({"ok": True, "id": item_id})

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
                title=title,
                body=body,
                source=source,
                ref=ref,
                gate=payload.get("gate"),
                task_spec=payload.get("task_spec"),
            )
        except StoreError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        self._send_json({"ok": True, "id": record["id"]})

    def _list_invoices(self) -> None:
        from invoices import list_invoices

        self._send_json({"ok": True, "items": list_invoices(self._stores())})

    def _get_invoice(self, item_id: str) -> None:
        from invoices import get_invoice

        try:
            record = get_invoice(self._stores(), item_id)
        except StoreError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if record is None:
            return self._send_json({"ok": False, "error": "Not found"}, status=404)
        self._send_json({"ok": True, "item": record})

    def _create_invoice(self, config, payload: dict) -> None:
        from invoices import create_draft

        try:
            record = create_draft(
                self._stores(), payload, seller_defaults=getattr(config, "seller", None)
            )
        except (ValueError, StoreError) as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        self._send_json({"ok": True, "id": record["id"], "item": record}, status=201)

    def _revise_invoice(self, item_id: str, payload: dict) -> None:
        from invoices import update_draft

        try:
            record = update_draft(self._stores(), item_id, payload)
        except KeyError:
            return self._send_json({"ok": False, "error": "Not found"}, status=404)
        except (ValueError, StoreError) as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        self._send_json({"ok": True, "item": record})

    def _review_invoice(self, item_id: str, payload: dict) -> None:
        from invoices import review_draft

        reviewer = payload.get("reviewer", "")
        try:
            record = review_draft(self._stores(), item_id, reviewer)
        except KeyError:
            return self._send_json({"ok": False, "error": "Not found"}, status=404)
        except (ValueError, StoreError) as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        self._send_json({"ok": True, "item": record})

    def _send_workflow_options(self) -> None:
        from ai_agent.skills import SKILL_TOOLS
        from ai_agent.workflow_graph import AGENT_RUN_MODES, NODE_TYPES

        self._send_json(
            {
                "ok": True,
                "node_types": list(NODE_TYPES),
                "skills": sorted(SKILL_TOOLS),
                "modes": list(AGENT_RUN_MODES),
            }
        )

    def _send_workflows(self, query: str) -> None:
        from dashboard_stores import WORKFLOW_STATUSES

        params = parse_qs(query)
        wanted_status = params.get("status", [None])[0]
        if wanted_status is not None and wanted_status not in WORKFLOW_STATUSES:
            return self._send_json({"ok": False, "error": "Invalid status filter"}, status=400)
        items, _total = self._stores().workflows.list(limit=100)
        if wanted_status is not None:
            items = [item for item in items if item.get("status") == wanted_status]
        self._send_json({"ok": True, "items": items, "total": len(items)})

    def _create_workflow(self, payload: dict) -> None:
        name = payload.get("name", "")
        description = payload.get("description", "")
        nodes = payload.get("nodes", [])
        if not all(isinstance(value, str) for value in (name, description)):
            return self._send_json(
                {"ok": False, "error": "name and description must be strings"}, status=400
            )
        if not isinstance(nodes, list):
            return self._send_json({"ok": False, "error": "nodes must be a list"}, status=400)
        try:
            record = self._stores().create_workflow(name=name, description=description, nodes=nodes)
        except StoreError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        self._send_json({"ok": True, "id": record["id"]})

    def _validate_workflow(self, payload: dict) -> None:
        from ai_agent.workflow_graph import graph_from_dict, plan_graph

        try:
            plan = plan_graph(graph_from_dict(payload.get("graph", payload)))
        except ValueError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        self._send_json({"ok": True, "plan": plan})

    def _set_workflow_status(self, item_id: str, payload: dict) -> None:
        status = payload.get("status", "")
        if not isinstance(status, str):
            return self._send_json({"ok": False, "error": "status must be a string"}, status=400)
        try:
            record = self._stores().set_workflow_status(item_id, status=status)
        except StoreError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        self._send_json({"ok": True, "status": record["status"]})

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

    def _promote_backlog_to_task(self, item_id: str) -> None:
        try:
            result = self._stores().promote_backlog_to_task(item_id)
        except StoreError as exc:
            message = str(exc).lower()
            if "not found" in message:
                code = 404
            elif "gate closed" in message or "open task" in message:
                code = 409
            else:
                code = 400
            return self._send_json({"ok": False, "error": str(exc)}, status=code)
        self._send_json({"ok": True, "id": result["item"]["id"], "task_id": result["task"]["id"]})

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

    def _restrictions_with_toggles(self, config: DashboardConfig) -> None:
        from restrictions import describe_toggles, load_toggles

        status = restrictions_status(self._stores())
        status["toggles"] = describe_toggles(load_toggles(self.data_dir))
        status["fanout"] = {
            "chat": config.chat_fanout_policy,
            "bridge": config.bridge_fanout_policy,
        }
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

    def _set_fanout_default(self, payload: dict) -> None:
        from dashboard_config import save_fanout_default

        scope = payload.get("scope")
        policy = payload.get("policy")
        if not isinstance(scope, str) or not isinstance(policy, str):
            return self._send_json(
                {"ok": False, "error": "scope and policy must be strings"},
                status=400,
            )
        try:
            saved = save_fanout_default(self.config_path, scope, policy)
        except ValueError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        self._send_json({"ok": True, "scope": scope, "policy": saved})

    def _send_documents(self) -> None:
        from doc_pins import load_pinned

        pinned = load_pinned(self.data_dir)
        documents = self._library().list_documents()
        for entry in documents:
            entry["pinned"] = entry.get("id") in pinned
        documents.sort(key=lambda entry: (not entry["pinned"], entry.get("modified_utc") or ""))
        self._send_json({"ok": True, "documents": documents})

    def _set_document_pin(self, payload: dict) -> None:
        from doc_pins import save_pin

        doc_id = payload.get("id")
        pinned = payload.get("pinned")
        if not isinstance(doc_id, str) or not isinstance(pinned, bool):
            return self._send_json(
                {"ok": False, "error": "id must be a string and pinned a boolean"},
                status=400,
            )
        try:
            current = save_pin(self.data_dir, doc_id, pinned)
        except ValueError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        self._send_json({"ok": True, "pinned": sorted(current)})

    def _save_spend_policy(self, payload: dict) -> None:
        import os
        import tempfile

        try:
            rules = policy_rules_from_doc(payload)
        except ValueError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        policy_path = self.data_dir / "spend" / "policy.json"
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        document = {
            "rules": [
                {
                    "scope": rule.scope,
                    "prepaid_allowed": rule.prepaid_allowed,
                    "max_prepaid_cents": rule.max_prepaid_cents,
                }
                for rule in rules
            ]
        }
        fd, tmp_name = tempfile.mkstemp(dir=str(policy_path.parent), prefix="policy")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(document, handle, indent=2, sort_keys=True)
            os.replace(tmp_name, policy_path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        if self.spend_ledger is not None:
            self.spend_ledger.set_rules(rules)
        self._send_json({"ok": True, "spend": spend_status(self.data_dir, self.spend_ledger)})

    def _adjust_spend_balance(self, payload: dict) -> None:
        import datetime

        allowance_id = payload.get("allowance_id")
        remaining = payload.get("remaining_cents")
        if not isinstance(allowance_id, str) or not allowance_id.strip():
            return self._send_json(
                {"ok": False, "error": "allowance_id must be a non-blank string"},
                status=400,
            )
        if not isinstance(remaining, int) or remaining < 0:
            return self._send_json(
                {"ok": False, "error": "remaining_cents must be a non-negative integer"},
                status=400,
            )
        ledger = self.spend_ledger or load_spend_ledger(self.data_dir)
        try:
            balance = ledger.get_allowance(allowance_id).balance_cents
        except KeyError:
            return self._send_json(
                {"ok": False, "error": f"Unknown allowance: {allowance_id}"}, status=404
            )
        if remaining > balance:
            return self._send_json(
                {"ok": False, "error": "remaining exceeds current balance"}, status=400
            )
        amount = balance - remaining
        if amount == 0:
            self._send_json({"ok": True, "spend": spend_status(self.data_dir, self.spend_ledger)})
            return
        day = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")
        admission = ledger.admit(
            task_id=f"manual-{day}-{allowance_id}",
            task_class="manual_adjustment",
            estimated_cents=amount,
            provider=ledger.get_allowance(allowance_id).provider,
        )
        if admission.decision != "admitted" or admission.reservation is None:
            return self._send_json(
                {"ok": False, "error": admission.reason or "adjustment not admitted"},
                status=409,
            )
        if admission.allowance_id != allowance_id:
            ledger.refund(admission.reservation.id)
            return self._send_json(
                {"ok": False, "error": "spend order drew another bucket; retry"},
                status=409,
            )
        ledger.settle(admission.reservation.id, actual_cents=amount, usage_source="manual")
        self._send_json({"ok": True, "spend": spend_status(self.data_dir, self.spend_ledger)})

    def _bridge_inbox_runs(self) -> None:
        from inbox_bridge import bridge_agent_queue, resolve_bridge_fanout

        try:
            from dashboard_config import load_config

            policy = resolve_bridge_fanout(load_config(self.config_path).bridge_fanout_policy)
        except Exception:  # noqa: BLE001 - config trouble fails closed to restricted
            policy = "restricted"
        try:
            receipts = bridge_agent_queue(self._stores(), fanout_policy=policy)
        except Exception as exc:  # noqa: BLE001 - report, never 500 blindly
            return self._send_json({"ok": False, "error": str(exc)}, status=500)
        self._send_json({"ok": True, "bridged": receipts})

    def _send_knowme(self, query: str) -> None:
        from knowme_bank import CATEGORIES, KnowMeStore

        params = parse_qs(query)
        category = params.get("category", [None])[0]
        if category is not None and category not in CATEGORIES:
            return self._send_json(
                {"ok": False, "error": f"Unknown category (one of {', '.join(CATEGORIES)})"},
                status=400,
            )
        try:
            limit = min(max(int(params.get("limit", ["50"])[0]), 1), 200)
        except ValueError:
            return self._send_json({"ok": False, "error": "Invalid limit"}, status=400)
        db_path = self.data_dir / "knowme.sqlite3"
        if not db_path.exists():
            return self._send_json({"ok": True, "entries": [], "count": 0, "bank": "missing"})
        store = KnowMeStore(db_path)
        entries = store.find(category=category, limit=limit)
        self._send_json(
            {
                "ok": True,
                "entries": [
                    {
                        "id": entry.id,
                        "category": entry.category,
                        "text": entry.text,
                        "source": entry.source,
                        "source_file": entry.source_file,
                        "origin_text": entry.origin_text,
                    }
                    for entry in entries
                ],
                "count": store.count(),
                "bank": "ready",
            }
        )

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
        self._send_json(
            {"ok": True, "project": project, "related": self._stores().related(project_id)}
        )

    def _create_project(self, payload: dict) -> None:
        name = payload.get("name")
        root = payload.get("root")
        description = payload.get("description", "")
        project_type = payload.get("type", "general")
        explainer = payload.get("explainer", "")
        if not isinstance(name, str) or not isinstance(root, str):
            return self._send_json(
                {"ok": False, "error": "name and root must be strings"}, status=400
            )
        if not isinstance(description, str) or not isinstance(project_type, str):
            return self._send_json(
                {"ok": False, "error": "description and type must be strings"}, status=400
            )
        if not isinstance(explainer, str):
            return self._send_json({"ok": False, "error": "explainer must be a string"}, status=400)
        try:
            project = create_project(
                self.data_dir,
                name=name,
                root=root,
                description=description,
                project_type=project_type,
                explainer=explainer,
            )
        except StagedEditError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        self._send_json({"ok": True, "project": project})

    def _set_project_manuscript(self, project_id: str, payload: dict) -> None:
        path = payload.get("path", "")
        if not isinstance(path, str):
            return self._send_json({"ok": False, "error": "path must be a string"}, status=400)
        try:
            project = set_project_manuscript(self.data_dir, project_id, path)
        except StagedEditError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        self._send_json({"ok": True, "manuscript": project["manuscript"]})

    def _request_book_check(self, project_id: str, payload: dict) -> None:
        check = payload.get("check", "")
        focus = payload.get("focus", "")
        if not isinstance(check, str) or not isinstance(focus, str):
            return self._send_json(
                {"ok": False, "error": "check and focus must be strings"}, status=400
            )
        try:
            project = get_project(self.data_dir, project_id)
        except StagedEditError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=500)
        if project is None:
            return self._send_json({"ok": False, "error": "Not found"}, status=404)
        try:
            title, body = book_check_task(project, check, focus)
            task = self._stores().create_inbox_task(
                title=title,
                body=body,
                task_type="task",
                created_by="owner",
                assignee="agent",
                metadata={"project_id": project_id, "check": check},
            )
        except (StagedEditError, StoreError) as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        self._send_json({"ok": True, "inbox_id": task["id"]})

    def _approve_intake(self, name: str) -> None:
        from p7_intake import approve_intake

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
        try:
            from e2e_promotion import route_pointer_runs

            routed = route_pointer_runs(stores)
        except Exception as exc:  # noqa: BLE001 - routing never breaks drain
            routed = [{"action": "error", "error": str(exc)[:200]}]
        self._send_json({"ok": True, "outcomes": outcomes, "routed": routed})

    def _cancel_run(self, run_id: str) -> None:
        runs = self._stores().runs
        claim = False
        try:
            run = runs.get(run_id)
            if run is None:
                claim = True
                run = runs.get(run_id, claim=True)
        except StoreError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if run is None:
            return self._send_json({"ok": False, "error": "Not found"}, status=404)
        try:
            request_run_cancel(run)
            runs.put(run_id, run, claim=claim)
        except (StoreError, ValueError) as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        self._send_json({"ok": True, "run": with_fanout_policy(run)})

    def _set_run_fanout(self, run_id: str, payload: dict) -> None:
        from ai_agent.fanout import FanoutPolicy

        try:
            run = self._stores().runs.get(run_id)
        except StoreError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if run is None:
            return self._send_json({"ok": False, "error": "Not found"}, status=404)
        if str(run.get("status") or "") not in ("queued", "paused"):
            return self._send_json(
                {"ok": False, "error": "Fan-out can only change before execution (queued/paused)"},
                status=409,
            )
        try:
            policy = FanoutPolicy.coerce(str(payload.get("policy") or "")).value
        except ValueError:
            return self._send_json(
                {"ok": False, "error": "policy must be one of: allowed, restricted, denied"},
                status=400,
            )
        run["fanout_policy"] = policy
        run["fanout_effective"] = policy
        run["updated_at_utc"] = datetime.now(UTC).isoformat()
        try:
            self._stores().runs.put(run_id, run)
        except StoreError as exc:
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
        if name.lower().endswith(".md"):
            content_type = "text/markdown; charset=utf-8"
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
        from meeting_notes import (
            MEETING_BODY_MAX_BYTES,
            assemble_transcript,
            parse_meeting_form,
            split_wav_clips,
            store_meeting,
        )

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

    def _schedule_sleep(self, payload: dict) -> None:
        minutes = payload.get("delay_minutes", 10)
        if isinstance(minutes, bool) or not isinstance(minutes, int):
            return self._send_json(
                {"ok": False, "error": "delay_minutes must be an integer"}, status=400
            )
        try:
            outcome = schedule_owner_sleep(self.repo_root, minutes, launcher=self.sleep_launcher)
        except ValueError as exc:
            status = 400 if str(exc).startswith("delay must be") else 409
            return self._send_json({"ok": False, "error": str(exc)}, status=status)
        self._send_json({"ok": True, **outcome})

    def _send_meeting(self, meeting_id: str) -> None:
        from meeting_notes import get_meeting, purge_expired_meetings

        purge_expired_meetings(self.data_dir)
        record = get_meeting(self.data_dir, meeting_id)
        if record is None:
            return self._send_json({"ok": False, "error": "Not found"}, status=404)
        self._send_json({"ok": True, **record})

    def _analyze_meeting_endpoint(self, config, meeting_id: str, payload: dict) -> None:
        from meeting_notes import analyze_meeting

        confirm = payload.get("confirm_external", False)
        if confirm is not True:
            return self._send_json(
                {"ok": False, "error": "external analysis requires explicit confirmation"},
                status=409,
            )
        try:
            if self.analysis_client_factory is not None:
                client, model_id, route_id = self.analysis_client_factory()
            else:
                client, model_id, route_id = _resolve_analysis_client(config, self.repo_root)
        except ValueError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=503)
        try:
            ledger = self.spend_ledger
            if ledger is not None:
                from ai_orchestrator.spend_ledger import record_measured_usage
                from ai_provider.route_eval import estimate_cost_usd
                from ai_provider.turn_usage import measured_calls

                def _sink(summary: dict, context: dict) -> None:
                    record_measured_usage(
                        ledger,
                        summary,
                        task_id=f"meeting-{meeting_id}",
                        task_class="meeting_analysis",
                        provider=str(route_id or ""),
                        model_id=str(model_id or ""),
                        estimate_cost_usd=estimate_cost_usd,
                    )

                with measured_calls(sink=_sink, context={}):
                    outcome = analyze_meeting(
                        self.data_dir,
                        meeting_id,
                        client=client,
                        model_id=model_id,
                        route_id=route_id,
                        confirm_external=True,
                    )
            else:
                outcome = analyze_meeting(
                    self.data_dir,
                    meeting_id,
                    client=client,
                    model_id=model_id,
                    route_id=route_id,
                    confirm_external=True,
                )
        except KeyError:
            return self._send_json({"ok": False, "error": "Not found"}, status=404)
        except ValueError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, status=502)
        except ProviderError as exc:
            return self._send_json(
                {"ok": False, "error": f"analysis model failed: {exc}"}, status=502
            )
        self._send_json({"ok": True, **outcome})

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
DRAIN_PAUSE_ALERT_KIND = "drain-pause"
DRAIN_PAUSE_CLASSES = frozenset({"allowance", "config"})
_drain_pause_lock = threading.Lock()


def _run_sort_key(run: dict) -> str:
    return str(
        run.get("finished_at_utc") or run.get("updated_at_utc") or run.get("created_at_utc") or ""
    )


def drain_pause_state(stores: DashboardStores) -> dict | None:
    """AI-visible drain pause; None means proceed this tick.

    Pauses when the newest terminal failure is allowance/config-related
    with no success since, so the queue stops burning money or hammering
    a broken setup. Files one AI alert (deduped); the AI agent resumes
    by closing it after fixing the underlying issue, and a later failure
    re-files. Recovered runs auto-close a stale alert. Manual drains
    bypass the pause (explicit owner action).
    """
    runs, _ = stores.runs.list(limit=10000)
    failed = sorted(
        (
            run
            for run in runs
            if isinstance(run, dict)
            and run.get("status") == "failed"
            and _run_failure_class(run) in DRAIN_PAUSE_CLASSES
        ),
        key=_run_sort_key,
        reverse=True,
    )
    succeeded = sorted(
        (
            run
            for run in runs
            if isinstance(run, dict) and run.get("status") in ("completed", "merged")
        ),
        key=_run_sort_key,
        reverse=True,
    )
    # Scheduler and HTTP ticks may observe the same failure concurrently.
    # Read alerts inside the filing lock so the second caller sees the first alert.
    with _drain_pause_lock:
        return _drain_pause_alert_state(stores, failed, succeeded)


def _drain_pause_alert_state(
    stores: DashboardStores, failed: list[dict], succeeded: list[dict]
) -> dict | None:
    """Check and file pause alerts while holding the drain pause lock."""
    inbox, _ = stores.inbox.list(limit=10000)
    alerts = [
        item
        for item in inbox
        if isinstance(item, dict)
        and (item.get("metadata") or {}).get("kind") == DRAIN_PAUSE_ALERT_KIND
    ]
    open_alerts = [item for item in alerts if item.get("status") == "open"]
    blocking = bool(failed) and (
        not succeeded or _run_sort_key(failed[0]) > _run_sort_key(succeeded[0])
    )
    if not blocking:
        for alert in open_alerts:
            stores.close_inbox_task(
                alert["id"],
                resolution="Recovered: a run completed since the pause; drain resumed.",
            )
        return None
    newest = failed[0]
    reason = (
        f"run {newest.get('id', '?')[:8]} failed ({_run_failure_class(newest)}): "
        f"{str(newest.get('error') or 'no error recorded')[:160]}"
    )
    if open_alerts:
        return {"paused": True, "reason": reason, "alert_id": open_alerts[0]["id"]}
    failure_ts = _run_sort_key(newest)
    if any(
        str(alert.get("resolved_at") or alert.get("updated_at") or "") > failure_ts
        for alert in alerts
        if alert.get("status") != "open"
    ):
        return None  # owner acknowledged by closing; resume until the next failure
    alert = stores.create_inbox_task(
        title="Drain paused: allowance or config failure",
        body=(
            f"{reason}\n\nQueued runs are held, not executed. Investigate and fix "
            "the underlying issue (grants/budget or configuration), then close "
            "this task to resume. A later failure re-files automatically."
        ),
        task_type="task",
        metadata={
            "kind": DRAIN_PAUSE_ALERT_KIND,
            "run_id": newest["id"],
            "failure_class": _run_failure_class(newest),
        },
        assignee="agent",
    )
    return {"paused": True, "reason": reason, "alert_id": alert["id"]}


def should_start_drain_scheduler(config: DashboardConfig) -> bool:
    """Return True when the config enables periodic run drains."""
    return config.drain_interval_seconds >= DRAIN_SCHEDULER_MIN_INTERVAL_SECONDS


def _file_failed_run_triage(stores: DashboardStores, run: dict, run_id: str, summary: dict) -> None:
    """File one agent triage task for a failed run; never raises.

    Dedupes on open inbox tasks with ``metadata.triage_for == run_id``.
    A store cap-refusal flags ``triage_pending`` on the open source item
    (mirroring ``closeout_pending``) instead of raising; a successful
    filing clears that stale flag.
    """
    try:
        try:
            items, _total = stores.inbox.list(limit=1000)
        except Exception:  # noqa: BLE001 - triage scan failure means no dedupe hit
            items = []
        for existing in items:
            if not isinstance(existing, dict):
                continue
            if existing.get("status") != "open":
                continue
            metadata = existing.get("metadata") or {}
            if isinstance(metadata, dict) and metadata.get("triage_for") == run_id:
                return
        source_ref = run.get("bridged_from") or run.get("inbox_id")
        if isinstance(source_ref, str) and source_ref:
            try:
                source_item = stores.inbox.get(source_ref)
            except Exception:  # noqa: BLE001 - triage never breaks report-back
                source_item = None
            if isinstance(source_item, dict) and (source_item.get("metadata") or {}).get(
                "triage_for"
            ):
                return  # failed triage runs don't spawn meta-triage; source stays open
        failure_class = summary.get("failure_class") or _run_failure_class(run)
        error = summary.get("error") or run.get("error") or "(unknown error)"
        body = (
            f"Run {run_id} failed.\n"
            f"Error: {error}\n"
            f"Failure class: {failure_class}\n"
            f"Run report: see run {run_id} (run:{run_id}).\n\n"
            "Triage the failure and decide the follow-up."
        )
        project_id: str | None = None
        candidate = run.get("project_id")
        if isinstance(candidate, str) and candidate.strip():
            project_id = candidate.strip()
        if project_id is None:
            source_ref = run.get("bridged_from") or run.get("inbox_id")
            if isinstance(source_ref, str) and source_ref:
                try:
                    source_item = stores.inbox.get(source_ref)
                except Exception:  # noqa: BLE001 - triage never breaks report-back
                    source_item = None
                if isinstance(source_item, dict):
                    raw_pid = source_item.get("project_id")
                    if isinstance(raw_pid, str) and raw_pid.strip():
                        project_id = raw_pid.strip()
        if project_id is None:
            try:
                project_id = stores.default_project_id()
            except Exception:  # noqa: BLE001 - create_inbox_task re-defaults on None
                project_id = None
        try:
            stores.create_inbox_task(
                title=f"Triage failed run {run_id[:8]}",
                body=body,
                task_type="task",
                created_by="supervisor",
                assignee="agent",
                project_id=project_id,
                metadata={"triage_for": run_id},
                context_refs=[f"run:{run_id}"],
            )
        except StoreError:
            try:
                pending_ref = run.get("bridged_from") or run.get("inbox_id")
                if isinstance(pending_ref, str) and pending_ref:
                    try:
                        pending_item = stores.inbox.get(pending_ref)
                    except Exception:  # noqa: BLE001 - pending flag is best-effort
                        pending_item = None
                    if isinstance(pending_item, dict) and pending_item.get("status") == "open":
                        pending_item["triage_pending"] = True
                        try:
                            stores.inbox.put(pending_ref, pending_item)
                        except Exception:  # noqa: BLE001 - pending flag is best-effort
                            return
            except Exception:  # noqa: BLE001 - triage never breaks report-back
                return
            return
        try:
            clear_ref = run.get("bridged_from") or run.get("inbox_id")
            if isinstance(clear_ref, str) and clear_ref:
                try:
                    clear_item = stores.inbox.get(clear_ref)
                except Exception:  # noqa: BLE001 - pending clear is best-effort
                    clear_item = None
                if (
                    isinstance(clear_item, dict)
                    and clear_item.get("status") == "open"
                    and "triage_pending" in clear_item
                ):
                    clear_item.pop("triage_pending", None)
                    try:
                        stores.inbox.put(clear_ref, clear_item)
                    except Exception:  # noqa: BLE001 - pending clear is best-effort
                        return
        except Exception:  # noqa: BLE001 - triage never breaks report-back
            return
    except Exception:  # noqa: BLE001 - triage never breaks report-back
        return


def report_run_terminal(stores: DashboardStores, summary: dict) -> dict:
    """Append a terminal run's outcome to its source inbox item (report-back).

    The bridge files runs from inbox items; this closes the loop so no
    finished work orphans its request. Notes only — items stay open for
    owner review; repeats dedupe on the run id. Failed runs additionally
    file one agent triage task (deduped, cap-safe). Never raises.
    """
    try:
        run_id = str(summary.get("run_id") or "")
        run = stores.runs.get(run_id) if run_id else None
        if run_id and summary.get("status") == "failed":
            _file_failed_run_triage(stores, run or {}, run_id, summary)
        source_id = (run or {}).get("bridged_from") or (run or {}).get("inbox_id")
        if not run or not source_id:
            return {"action": "skipped", "reason": "no linked source item"}
        item = stores.inbox.get(source_id)
        if item is None or item.get("status") != "open":
            return {"action": "skipped", "reason": "source not open"}
        note = item.get("note") or ""
        if run_id and run_id in note:
            return {"action": "skipped", "reason": "already noted"}
        status = summary.get("status", "?")
        error = summary.get("error")
        line = f"Run {run_id[:8]} {status}"
        if error:
            line += f": {error}"[:300]
        else:
            line += " — see the run report for results."
        item["note"] = (note + "\n" + line).strip() if note else line
        stores.inbox.put(source_id, item)
        return {"action": "noted", "run_id": run_id}
    except Exception as exc:  # noqa: BLE001 - report-back never breaks drain
        return {"action": "skipped", "reason": f"{type(exc).__name__}: {exc}"[:200]}


def build_run_drain(
    config: DashboardConfig,
    data_dir: Path,
    repo_root: Path,
    stores: DashboardStores,
    executor_factory: Callable[[], Executor] | None = None,
    worker_epoch: str | None = None,
) -> RunDrain:
    """Build the approved-runs drain shared by manual and scheduled drains.

    The default executor hands each run to a Mai session (Mai routes the
    model through the orchestrator by criteria) inside a per-run scratch
    worktree, so agent edits never touch shared checkouts; ``executor_factory``
    overrides it in tests. Runs are stamped with the worker epoch so boot
    reconciliation can tell orphaned runs from live ones.
    """
    if executor_factory is not None:
        executor = executor_factory()
    else:
        from mai_run import build_mai_executor, build_retrying_executor

        executor = build_retrying_executor(
            build_mai_executor(
                repo_root,
                repo_root / "user-config.toml",
                catalog=config.catalog_path or None,
                backend=getattr(config, "mai_backend", "subprocess"),
                isolate=True,
                progress_dir=data_dir / "run-progress",
            )
        )

    def _notify(summary: dict) -> None:
        report_run_terminal(stores, summary)
        try:
            # Read recorded follow-ups after report-back has filed failed-run triage.
            run_id = str(summary.get("run_id") or "")
            run = stores.runs.get(run_id) or {}
            summary = dict(summary)
            summary["shipment"] = run.get("shipment")
            summary["inbox_id"] = run.get("bridged_from") or run.get("inbox_id")
            items, _ = stores.inbox.list(limit=1000)
            for item in items:
                if (
                    item.get("status") == "open"
                    and (item.get("metadata") or {}).get("triage_for") == run_id
                ):
                    summary["triage_item"] = item.get("id")
                    break
            from owner_mail import notify_plan

            sender, notify_on = notify_plan(
                config.supervision, data_dir / "mail-receipts", root=repo_root
            )
        except Exception:  # noqa: BLE001 - terminal mail never breaks drain
            return
        if sender is None or summary.get("status") not in notify_on:
            return
        try:
            sender(summary)
        except Exception:  # noqa: BLE001 - terminal mail never breaks drain
            pass

    def _note(inbox_id: str, note: str) -> None:
        item = stores.inbox.get(inbox_id)
        if item is None:
            raise KeyError(f"inbox item gone: {inbox_id}")
        item["notes"] = (item.get("notes") or "") + note
        stores.inbox.put(inbox_id, item)

    def _run_has_output(run_id: str) -> bool:
        import re

        safe_id = re.sub(r"[^A-Za-z0-9_-]", "", run_id)[:64]
        try:
            return (data_dir / "run-progress" / f"{safe_id}.jsonl").stat().st_size > 0
        except OSError:
            return False

    def _ship_completed(run: dict) -> dict:
        from drain_ship import ship_completed_run

        return ship_completed_run(run, repo_root=repo_root, stores=stores)

    return RunDrain(
        runs_dir=data_dir / "runs",
        get_inbox=lambda inbox_id: stores.inbox.get(inbox_id),
        executor=executor,
        worker_epoch=worker_epoch or datetime.now(UTC).isoformat(),
        on_terminal=_notify,
        inbox_note=_note,
        output_evidence=_run_has_output,
        ship_completed=_ship_completed,
    )


def reconcile_runs_at_startup(
    config: DashboardConfig,
    data_dir: Path,
    drain_root: Path,
    stores: DashboardStores,
    epoch: str,
) -> list[dict]:
    """Requeue runs orphaned by a restart; drained runs resume unattended.

    Only runs from a different worker epoch — provably dead workers —
    are requeued; anything stamped with this boot's epoch is live and
    stays untouched. Never raises: reconcile must not block serving.
    """
    try:
        drain = build_run_drain(config, data_dir, drain_root, stores)
    except (StagedEditError, ValueError, OSError) as exc:
        print(f"Workbench dashboard: startup reconcile skipped (drain: {exc})")
        return []
    try:
        outcomes = drain.reconcile(epoch)
    except Exception as exc:  # noqa: BLE001 - reconcile must never block serving
        print(f"Workbench dashboard: startup reconcile failed: {exc}")
        return []
    if outcomes:
        print(f"Workbench dashboard: startup reconcile: {outcomes}")
    return outcomes


def maybe_start_drain_scheduler(
    config_path: Path, data_dir: Path, *, repo_root: Path | None = None
) -> DrainScheduler | None:
    """Start periodic drains when configured; never raises."""
    try:
        config = load_config(config_path)
    except ValueError as exc:
        print(f"Workbench dashboard: drain scheduler off (config: {exc})")
        return None
    if not should_start_drain_scheduler(config):
        return None
    stores = DashboardStores(data_dir)
    drain_root = repo_root or REPO_ROOT

    from wake_idle import WakeIdle

    wake_idle = WakeIdle(data_dir, config_path, drain_root)

    def tick() -> None:
        try:
            wake_idle.tick()
        except Exception as exc:  # noqa: BLE001 - idle failure must not stop drains
            print(f"Workbench dashboard: wake-idle check failed: {exc}")
        from inbox_bridge import bridge_agent_queue, resolve_bridge_fanout

        try:
            from owner_digest import flush_digest
            from owner_mail import load_smtp_config

            current = load_config(config_path)
            if current.supervision == "unattended":
                flush_digest(
                    data_dir=data_dir,
                    supervision=current.supervision,
                    config=load_smtp_config(root=drain_root),
                )
        except Exception as exc:  # noqa: BLE001 - delivery must not stop supervision
            print(f"Workbench dashboard: digest flush failed: {type(exc).__name__}")

        try:
            bridged = bridge_agent_queue(
                stores, fanout_policy=resolve_bridge_fanout(config.bridge_fanout_policy)
            )
        except Exception as exc:  # noqa: BLE001 - tick failures are never fatal
            print(f"Workbench dashboard: inbox bridge failed: {exc}")
            bridged = []
        if bridged:
            print(f"Workbench dashboard: bridged {len(bridged)} inbox tasks to runs")
        try:
            promoted = stores.promote_open_backlog()
        except Exception as exc:  # noqa: BLE001 - tick failures are never fatal
            print(f"Workbench dashboard: backlog auto-promote failed: {exc}")
            promoted = []
        if promoted:
            print(f"Workbench dashboard: auto-promoted {len(promoted)} backlog items")
        try:
            from supervisor_followups import supervisor_tick_audit

            audit = supervisor_tick_audit(stores)
        except Exception as exc:  # noqa: BLE001 - tick failures are never fatal
            print(f"Workbench dashboard: supervisor self-audit failed: {exc}")
            audit = {}
        healed = (audit.get("healed") or {}) if isinstance(audit, dict) else {}
        if any(healed.values()):
            print(f"Workbench dashboard: self-audit healed {healed}")
        paused = drain_pause_state(stores)
        if paused is not None:
            print(f"Workbench dashboard: scheduled drain paused: {paused['reason']}")
            return
        drain = build_run_drain(config, data_dir, drain_root, stores)
        outcomes = drain.drain(max_runs=SCHEDULER_DRAIN_MAX_RUNS)
        print(f"Workbench dashboard: scheduled drain: {outcomes}")
        try:
            from e2e_promotion import route_pointer_runs

            routed = route_pointer_runs(stores)
        except Exception as exc:  # noqa: BLE001 - tick failures are never fatal
            print(f"Workbench dashboard: pointer routing failed: {exc}")
            routed = []
        if routed:
            print(f"Workbench dashboard: routed pointer runs: {routed}")

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
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="State root for receipts/docs (.env, .tmp, window status). Defaults to the code checkout; the serve worktree points it at the main checkout.",
    )
    return parser


def ensure_single_server(host: str, port: int, *, probe=None) -> None:
    """Refuse to start when another server already holds the port.

    On Windows the listener socket allows double binds, so two racing
    starters would both serve (and split traffic) without this guard.
    Exits loudly instead of double-serving: a second server is never
    correct, and the supervisor's health check reports the outcome.
    """
    check = probe or _probe_busy
    if check(host, port):
        print(
            f"Workbench dashboard: {host}:{port} is already served; "
            "refusing to start a second server."
        )
        raise SystemExit(1)


def _probe_busy(host: str, port: int) -> bool:
    """True when something answers on the dashboard port."""
    import socket

    probe = socket.socket()
    probe.settimeout(2.0)
    try:
        probe.connect((host, port))
    except OSError:
        return False
    finally:
        probe.close()
    return True


def main() -> None:
    args = build_parser().parse_args()
    from ai_provider.secrets import load_dotenv

    loaded = load_dotenv(args.repo_root or REPO_ROOT)
    if loaded:
        print(f"Workbench dashboard: secret store loaded ({len(loaded)} keys by name)")
    DashboardRequestHandler.config_path = args.config
    DashboardRequestHandler.data_dir = args.data_dir
    state_root = args.repo_root or REPO_ROOT
    DashboardRequestHandler.repo_root = state_root
    DashboardRequestHandler.served_version = capture_server_version(
        REPO_ROOT, config_path=args.config, data_dir=args.data_dir
    )
    try:
        pid_path = args.data_dir / "dashboard.pid"
        pid_tmp = pid_path.with_suffix(".json.tmp")
        pid_tmp.write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "argv": [sys.executable, *sys.argv],
                    "cwd": os.getcwd(),
                    "started_utc": datetime.now(UTC).isoformat(),
                }
            ),
            encoding="utf-8",
        )
        pid_tmp.replace(pid_path)
    except OSError as exc:
        print(f"Workbench dashboard: pidfile unwritable, supervisor restarts unavailable: {exc}")
    boot_epoch = datetime.now(UTC).isoformat()
    try:
        boot_config = load_config(args.config)
        reconcile_runs_at_startup(
            boot_config, args.data_dir, state_root, DashboardStores(args.data_dir), boot_epoch
        )
    except Exception as exc:  # noqa: BLE001 - reconcile must never block serving
        print(f"Workbench dashboard: startup reconcile failed: {exc}")
    try:
        DashboardRequestHandler.drain_scheduler = maybe_start_drain_scheduler(
            args.config, args.data_dir, repo_root=state_root
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
    ensure_single_server(args.host, args.port)
    server = ThreadingHTTPServer((args.host, args.port), DashboardRequestHandler)
    print(f"Workbench dashboard: http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
