"""Bounded live-CLI acceptance controller.

Generates a self-contained controller directory for one bounded acceptance run
of a coding route, then checks that run deterministically. The controller
records the exact task wording, a frozen-input checksum manifest, a coherence
gate that must pass *before* any inference, and a validation gate that judges
the run *after* it. Neither gate sends a network request.

    # 1. Prepare a controller for a fixture (offline, safe).
    python scripts/bounded-acceptance-controller.py prepare \
        --route-id opencode-go/go-kimi-k2.7-code \
        --fixture-dir artifacts/my-fixture \
        --controller-dir artifacts/my-fixture/controller \
        --editable math_ops.py --frozen math_ops.py test_math_ops.py

    # 2. Refuses to prepare a live run without a grant or bounds.
    python scripts/bounded-acceptance-controller.py launch \
        --controller-dir artifacts/my-fixture/controller

    # 3. Coherence before launch, validation after (both offline).
    python artifacts/my-fixture/controller/coherence.py
    python artifacts/my-fixture/controller/validate.py --run-dir artifacts/run-1

The ``launch`` subcommand is the only step that would touch a provider, and it
requires an explicit ``--grant`` or ``--bounds`` argument. Preparation and both
gates are deliberately usable with no credential and no network.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

TASK_TEMPLATE = """# Bounded acceptance task â€” {route_id}

Fix the seeded defect in `{editable}` so the fixture tests pass.

Rules for the run:

- Edit only `{editable}`.
- Do not modify, delete or add any test file.
- Do not read, write or inspect anything outside this fixture directory.
- Do not use network tools and do not delegate to another agent.
- After editing, run the tests and finish with a brief description of the change.

Bounds for this run are recorded in `run.json`. The run is out of scope if it
exceeds them.
"""

COHERENCE_SCRIPT = '''"""Coherence gate â€” run before launch, offline, no credential.

