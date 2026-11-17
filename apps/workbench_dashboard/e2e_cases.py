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


def _is_test_file(path: str) -> bool:
    """Test files never ground steps; fixtures cite routes they don't serve."""
    normalized = path.replace("\\", "/")
    name = normalized.rsplit("/", 1)[-1]
    return "/tests/" in f"/{normalized}" or name.startswith("test_")


def extract_diff_evidence(
    repo_root: str,
    base: str,
    head: str,
    files: Sequence[str],
    runner: Callable[..., bytes] | None = None,
) -> dict[str, dict[str, list[str]]]:
    """Per-file evidence: changed symbols, API routes, dashboard views.

    Parsed from added diff lines only, so renamed-but-untouched code
    cannot ground a step. Test files are excluded: a fixture string
    mentioning a route is not the route changing. Files with no
    evidence get no entry.
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
        if _is_test_file(current):
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
        # Site files carry no code symbols; the file list itself grounds steps.
        if any(entry.values()) or path.startswith("company-site/")
    }


def _view_label(view: str) -> str:
    return view.removeprefix("#/").strip("/").replace("/", " ").strip() or "home"


# API route prefix -> (tab label, tab hash). Verified against the app.js
# router; routes without a mapped tab cannot ground a UI step and fall
# back to owner pointers instead of an unactionable "trigger from the UI".
ROUTE_UI: tuple[tuple[str, str, str], ...] = (
    ("/api/e2e/", "E2E", "#/e2e"),
    ("/api/chat/", "Chat", "#/chat"),
    ("/api/inbox", "Inbox", "#/inbox"),
    ("/api/runs", "Runs", "#/runs"),
    ("/api/ideas", "Ideas", "#/ideas"),
    ("/api/backlog", "Backlog", "#/backlog"),
    ("/api/plans", "Plans", "#/plans"),
    ("/api/documents", "Documents", "#/documents"),
    ("/api/workflows", "Workflows", "#/workflows"),
    ("/api/projects", "Projects", "#/projects"),
    ("/api/meetings", "Meetings", "#/meetings"),
    ("/api/knowme", "KnowMe", "#/knowme"),
    ("/api/providers", "Providers", "#/providers"),
    ("/api/fleet", "Fleet", "#/fleet"),
    ("/api/spend", "Providers", "#/providers"),
    ("/api/invoices", "Invoices", "#/invoices"),
    ("/api/intake", "Intake", "#/intake"),
    ("/api/modules", "Modules", "#/modules"),
    ("/api/restrictions", "Restrictions", "#/restrictions"),
    ("/api/tasks/propose", "Schedule", "#/schedule"),
    ("/api/overview", "Home", "#/"),
)


def _route_ui(route: str) -> tuple[str, str] | None:
    for prefix, label, view_hash in ROUTE_UI:
        if route == prefix.rstrip("/") or route.startswith(prefix):
            return label, view_hash
    return None


def _dashboard_steps(evidence: dict[str, dict[str, list[str]]]) -> list[dict]:
    steps: list[dict] = []
    seen: set[str] = set()
    unmapped: list[str] = []
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
        symbols = ", ".join(sorted(set(evidence[path]["symbols"])))
        touched = f" (touched: {symbols})" if symbols else ""
        for route in evidence[path]["routes"]:
            key = f"route:{route}"
            if key in seen:
                continue
            seen.add(key)
            mapped = _route_ui(route)
            if mapped is None:
                unmapped.append(route)
                continue
            label, view_hash = mapped
            steps.append(
                {
                    "action": (
                        f"Open the {label} tab ({view_hash}) and exercise "
                        f"the changed control end to end{touched}"
                    ),
                    "expected": "Action completes; badges and counts update; no error toast.",
                    "grounded": True,
                }
            )
    if unmapped:
        steps.append(
            {
                "action": (
                    "Route(s) without a mapped UI surface: "
                    + ", ".join(sorted(set(unmapped)))
                    + " — pointers needed"
                ),
                "expected": "N/A: the owner names what to verify.",
                "grounded": False,
            }
        )
    # Note: _send_* symbols are API handlers, not views — views ground
    # only from #/... hashes, actions only from mapped /api/... routes.
    return steps


def _site_steps(evidence: dict[str, dict[str, list[str]]], subjects: Sequence[str]) -> list[dict]:
    subject = subjects[0] if subjects else "this change"
    steps: list[dict] = []
    for path in sorted(evidence):
        if path.endswith(".html"):
            steps.append(
                {
                    "action": f"Open {path} on the served company site and verify: {subject}.",
                    "expected": "Page renders per the change; layout, links, and form wiring intact.",
                    "grounded": True,
                }
            )
    assets = [path for path in sorted(evidence) if path.rsplit(".", 1)[-1] in {"css", "js"}]
    if assets:
        steps.append(
            {
                "action": (
                    f"Spot-check the PL index and one EN page ({', '.join(assets)} changed) "
                    f"and verify: {subject}."
                ),
                "expected": "Shared-asset change renders correctly in both languages; no broken layout.",
                "grounded": True,
            }
        )
    others = [
        path
        for path in sorted(evidence)
        if not path.endswith(".html") and path.rsplit(".", 1)[-1] not in {"css", "js"}
    ]
    if others:
        steps.append(
            {
                "action": (
                    f"Non-page site files changed ({', '.join(others)}) — pointers needed: "
                    "what verifies them?"
                ),
                "expected": "Owner pointers say how to check non-renderable files.",
                "grounded": False,
            }
        )
    if not steps:
        steps.append(
            {
                "action": "Site files changed but named no checkable surface — pointers needed.",
                "expected": "Owner pointers say what to verify.",
                "grounded": False,
            }
        )
    return steps


def _is_test_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return "/tests/" in normalized or normalized.split("/")[-1].startswith("test_")


def _command_steps(
    evidence: dict[str, dict[str, list[str]]], action_template: str, expected: str
) -> list[dict]:
    steps: list[dict] = []
    for path in sorted(evidence):
        for symbol in evidence[path]["symbols"]:
            if _is_test_path(path):
                action = (
                    f"Run `.venv/Scripts/python.exe -m pytest {path} -q` "
                    "(via pytest, never by executing the file directly)"
                )
                runnable = True
            else:
                action = action_template.format(symbol=symbol, path=path)
                runnable = False
            steps.append(
                {
                    "action": action,
                    "expected": expected,
                    "grounded": True,
                    "agent_runnable": runnable,
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
    elif area == "company-site":
        steps = _site_steps(evidence, subjects)
        return steps
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
