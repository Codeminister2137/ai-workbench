"""Fetch, summarize, and mail the weekly digest to the owner.

One shot: probe the Gmail login, fetch the latest mails, summarize them via
the hosted no-training route, and mail the summary to the owner's own address.
A JSON receipt lands under ``.tmp/weekly-digest/`` on every run.

Exit codes: 0 mailed, 2 skipped (reason in the receipt), 1 failed.
``--dry-run`` probes and fetches but neither summarizes (spend) nor sends.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(
    *,
    count: int = 10,
    out_dir: Path | None = None,
    dry_run: bool = False,
    digest_module=None,
    notify_module=None,
) -> dict[str, Any]:
    """Run one digest cycle; returns the receipt dict (also written to disk)."""
    digest = digest_module or _load_script("mail_digest")
    notify = notify_module or _load_script("loop_notify")
    target = out_dir or (ROOT / ".tmp" / "weekly-digest")
    target.mkdir(parents=True, exist_ok=True)
    receipt: dict[str, Any] = {
        "at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": count,
        "dry_run": dry_run,
        "status": "failed",
    }

    def _finish(status: str, **extra: Any) -> dict[str, Any]:
        receipt["status"] = status
        receipt.update(extra)
        path = target / f"weekly-digest-{receipt['at_utc'].replace(':', '')}.json"
        path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        receipt["receipt_path"] = str(path)
        return receipt

    ok, reason = digest.probe()
    if not ok:
        return _finish("skipped", reason=f"probe-{reason}")
    try:
        messages = digest.fetch_latest(count)
    except digest.DigestError as error:
        return _finish("skipped", reason=str(error))
    receipt["fetched"] = len(messages)
    if not messages:
        return _finish("skipped", reason="empty-inbox")
    if dry_run:
        return _finish("skipped", reason="dry-run")
    try:
        summary = digest.summarize_digest(messages)
    except digest.DigestError as error:
        return _finish("skipped", reason=f"summarize-{error}")
    receipt["summary_chars"] = len(summary.get("summary", ""))
    receipt["model"] = summary.get("model")
    receipt["estimated_usd"] = summary.get("estimated_usd")
    lines = [
        "Weekly mail digest",
        "",
        summary.get("summary", ""),
        "",
        f"Model: {summary.get('model')}; est. ${summary.get('estimated_usd')}.",
    ]
    ping = notify.send_ping(
        subject=f"Weekly digest ({receipt['at_utc'][:10]})",
        body="\n".join(lines),
        run_dir=target,
        event="weekly-digest",
    )
    return _finish("mailed" if ping.get("success") else "failed", ping=ping)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=10, help="mails to fetch")
    parser.add_argument("--dry-run", action="store_true", help="probe+fetch only")
    parser.add_argument("--out-dir", type=Path, default=None, help="receipt dir")
    args = parser.parse_args(argv)
    receipt = run(count=args.count, out_dir=args.out_dir, dry_run=args.dry_run)
    status = receipt["status"]
    print(f"WEEKLY_DIGEST_{status.upper()} {receipt.get('reason', '')}".rstrip())
    return {"mailed": 0, "skipped": 2}.get(status, 1)


if __name__ == "__main__":
    raise SystemExit(main())
