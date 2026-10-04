"""Private fixed-harness worker; execution authority comes from its owning host."""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

from ai_provider.acceptance_harness import run_fixture
from ai_provider.acceptance_jobs import AcceptanceJob, validate_route
from ai_provider.acceptance_processes import remaining, verify_runtime_owner


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--definition", type=Path, required=True)
    parser.add_argument("--runtime-receipt", type=Path, required=True)
    parser.add_argument("--start-receipt", type=Path, required=True)
    parser.add_argument("--deadline", type=float, required=True)
    args = parser.parse_args()
    if not math.isfinite(args.deadline):
        parser.error("A finite monotonic deadline is required")
    remaining(args.deadline)
    job = AcceptanceJob.from_json(args.definition.read_text(encoding="utf-8"))
    validate_route(job)
    identity = json.loads(args.runtime_receipt.read_text(encoding="utf-8"))
    # The host releases this gate only after assigning the worker to its OS job
    # and saving the worker ownership receipt. Imports alone cannot start work.
    while not args.start_receipt.is_file():
        remaining(args.deadline)
        time.sleep(0.02)
    artifact = args.definition.parent
    result = run_fixture(
        job,
        artifact,
        args.deadline,
        lambda timeout: verify_runtime_owner(job.runtime_base_url, identity, timeout=timeout),
    )
    with (artifact / "worker-result.json").open("x", encoding="utf-8") as output:
        json.dump(result, output, allow_nan=False)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
