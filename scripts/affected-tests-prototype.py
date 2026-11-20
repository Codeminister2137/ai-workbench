"""Print shadow-only group selection; never execute or replace the merge gate.

Unknown paths and shared infrastructure fall back to the full offline suite.
GROUPS describe ownership, not a complete dependency graph: recommendations
remain experimental even when historical recall is perfect.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_suites():
    spec = importlib.util.spec_from_file_location("test_suites", ROOT / "scripts/run-tests.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def select_groups(paths: list[str], groups: dict[str, tuple[str, ...]]) -> dict:
    """Keep cross-component workspace consumers; fail open to full testing."""
    offline = set(groups) - {"live"}
    workspace = offline - {"council", "job-search"}
    selected: set[str] = set()
    reasons = []
    owners = {path: name for name, files in groups.items() for path in files}
    for path in paths:
        path = path.replace("\\", "/")
        if path in owners and owners[path] != "live":
            affected = {owners[path]}
            reason = "test module ownership"
        elif Path(path).name.startswith("test_") and path.endswith(".py"):
            affected = offline
            reason = "unowned/deleted test module: full fallback"
        elif path.startswith("apps/ai_council/"):
            affected = workspace | {"council"}
            reason = "Council plus workspace consumers"
        elif path.startswith("apps/job_search/"):
            affected = workspace | {"job-search"}
            reason = "job-search plus workspace consumers"
        elif path.startswith(("packages/ai_agent/", "apps/workbench_dashboard/")):
            affected = workspace
            reason = "agent/dashboard plus all workspace consumers"
        else:
            affected = offline
            reason = "unknown/shared/deleted path: full fallback"
        selected |= affected
        reasons.append({"path": path, "reason": reason})
    return {"shadow_only": True, "groups": sorted(selected), "reasons": reasons}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="compare base to HEAD (both rename paths)")
    args = parser.parse_args()
    result = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", "-z", args.base, "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    paths = [path for path in result.stdout.decode("utf-8").split("\0") if path]
    print(json.dumps(select_groups(paths, load_suites().suite_files()), indent=2))


if __name__ == "__main__":
    main()
