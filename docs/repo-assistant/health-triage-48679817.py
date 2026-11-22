"""Snapshot a finite reviewed handler sample and synthetic ambiguity probe."""

from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

root = Path.cwd()
out = root / ".tmp/health-48679817"
reviewed = [
    (
        "apps/ai_council/evals/run_synthesis_eval.py",
        "main",
        "Diagnostic ambiguity: unreadable and malformed baseline both say no baseline; nonzero exit prevents false passing evaluation.",
    ),
    (
        "apps/ai_council/investor/judge.py",
        "parse_weights",
        "Documented junk-line filter; not evidence of missing configuration. Empty mapping semantics delegated to caller.",
    ),
    (
        "apps/ai_council/web_app.py",
        "abort_read",
        "Best-effort socket cleanup; expired event is set before shutdown, reader reports 408.",
    ),
    (
        "apps/job_search/job-email/models.py",
        "is_approved_for_sending",
        "Intentional fail-closed boolean authorization check; attachment read failure cannot authorize sending.",
    ),
    (
        "apps/job_search/job-email/openings_api.py",
        "expire",
        "Best-effort watchdog shutdown; enclosing request owns timeout failure. No absence assertion.",
    ),
    (
        "apps/job_search/job-email/outreach_cli.py",
        "run_outreach",
        "Explicit user diagnostics and failure exits/flags; delivery ledger failures stop to prevent duplicate sends. Cancellation breaks review intentionally.",
    ),
    (
        "packages/ai_provider/src/ai_provider/secrets.py",
        "load_dotenv",
        "Convenience loader deliberately returns empty on missing/unreadable; unsafe as presence evidence. Inspect callers separately.",
    ),
    (
        "packages/ai_provider/src/ai_provider/secrets.py",
        "dotenv_names",
        "Names-only helper folds read errors; secret_status is necessary to distinguish empty from unreadable.",
    ),
    (
        "packages/ai_provider/src/ai_provider/secrets.py",
        "read_dotenv_values",
        "Confirmed API ambiguity: missing=raise only raises on missing-file; unreadable still returns empty. Not a presence-verdict API.",
    ),
    (
        "packages/ai_provider/src/ai_provider/secrets.py",
        "secret_status",
        "Explicit missing-file versus unreadable outcomes; retain distinct verdicts.",
    ),
    (
        "packages/ai_provider/src/ai_provider/secrets.py",
        "read_secret_key",
        "Raises labelled cause-specific errors; no folded absence result.",
    ),
]
records = []
for relative, name, assessment in reviewed:
    path = root / relative
    raw = path.read_bytes()
    tree = ast.parse(raw)
    functions = [
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    ]
    assert len(functions) == 1, (relative, name)
    for handler in ast.walk(functions[0]):
        if isinstance(handler, ast.ExceptHandler):
            records.append(
                {
                    "file": relative,
                    "function": name,
                    "line": handler.lineno,
                    "source_sha256": hashlib.sha256(raw).hexdigest(),
                    "handler": ast.unparse(handler),
                    "assessment": assessment,
                }
            )
with (out / "handler-triage.json").open("x", encoding="utf-8") as stream:
    json.dump(
        {
            "bounds": "11 named functions; all their lexical handlers; no live credentials or inference",
            "handlers": records,
            "not_exhaustive": True,
        },
        stream,
        indent=2,
    )
sys.path.insert(0, str(root / "packages/ai_provider/src"))
from ai_provider.secrets import read_dotenv_values, secret_status  # noqa: E402

synthetic = out / "synthetic-unreadable.env"
original = Path.read_text


def denied(path, *args, **kwargs):
    if path == synthetic:
        raise PermissionError("synthetic test denial")
    return original(path, *args, **kwargs)


with patch.object(Path, "read_text", denied):
    values = read_dotenv_values(synthetic, {"SYNTHETIC_KEY"}, missing="raise")
    verdict = secret_status(synthetic, "SYNTHETIC_KEY")
    assert values == {} and verdict.reason == "unreadable"
with (out / "synthetic-handler-probe.json").open("x", encoding="utf-8") as stream:
    json.dump(
        {
            "read_dotenv_values_missing_raise": values,
            "secret_status_reason": verdict.reason,
            "scope": "Mocked synthetic path only; no actual credential-store observation",
            "caller_review": "loop_notify.read_gmail_config consumes empty mapping and may return None; alternate-agent-acceptance.load_dotenv_secrets only catches missing-file. Fixes excluded from this slice.",
        },
        stream,
        indent=2,
    )
print(f"Reviewed {len(records)} handlers; synthetic ambiguity confirmed")
