"""Source-checkout entry point for the reusable offline report verifier."""

import argparse
import hashlib
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
for _NAME in ("ai_agent", "ai_provider", "ai_orchestrator"):
    sys.path.insert(0, str(_ROOT / "packages" / _NAME / "src"))

from ai_agent.research_reports import (  # noqa: E402, F401
    REQUIRED_SECTIONS,
    has_report_write_receipt,
    validate_report,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a disposable local research report.")
    parser.add_argument("path", type=Path)
    parser.add_argument(
        "--min-chars", type=int, default=7000, help="Advisory length guideline, not a failure gate"
    )
    parser.add_argument(
        "--run-db", type=Path, help="Existing local run database for receipt checks"
    )
    parser.add_argument("--run-id", help="Current research run ID (requires --run-db)")
    args = parser.parse_args(argv)
    if args.min_chars <= 0:
        parser.error("--min-chars must be greater than zero")
    if bool(args.run_db) != bool(args.run_id):
        parser.error("--run-db and --run-id must be supplied together")
    try:
        text = args.path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        print(f"missing research file: {args.path}", file=sys.stderr)
        return 1
    except (OSError, UnicodeError) as error:
        print(f"cannot read research file: {args.path}: {error}", file=sys.stderr)
        return 1
    receipts = None
    if args.run_db:
        try:
            from ai_provider.orchestrated_runs import SQLiteOrchestratedRunStore

            if not args.run_db.is_file():
                raise ValueError("run database does not exist")
            store = SQLiteOrchestratedRunStore(args.run_db)
            run = store.get_run(args.run_id)
            if run is None:
                raise ValueError("run ID does not exist")
            stage = next(s for s in store.list_stages(args.run_id) if s.name == "implementation")
            receipts = (stage.details or {}).get("fetch_receipts", [])
            writes = (stage.details or {}).get("report_receipts", [])
            relocations = (stage.details or {}).get("report_relocations", [])
            if not isinstance(receipts, list) or not all(isinstance(r, dict) for r in receipts):
                raise ValueError("invalid fetch receipt metadata")
            digest = hashlib.sha256(args.path.read_bytes()).hexdigest()
            if not isinstance(writes, list) or not all(isinstance(w, dict) for w in writes):
                raise ValueError("invalid report receipt metadata")
            if not isinstance(relocations, list) or not all(
                isinstance(r, dict) for r in relocations
            ):
                raise ValueError("invalid report relocation metadata")
            if not has_report_write_receipt(str(args.path.resolve()), digest, writes, relocations):
                raise ValueError("report has no matching current-run write receipt")
        except (ValueError, OSError, StopIteration, sqlite3.Error) as error:
            print(f"cannot verify research receipts: {error}", file=sys.stderr)
            return 1
    advisories: list[str] = []
    errors = validate_report(
        text, min_chars=args.min_chars, fetch_receipts=receipts, advisories=advisories
    )
    for advisory in advisories:
        print(advisory, file=sys.stderr)
    if errors:
        print("research report validation failed:\n- " + "\n- ".join(errors), file=sys.stderr)
        return 1
    scope = (
        "current-run retrieval receipts checked; factual truth not verified"
        if receipts is not None
        else "source retrieval/truth not verified"
    )
    print(f"research report structure validated: {args.path}; {scope}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
