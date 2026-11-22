"""Daily allowance health check: stale models + refresh-eve provider state.

Reads native allowance windows (codex required, copilot/kiro best-effort),
flags exhausted windows and failed codex reads, lists models with no spend
in STALE_DAYS, and writes a receipt. Files ONE agent inbox item on problems
(deduped by problem hash); healthy runs stay silent. 5h rolling windows
refresh too fast to target, so they get health-checked, not eve-checked.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve()
REPO_ROOT = HERE.parents[1]
DASHBOARD_DIR = REPO_ROOT / "apps" / "workbench_dashboard"
DEFAULT_DATA_DIR = DASHBOARD_DIR / "data"

sys.path.insert(0, str(DASHBOARD_DIR))

STALE_DAYS = 30
REFRESH_HORIZON_HOURS = 24
EXHAUST_PCT = 95.0
READ_TIMEOUT_SECONDS = 15.0
DEDUPE_KEY = "allowance-health"


def _window_used(window: dict[str, Any]) -> float | None:
    for key in ("used_percent", "remaining_percent"):
        value = window.get(key)
        if isinstance(value, (int, float)):
            return float(value) if key == "used_percent" else 100.0 - float(value)
    return None


def _resets_within(window: dict[str, Any], now: datetime, horizon_h: float) -> bool:
    raw = window.get("resets_at_utc")
    if not isinstance(raw, str) or not raw:
        return False
    try:
        moment = datetime.fromisoformat(raw)
    except ValueError:
        return False
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    delta = (moment - now).total_seconds()
    return 0 <= delta <= horizon_h * 3600


def evaluate(
    readings: dict[str, dict[str, Any]],
    spend_models: list[tuple[str, float]],
    now: datetime,
    *,
    stale_days: int = STALE_DAYS,
    refresh_horizon_h: float = REFRESH_HORIZON_HOURS,
    exhaust_pct: float = EXHAUST_PCT,
    previously_available: set[str] | None = None,
) -> dict[str, Any]:
    """Pure evaluation: problems to file, stale models, unavailable readers."""
    problems: list[dict[str, Any]] = []
    unavailable: list[str] = []
    regressed = previously_available or set()
    for provider in sorted(readings):
        report = readings[provider]
        if report.get("status") != "available":
            if provider == "codex":
                problems.append(
                    {
                        "kind": "reader_failed",
                        "provider": provider,
                        "detail": str(report.get("reason") or "unknown"),
                    }
                )
            elif provider in regressed:
                problems.append(
                    {
                        "kind": "reader_regressed",
                        "provider": provider,
                        "detail": f"was available, now {report.get('reason') or 'unknown'}",
                    }
                )
            else:
                unavailable.append(provider)
            continue
        for window in report.get("windows") or []:
            if not isinstance(window, dict):
                continue
            used = _window_used(window)
            label = f"{window.get('bucket_id')}/{window.get('window')}"
            if used is not None and used >= exhaust_pct:
                problems.append(
                    {
                        "kind": "window_exhausted",
                        "provider": provider,
                        "detail": f"{label} at {used:.1f}% used",
                    }
                )
            elif _resets_within(window, now, refresh_horizon_h):
                problems.append(
                    {
                        "kind": "refresh_approaching",
                        "provider": provider,
                        "detail": f"{label} resets at {window.get('resets_at_utc')}",
                    }
                )
    cutoff = now.timestamp() - stale_days * 86400
    stale = sorted({model for model, ts in spend_models if model and ts < cutoff})
    return {"problems": problems, "stale_models": stale, "unavailable": sorted(unavailable)}


def _problems_hash(problems: list[dict[str, Any]]) -> str:
    canonical = json.dumps(problems, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def file_problems(stores, problems: list[dict[str, Any]], stale: list[str]):
    """File actionable agent investigation; deduplicate unresolved problem sets."""
    if not problems:
        return None
    digest = _problems_hash(problems)
    items, _total = stores.inbox.list(limit=1000)
    for item in items:
        meta = item.get("metadata") or {}
        if (
            meta.get("key") == DEDUPE_KEY
            and meta.get("problems_hash") == digest
            and item.get("status") in {"open", "answered"}
        ):
            return None
    lines = ["Allowance health check found problems:"]
    for problem in problems:
        lines.append(f"- [{problem['provider']}] {problem['kind']}: {problem['detail']}")
    lines.extend(
        [
            "",
            "Agent action:",
            "1. Inspect the latest .tmp/allowance-health/receipt-*.json and compare "
            "the prior reading; retain the failure evidence.",
            "2. Trace the affected provider reader in packages/ai_provider/src/ai_provider/ "
            "and its command discovery. Check installed client paths and scheduled-task "
            "environment before attributing the failure to the provider or account.",
            "3. Fix a confirmed local defect and add focused regression tests. For exhausted "
            "or resetting windows, report the reset/headroom evidence without treating "
            "normal quota state as a software defect.",
            "4. Run focused tests and lint; record findings, changes, checks and any "
            "remaining limitation as this item's resolution, then close it.",
            "Escalate only an evidenced owner decision or manual action with a complete "
            "decision brief. Do not change billing, credentials, client versions or run "
            "inference to diagnose this alert.",
        ]
    )
    if stale:
        lines.append("")
        lines.append(f"Models with no spend in {STALE_DAYS}d (info): {', '.join(stale)}")
    return stores.create_inbox_task(
        title=f"Allowance health: {len(problems)} problem(s)",
        body="\n".join(lines),
        task_type="task",
        created_by="supervisor",
        assignee="agent",
        options=[],
        context_refs=["scripts/allowance_healthcheck.py", ".tmp/allowance-health/"],
        metadata={"key": DEDUPE_KEY, "problems_hash": digest},
    )


def _read_allowances() -> dict[str, dict[str, Any]]:
    from ai_provider.codex_usage import read_codex_allowance
    from ai_provider.copilot_usage import read_copilot_allowance
    from ai_provider.kiro_usage import read_kiro_allowance

    readers = (
        ("codex", read_codex_allowance),
        ("copilot", read_copilot_allowance),
        ("kiro", read_kiro_allowance),
    )
    readings: dict[str, dict[str, Any]] = {}
    for provider, reader in readers:
        try:
            readings[provider] = reader(timeout_seconds=READ_TIMEOUT_SECONDS)
        except Exception as exc:  # noqa: BLE001 - one reader must not kill the check
            readings[provider] = {"status": "unknown", "reason": type(exc).__name__, "windows": []}
    return readings


def _spend_models(data_dir: Path) -> list[tuple[str, float]]:
    from ai_orchestrator.spend_ledger import SpendLedger

    path = data_dir / "spend_ledger.sqlite3"
    if not path.is_file():
        return []
    ledger = SpendLedger(path)
    seen: dict[str, float] = {}
    for record in ledger.records():
        if record.model_id:
            seen[record.model_id] = max(seen.get(record.model_id, 0.0), record.timestamp)
    return sorted(seen.items())


def _previously_available(receipt_dir: Path) -> set[str]:
    """Providers available in the latest prior receipt (regression baseline)."""
    try:
        receipts = sorted(receipt_dir.glob("receipt-*.json"))
    except OSError:
        return set()
    if not receipts:
        return set()
    try:
        data = json.loads(receipts[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    readers = data.get("readers") or {}
    return {name for name, status in readers.items() if status == "available"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--receipt-dir", type=Path, default=None)
    parser.add_argument("--stale-days", type=int, default=STALE_DAYS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    from dashboard_stores import DashboardStores

    now = datetime.now(UTC)
    receipt_dir = args.receipt_dir or (REPO_ROOT / ".tmp" / "allowance-health")
    receipt_dir.mkdir(parents=True, exist_ok=True)
    previously = _previously_available(receipt_dir)
    readings = _read_allowances()
    models = _spend_models(args.data_dir)
    result = evaluate(
        readings, models, now, stale_days=args.stale_days, previously_available=previously
    )
    receipt = {
        "checked_at_utc": now.isoformat(),
        "problems": result["problems"],
        "stale_models": result["stale_models"],
        "unavailable": result["unavailable"],
        "readers": {name: report.get("status") for name, report in readings.items()},
    }
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    (receipt_dir / f"receipt-{stamp}.json").write_text(
        json.dumps(receipt, indent=2), encoding="utf-8"
    )
    if args.dry_run:
        print(json.dumps(receipt, indent=2))
        return 0
    filed = file_problems(
        DashboardStores(args.data_dir), result["problems"], result["stale_models"]
    )
    print(
        f"problems={len(result['problems'])} stale={len(result['stale_models'])} filed={bool(filed)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
