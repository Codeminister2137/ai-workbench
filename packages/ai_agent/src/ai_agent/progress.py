"""Human progress narration over agent telemetry events.

``narrate`` translates ``key: detail`` telemetry lines into one-line
narrations for owners; unknown lines pass through untouched so nothing is
ever dropped or hidden (failures keep their details). ``reporter`` builds
the print sink: verbose mode prints raw telemetry, default mode narrates.
"""

from __future__ import annotations

import re
from collections.abc import Callable

_PRETTY = {
    "local_agent_activity": "Agent",
    "local_tool_activity": "Tool",
    "delegated_agent_activity": "Subagent",
    "scrutiny_activity": "Scrutiny",
    "repair_activity": "Repair",
    "auxiliary_panel_activity": "Auxiliary panel",
}


def _pretty(prefix: str) -> str:
    return _PRETTY.get(prefix, prefix)


_RULES: tuple[tuple[re.Pattern[str], Callable[[re.Match[str]], str]], ...] = (
    (
        re.compile(r"^local_agent_activity: model_request - provider=(\S+) model=(\S+)"),
        lambda m: f"Asking {m.group(2)} ({m.group(1)})…",
    ),
    (
        re.compile(r"^local_agent_activity: ollama_start\b"),
        lambda m: "Starting local Ollama…",
    ),
    (
        re.compile(r"^local_agent_activity: failed - (.+)"),
        lambda m: f"Agent run failed — {m.group(1)}",
    ),
    (
        re.compile(
            r"^local_agent_activity: (\S+) - iterations=(\d+) tool_results=(\d+) usage=(.+)"
        ),
        lambda m: (
            f"Finished ({m.group(1)}): {m.group(2)} iterations, "
            f"{m.group(3)} tool results ({m.group(4)})"
        ),
    ),
    (
        re.compile(r"^local_tool_activity: recorded - ([^:]+): (.+)"),
        lambda m: f"Tool {m.group(1)}: {m.group(2)}",
    ),
    (
        re.compile(r"^local_tool_activity: (\S+) - ([^:]+): (.+)"),
        lambda m: f"Tool {m.group(2)} ({m.group(1)}): {m.group(3)}",
    ),
    (
        re.compile(r"^delegated_agent_activity: started - (.+)"),
        lambda m: f"Delegating subtask: {m.group(1)}",
    ),
    (
        re.compile(r"^delegated_agent_activity: model_request - route=(\S+) model=(\S+)"),
        lambda m: f"Subagent asking {m.group(2)} ({m.group(1)})…",
    ),
    (
        re.compile(r"^delegated_agent_activity: completed - iterations=(\d+) tool_results=(\d+)"),
        lambda m: f"Subagent done: {m.group(1)} iterations, {m.group(2)} tool results",
    ),
    (
        re.compile(r"^delegated_agent_activity: failed - kind=(\S+) detail=(.+)"),
        lambda m: f"Subagent failed ({m.group(1)}): {m.group(2)}",
    ),
    (
        re.compile(r"^model_output_errors: (\d+)"),
        lambda m: f"Model output errors so far: {m.group(1)}",
    ),
    (
        re.compile(r"^completion_failures: (\d+)"),
        lambda m: f"Completion failures so far: {m.group(1)}",
    ),
    (
        re.compile(r"^delegation_fanout: n=(\d+) workers=(.+)"),
        lambda m: f"Fanning out to {m.group(1)} workers ({m.group(2)})…",
    ),
    (
        re.compile(r"^loop_compaction: "),
        lambda m: "Compacting transcript…",
    ),
    (
        re.compile(r"^model_output_error: "),
        lambda m: "Model output error — attempting recovery",
    ),
    (
        re.compile(
            r"^(model_output_recovery|completion_recovery|groundedness_recovery): errors=(\d+) action=(\S+)"
        ),
        lambda m: f"Recovery ({m.group(2)} errors): {m.group(3)}",
    ),
    (
        re.compile(r"^completion_check: missing=(.+)"),
        lambda m: f"Completion check: still missing {m.group(1)}",
    ),
    (
        re.compile(r"^groundedness_check: unsupported=(.+)"),
        lambda m: f"Groundedness check: unsupported {m.group(1)}",
    ),
    (
        re.compile(r"^fallback_history: (.+)"),
        lambda m: f"Fallback: {m.group(1)}",
    ),
    (
        re.compile(r"^context_budget_omitted: (.+)"),
        lambda m: f"Context: omitted {m.group(1)} (over budget)",
    ),
    (
        re.compile(r"^context_file_truncated: (\S+)"),
        lambda m: f"Context: truncated {m.group(1)}",
    ),
    (
        re.compile(r"^([a-z_]+_activity): failed - (.+)"),
        lambda m: f"{_pretty(m.group(1))} failed: {m.group(2)}",
    ),
    (
        re.compile(r"^([a-z_]+_activity): (\S+) - (.+)"),
        lambda m: f"{_pretty(m.group(1))} {m.group(2)}: {m.group(3)}",
    ),
)


def narrate(line: str) -> str:
    """Translate one telemetry line; unknown lines pass through unchanged."""
    for pattern, render in _RULES:
        match = pattern.search(line)
        if match:
            try:
                return render(match)
            except (IndexError, ValueError):
                return line
    return line


def reporter(*, verbose: bool) -> Callable[[str], None]:
    """Print sink: raw telemetry when verbose, narration otherwise."""
    if verbose:
        return print
    return lambda line: print(narrate(line))
