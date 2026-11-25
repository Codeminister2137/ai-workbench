"""Flip and verify dashboard supervision mode (owner decision fc87c472, option C).

Owner mail (terminal + digest) only flows when supervision is
"unattended", but nothing flipped it: windows ran attended and mail
stayed silent. The runbook flips at window start and restores at
closeout; `check` warns on any mismatch.

Two live configs exist: the main checkout's dashboard.json (supervisor
gates read it) and the serve worktree's dashboard.json (serve + drain
gates read it; missing means defaults, i.e. attended). Both must
agree; split-brain fails loudly.

Usage:
    python scripts/supervision.py set unattended|attended [--repo ROOT]
    python scripts/supervision.py check [--expect MODE] [--repo ROOT]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "workbench_dashboard"))

from dashboard_config import load_config, save_supervision  # noqa: E402

MODES = ("attended", "unattended")


def _dashboard_json(repo: Path) -> Path:
    return repo / "apps" / "workbench_dashboard" / "dashboard.json"


def _serve_worktree(repo: Path) -> Path | None:
    candidate = repo.parent / "ai-workbench-serve"
    return candidate if candidate.is_dir() else None


def _targets(repo: Path) -> list[tuple[str, Path]]:
    paths = [("main", _dashboard_json(repo))]
    serve = _serve_worktree(repo)
    if serve is not None:
        paths.append(("serve", serve / "apps" / "workbench_dashboard" / "dashboard.json"))
    return paths


def _read_mode(path: Path) -> str:
    if not path.exists():
        return "attended"  # load_config defaults on missing file
    return load_config(path).supervision


def cmd_set(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    mode: str = args.mode
    if mode not in MODES:
        print(f"error: mode must be one of {', '.join(MODES)}", file=sys.stderr)
        return 2
    touched: list[str] = []
    for label, path in _targets(repo):
        save_supervision(path, mode)
        if _read_mode(path) != mode:
            print(f"error: readback failed for {label} ({path})", file=sys.stderr)
            return 1
        touched.append(f"{label}={path}")
    print(f"supervision={mode} :: " + " ".join(touched))
    if _serve_worktree(repo) is None:
        print("warning: no serve worktree found; flipped main checkout only", file=sys.stderr)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    states = {label: _read_mode(path) for label, path in _targets(repo)}
    for label, mode in states.items():
        print(f"{label}: {mode}")
    values = set(states.values())
    if len(values) > 1:
        print("MISMATCH: main and serve supervision disagree", file=sys.stderr)
        return 1
    if args.expect is not None:
        if args.expect not in MODES:
            print(f"error: --expect must be one of {', '.join(MODES)}", file=sys.stderr)
            return 2
        actual = next(iter(values))
        if actual != args.expect:
            print(
                f"MISMATCH: supervision is {actual!r}, expected {args.expect!r}",
                file=sys.stderr,
            )
            return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Flip/verify dashboard supervision mode.")
    sub = parser.add_subparsers(dest="command", required=True)
    setter = sub.add_parser("set", help="Set supervision on main + serve configs.")
    setter.add_argument("mode", help="attended or unattended")
    setter.add_argument("--repo", default=str(ROOT))
    setter.set_defaults(func=cmd_set)
    checker = sub.add_parser("check", help="Report effective supervision; --expect enforces.")
    checker.add_argument("--expect", default=None)
    checker.add_argument("--repo", default=str(ROOT))
    checker.set_defaults(func=cmd_check)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
