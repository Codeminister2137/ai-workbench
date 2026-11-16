"""Case-specific E2E steps grounded in the merge diff.

Manual-testing convention (ISTQB glossary, ISO/IEC/IEEE 29119): a test
case is preconditions plus numbered steps, each step one action with an
observable expected result, plus pass/fail and traceability to the
change. Area-level "how to test" prose told the tester nothing
concrete, so each behavior item now carries authored ``steps``:
``[{action, expected}]``. Affected files stay on the item as the
record, but the checklist itself is checkable steps.

Grounding: evidence (changed symbols, API routes, dashboard views) is
extracted deterministically from the diff, and steps cite it. Steps
that cannot cite evidence are flagged ``needs_pointers``: the task
stays a draft and the owner is asked what to verify, because a vague
scheduled test the owner must send back costs more than a question.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence

_SYMBOL_RE = re.compile(r"^\+\s*(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)")
_ROUTE_RE = re.compile(r"/api/[A-Za-z0-9_\-/]+")
_VIEW_RE = re.compile(r"#/[A-Za-z0-9/_-]+")


def extract_diff_evidence(
    repo_root: str,
    base: str,
    head: str,
    files: Sequence[str],
    runner: Callable[..., bytes] | None = None,
) -> dict[str, dict[str, list[str]]]:
    """Per-file evidence: changed symbols, API routes, dashboard views.

    Parsed from added diff lines only, so renamed-but-untouched code
    cannot ground a step. Files with no evidence get no entry.
    """
    from e2e_promotion import run_git

    run = runner or run_git
    if not files:
        return {}
    raw = run(repo_root, "diff", f"{base}...{head}", "--", *files)
    evidence: dict[str, dict[str, set[str]]] = {}
    current: str | None = None
    for line in raw.decode("utf-8", "replace").splitlines():
        if line.startswith("+++ b/"):
            current = line[len("+++ b/") :].strip()
            continue
        if current is None or not line.startswith("+") or line.startswith("+++"):
            continue
        entry = evidence.setdefault(current, {"symbols": set(), "routes": set(), "views": set()})
        symbol = _SYMBOL_RE.match(line)
        if symbol:
            entry["symbols"].add(symbol.group(1))
        for route in _ROUTE_RE.findall(line):
            entry["routes"].add(route.rstrip("/"))
        for view in _VIEW_RE.findall(line):
            entry["views"].add(view)
    return {
        path: {key: sorted(values) for key, values in entry.items()}
        for path, entry in sorted(evidence.items())
        if any(entry.values())
    }


def _view_label(view: str) -> str:
    return view.removeprefix("#/").strip("/").replace("/", " ").strip() or "home"


def _dashboard_steps(evidence: dict[str, dict[str, list[str]]]) -> list[dict]:
    steps: list[dict] = []
    seen: set[str] = set()
    for path in sorted(evidence):
        for view in evidence[path]["views"]:
            if view.strip("#/").count("/") > 0:
                continue  # nested hashes need an id; not an openable view
            key = f"view:{view}"
            if key in seen:
                continue
            seen.add(key)
            steps.append(
                {
                    "action": f"Open the {_view_label(view)} view ({view})",
                    "expected": "View renders current data with no error toast.",
                    "grounded": True,
                }
            )
        for route in evidence[path]["routes"]:
            key = f"route:{route}"
            if key in seen:
                continue
            seen.add(key)
            steps.append(
                {
                    "action": f"Trigger the action served by {route} from the UI",
                    "expected": "Action completes; badges and counts update; no error toast.",
                    "grounded": True,
                }
            )
    # Note: _send_* symbols are API handlers, not views — views ground
    # only from #/... hashes, actions only from /api/... routes. A .py-only
    # dashboard diff therefore falls through to the pointer fallback below.
    return steps


def _command_steps(
    evidence: dict[str, dict[str, list[str]]], action_template: str, expected: str
) -> list[dict]:
    steps: list[dict] = []
    for path in sorted(evidence):
        for symbol in evidence[path]["symbols"]:
            steps.append(
                {
                    "action": action_template.format(symbol=symbol, path=path),
                    "expected": expected,
                    "grounded": True,
                }
            )
    return steps


def draft_steps(
    area: str,
    evidence: dict[str, dict[str, list[str]]],
    subjects: Sequence[str],
) -> list[dict]:
    """Draft checkable steps for one behavior item.

    Grounded steps cite diff evidence; when the diff yields nothing the
    generator can point at, the fallback step says so honestly and the
    item needs owner pointers instead of a vague scheduled test.
    """
    # Silence unused-argument lint: subjects feed the item record, steps cite files.
    _ = subjects
    if area == "dashboard":
        steps = _dashboard_steps(evidence)
    elif area == "agent-cli":
        steps = _command_steps(
            evidence,
            "Exercise the changed path {symbol} ({path}) through its documented caller, then run the scoped pytest",
            "Behaves as before; no traceback; no unintended writes.",
        )
    elif area == "provider":
        steps = _command_steps(
            evidence,
            "Run the scoped pytest for the touched adapter, then one real local request through {symbol} and read the route line",
            "Correct route chosen, response complete, usage recorded.",
        )
    elif area == "orchestrator":
        steps = _command_steps(
            evidence,
            "Run the scoped pytest for the touched module, trigger one decision through {symbol}, read the reasoning",
            "Sensible decision with visible reasoning; no gate bypass.",
        )
    else:
        steps = [
            {
                "action": (
                    f"Exercise the changed {area} behavior end to end "
                    "(no UI hook found in the diff — pointers needed)"
                ),
                "expected": "Behavior works as before with no errors.",
                "grounded": False,
            }
        ]
        return steps
    if not steps:
        seen = sorted({s for entry in evidence.values() for s in entry["symbols"]})
        detail = (
            f"changed: {', '.join(seen)} — but no route or view to point at"
            if seen
            else "no symbol, route, or view found in the diff"
        )
        steps = [
            {
                "action": (
                    "Exercise the changed code path from its nearest user surface "
                    f"({detail}; pointers needed)"
                ),
                "expected": "Behaves as before with no errors.",
                "grounded": False,
            }
        ]
    return steps


def regression_steps(area: str) -> list[dict]:
    """Standing regression checks for an untouched neighbor area.

    These re-run the area's standard checks rather than guessing at
    this diff, so they are grounded by definition and need no pointers.
    """
    from e2e_promotion import REGRESSION_LEAD, TEST_GUIDANCE

    how, expected, _where = TEST_GUIDANCE.get(area, ([], "", ""))
    return [
        {
            "action": step,
            "expected": expected or "Behaves as before with no errors.",
            "grounded": True,
        }
        for step in [REGRESSION_LEAD, *how]
    ]


def needs_pointers(steps: Sequence[dict]) -> bool:
    """True when any step admits it could not ground itself in the diff."""
    return not steps or any(not step.get("grounded", True) for step in steps)


def validate_steps(steps: object) -> list[dict]:
    """Normalize finalized steps; agent-authored steps are understood."""
    if not isinstance(steps, list) or not steps:
        raise ValueError("Steps must be a non-empty list")
    normalized: list[dict] = []
    for step in steps:
        if not isinstance(step, dict):
            raise ValueError("Each step must be an object")
        action = str(step.get("action", "")).strip()
        expected = str(step.get("expected", "")).strip()
        if not action or not expected:
            raise ValueError("Each step needs a non-blank action and expected result")
        normalized.append({"action": action, "expected": expected, "grounded": True})
    return normalized