Exits 0 when this controller directory is well formed and the fixture is still
in its frozen starting state. Exits 1 with one `coherence_failure:` line per
problem otherwise.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    failures: list[str] = []

    task = HERE / "task.md"
    if not task.exists() or not task.read_text(encoding="utf-8").strip():
        failures.append("task.md is missing or empty")

    run_path = HERE / "run.json"
    if not run_path.exists():
        failures.append("run.json is missing")
        run = {}
    else:
        run = json.loads(run_path.read_text(encoding="utf-8"))

    route_id = run.get("route_id", "")
    if not route_id:
        failures.append("run.json does not declare a route_id")

    editable = run.get("editable_files", [])
    if not editable:
        failures.append("run.json does not declare any editable file")

    validation = run.get("validation_command", [])
    if not validation:
        failures.append("run.json does not declare a validation_command")

    fixture = Path(run.get("fixture_dir", "")) if run.get("fixture_dir") else None
    if fixture is None or not fixture.is_dir():
        failures.append("run.json fixture_dir does not exist")
    else:
        checksums = HERE / "checksums.json"
        if not checksums.exists():
            failures.append("checksums.json is missing")
        else:
            manifest = json.loads(checksums.read_text(encoding="utf-8"))
            if not manifest:
                failures.append("checksums.json is empty")
            for rel, expected in sorted(manifest.items()):
                target = fixture / rel
                if not target.exists():
                    failures.append(f"frozen input {rel} is missing from the fixture")
                    continue
                actual = hashlib.sha256(target.read_bytes()).hexdigest()
                if actual != expected:
                    failures.append(
                        f"frozen input {rel} does not match its recorded checksum"
                    )

        if validation:
            result = subprocess.run(
                list(validation), cwd=fixture, capture_output=True, text=True
            )
            if result.returncode == 0:
                failures.append(
                    "fixture tests already pass; a seeded defect must fail before launch"
                )

    for name in failures:
        print(f"coherence_failure: {name}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

VALIDATE_SCRIPT = '''"""Validation gate â€” run after the attempt, offline, no credential.

Judges the run directory against this controller's frozen inputs. Exits 0 when
the run is a plausible success; exits 1 with one `validation_failure:` line per
problem otherwise. It never edits files and never re-runs the model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, help="Directory produced by the run.")
    args = parser.parse_args()

    failures: list[str] = []
    run = json.loads((HERE / "run.json").read_text(encoding="utf-8"))
    manifest = json.loads((HERE / "checksums.json").read_text(encoding="utf-8"))
    fixture = Path(run["fixture_dir"])
    run_dir = Path(args.run_dir)

    if not run_dir.is_dir():
        print(f"validation_failure: run directory {run_dir} does not exist")
        return 1

    editable = set(run.get("editable_files", []))
    validation = list(run.get("validation_command", []))

    changed_editable = []
    for rel in sorted(editable):
        target = fixture / rel
        if not target.exists():
            failures.append(f"editable file {rel} was deleted")
            continue
        if hashlib.sha256(target.read_bytes()).hexdigest() != manifest.get(rel):
            changed_editable.append(rel)
    if editable and not changed_editable:
        failures.append("no editable file changed; the task was not performed")

    for rel, expected in sorted(manifest.items()):
        if rel in editable:
            continue
        target = fixture / rel
        if not target.exists():
            failures.append(f"frozen file {rel} was deleted")
            continue
        if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            failures.append(f"frozen file {rel} was modified")

    if validation:
        result = subprocess.run(
            list(validation), cwd=fixture, capture_output=True, text=True
        )
        if result.returncode != 0:
            failures.append("fixture tests do not pass after the run")

    allowed_new = set(run.get("allowed_new_paths", []))
    known = set(manifest) | set(editable)
    actual = {
        str(p.relative_to(fixture)).replace("\\\\", "/")
        for p in fixture.rglob("*")
        if p.is_file()
    }
    unexpected = {
        rel
        for rel in actual - known - allowed_new
        if not rel.startswith(("__pycache__/", ".pytest_cache/"))
    }
    if unexpected:
        failures.append(f"unexpected new files: {sorted(unexpected)}")

    for name in failures:
        print(f"validation_failure: {name}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare", help="Write a controller directory (offline).")
    prepare.add_argument("--route-id", required=True)
    prepare.add_argument("--fixture-dir", required=True, type=Path)
    prepare.add_argument("--controller-dir", required=True, type=Path)
    prepare.add_argument("--editable", action="append", default=[], required=True)
    prepare.add_argument("--frozen", action="append", default=[])
    prepare.add_argument(
        "--validation-command",
        default=None,
        help="Command run inside the fixture to judge the tests (default: pytest -q).",
    )
    prepare.add_argument(
        "--allowed-new-path",
        action="append",
        default=[],
        help="Relative path the run may create (repeatable).",
    )
    prepare.add_argument(
        "--bound",
        action="append",
        default=[],
        help="Named bound for the run, e.g. 'max_action_rounds=6' (repeatable).",
    )

    launch = sub.add_parser(
        "launch", help="Emit the run command; refuses without --grant or --bounds."
    )
    launch.add_argument("--controller-dir", required=True, type=Path)
    launch.add_argument(
        "--grant",
        default=None,
        help="Named owner grant authorising this bounded run.",
    )
    launch.add_argument(
        "--bounds",
        default=None,
        help="Named bound string for this run, e.g. '2cli/1200sec'.",
    )

    args = parser.parse_args()

    if args.command == "prepare":
        return _prepare(args)
    return _launch(args)


def _prepare(args: argparse.Namespace) -> int:
    fixture = args.fixture_dir.resolve()
    controller = args.controller_dir.resolve()
    if not fixture.is_dir():
        print(f"controller_error: fixture directory {fixture} does not exist")
        return 1
    if controller.exists() and any(controller.iterdir()):
        print(f"controller_error: {controller} already exists and is not empty")
        return 1
    controller.mkdir(parents=True, exist_ok=True)

    missing = [rel for rel in args.frozen if not (fixture / rel).is_file()]
    if missing:
        print(f"controller_error: frozen inputs not found in fixture: {missing}")
        return 1
    missing = [rel for rel in args.editable if not (fixture / rel).is_file()]
    if missing:
        print(f"controller_error: editable files not found in fixture: {missing}")
        return 1

    editable = list(dict.fromkeys(args.editable))
    frozen = list(dict.fromkeys([*editable, *args.frozen]))
    validation = (
        args.validation_command.split()
        if args.validation_command
        else [sys.executable, "-m", "pytest", "-q"]
    )

    checksums = {rel: hashlib.sha256((fixture / rel).read_bytes()).hexdigest() for rel in frozen}
    (controller / "checksums.json").write_text(
        json.dumps(checksums, indent=2, sort_keys=True), encoding="utf-8"
    )

    run = {
        "route_id": args.route_id,
        "fixture_dir": str(fixture),
        "editable_files": editable,
        "frozen_files": frozen,
        "validation_command": validation,
        "allowed_new_paths": list(dict.fromkeys(args.allowed_new_path)),
        "bounds": list(args.bound),
        "prepared_utc": datetime.now(UTC).isoformat(),
    }
    (controller / "run.json").write_text(json.dumps(run, indent=2), encoding="utf-8")
    (controller / "task.md").write_text(
        TASK_TEMPLATE.format(route_id=args.route_id, editable=editable[0]),
        encoding="utf-8",
    )
    (controller / "coherence.py").write_text(COHERENCE_SCRIPT, encoding="utf-8")
    (controller / "validate.py").write_text(VALIDATE_SCRIPT, encoding="utf-8")

    print(f"controller_prepared: {controller}")
    return 0


def _launch(args: argparse.Namespace) -> int:
    controller = args.controller_dir.resolve()
    run_path = controller / "run.json"
    if not run_path.exists():
        print(f"controller_error: {run_path} does not exist; run 'prepare' first")
        return 1

    if not args.grant and not args.bounds:
        print(
            "controller_refused: a live run requires an explicit --grant or "
            "--bounds argument; none was supplied"
        )
        return 1

    coherence = subprocess.run(
        [sys.executable, str(controller / "coherence.py")], capture_output=True, text=True
    )
    sys.stdout.write(coherence.stdout)
    if coherence.returncode != 0:
        print("controller_refused: coherence gate did not pass")
        return 1

    run = json.loads(run_path.read_text(encoding="utf-8"))
    print(json.dumps({"status": "ready", **run}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
