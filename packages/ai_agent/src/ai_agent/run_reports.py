"""Deterministic markdown reports for file-backed runs.

Owner automation (zero tokens): renders a run record plus its last receipt
into stable markdown. Defensive by design -- missing or wrong-typed keys
render as ``(none)`` or are skipped, and rendering never raises.

Two flavors (report B): ``full`` keeps everything; ``shareable`` drops
iterations, tool calls, owner-task ids, and error details.
"""

from __future__ import annotations


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _first_text(run: dict, keys: tuple[str, ...]) -> str | None:
    for key in keys:
        try:
            value = run.get(key)
        except AttributeError:
            return None
        text = _text(value)
        if text is not None:
            return text
    return None


def _last_receipt(run: dict) -> dict | None:
    try:
        receipts = run.get("receipts")
    except AttributeError:
        return None
    if not isinstance(receipts, list):
        return None
    for entry in reversed(receipts):
        if isinstance(entry, dict):
            return entry
    return None


def _tool_names(receipt: dict | None) -> list[str] | None:
    if not isinstance(receipt, dict):
        return None
    calls = receipt.get("tool_calls")
    if not isinstance(calls, list) or not calls:
        return None
    names: list[str] = []
    for entry in calls:
        if isinstance(entry, str):
            text = _text(entry)
            if text is not None:
                names.append(text)
        elif isinstance(entry, dict):
            for key in ("tool", "name", "function", "tool_name"):
                try:
                    candidate = entry.get(key)
                except AttributeError:
                    continue
                text = _text(candidate)
                if text is not None:
                    names.append(text)
                    break
    return names or None


def _staged_paths(run: dict) -> list[str] | None:
    try:
        staged = run.get("staged")
    except AttributeError:
        return None
    if not isinstance(staged, list) or not staged:
        return None
    paths: list[str] = []
    for entry in staged:
        if isinstance(entry, str):
            text = _text(entry)
            if text is not None:
                paths.append(text)
        elif isinstance(entry, dict):
            for key in ("relpath", "path", "file"):
                try:
                    candidate = entry.get(key)
                except AttributeError:
                    continue
                text = _text(candidate)
                if text is not None:
                    paths.append(text)
                    break
    return paths or None


def _owner_task_ids(receipt: dict | None) -> list[str] | None:
    if not isinstance(receipt, dict):
        return None
    tasks = receipt.get("owner_tasks")
    if not isinstance(tasks, list) or not tasks:
        return None
    ids: list[str] = []
    for entry in tasks:
        if isinstance(entry, str):
            text = _text(entry)
            if text is not None:
                ids.append(text)
        elif isinstance(entry, dict):
            try:
                candidate = entry.get("id")
            except AttributeError:
                continue
            if isinstance(candidate, str):
                text = _text(candidate)
                if text is not None:
                    ids.append(text)
            elif isinstance(candidate, int) and not isinstance(candidate, bool):
                ids.append(str(candidate))
        elif isinstance(entry, int) and not isinstance(entry, bool):
            ids.append(str(entry))
    return ids or None


def _run_id(run: dict) -> str:
    try:
        raw_id = run.get("id")
    except AttributeError:
        raw_id = None
    if isinstance(raw_id, str):
        return _text(raw_id) or "unknown"
    if isinstance(raw_id, int) and not isinstance(raw_id, bool):
        return str(raw_id)
    return "unknown"


def _receipt_summary(receipt: dict | None) -> str | None:
    if not isinstance(receipt, dict):
        return None
    return _text(receipt.get("summary"))


def render_run_report(run: dict) -> str:
    """Render a deterministic markdown report for ``run``; never raises."""
    try:
        if not isinstance(run, dict):
            run = {}
        title = _first_text(run, ("title",)) or "untitled"
        run_id = _run_id(run)
        status = _first_text(run, ("status",)) or "(none)"
        started = _first_text(run, ("started_at_utc", "started_at", "created_at_utc"))
        finished = _first_text(run, ("finished_at_utc", "finished_at", "completed_at_utc"))
        receipt = _last_receipt(run)
        iterations = "(none)"
        if isinstance(receipt, dict):
            count = receipt.get("iterations")
            if isinstance(count, int) and not isinstance(count, bool):
                iterations = str(count)
        tools = _tool_names(receipt)
        staged = _staged_paths(run)
        owner_tasks = _owner_task_ids(receipt)
        error = _first_text(run, ("error",))
        summary = _receipt_summary(receipt)
        lines: list[str] = [f"# {title} ({run_id})", f"Status: {status}"]
        if started is not None:
            lines.append(f"Started (UTC): {started}")
        if finished is not None:
            lines.append(f"Finished (UTC): {finished}")
        lines.append(f"Iterations: {iterations}")
        lines.append("")
        lines.append("## Tools used")
        if tools is None:
            lines.append("(none)")
        else:
            lines.extend(f"- {name}" for name in tools)
        lines.append("")
        lines.append("## Staged files")
        if staged is None:
            lines.append("(none)")
        else:
            lines.extend(f"- {path}" for path in staged)
        lines.append("")
        lines.append("## Owner tasks filed")
        if owner_tasks is None:
            lines.append("(none)")
        else:
            lines.extend(f"- {task_id}" for task_id in owner_tasks)
        if error is not None:
            lines.append("")
            lines.append("## Error")
            lines.append(error)
        if summary is not None:
            lines.append("")
            lines.append("## Summary")
            lines.append(summary)
        return "\n".join(lines)
    except Exception:
        return (
            "# untitled (unknown)\n"
            "Status: (none)\n"
            "Iterations: (none)\n"
            "\n"
            "## Tools used\n"
            "(none)\n"
            "\n"
            "## Staged files\n"
            "(none)\n"
            "\n"
            "## Owner tasks filed\n"
            "(none)"
        )


REPORT_FLAVORS = ("full", "shareable")


def render_shareable_report(run: dict) -> str:
    """Render the sanitized client-shareable flavor; never raises.

    Same run, minus internals: no iterations, tool calls, owner-task
    ids, or error details. Staged files (deliverables) and the summary
    stay.
    """
    try:
        if not isinstance(run, dict):
            run = {}
        title = _first_text(run, ("title",)) or "untitled"
        run_id = _run_id(run)
        status = _first_text(run, ("status",)) or "(none)"
        started = _first_text(run, ("started_at_utc", "started_at", "created_at_utc"))
        finished = _first_text(run, ("finished_at_utc", "finished_at", "completed_at_utc"))
        staged = _staged_paths(run)
        summary = _receipt_summary(_last_receipt(run))
        lines: list[str] = [f"# {title} ({run_id})", f"Status: {status}"]
        if started is not None:
            lines.append(f"Started (UTC): {started}")
        if finished is not None:
            lines.append(f"Finished (UTC): {finished}")
        lines.append("")
        lines.append("## Staged files")
        if staged is None:
            lines.append("(none)")
        else:
            lines.extend(f"- {path}" for path in staged)
        if summary is not None:
            lines.append("")
            lines.append("## Summary")
            lines.append(summary)
        return "\n".join(lines)
    except Exception:
        return "# untitled (unknown)\nStatus: (none)\n\n## Staged files\n(none)"


def render_report(run: dict, flavor: str = "full") -> str:
    """Render ``flavor`` of the run report; unknown flavors raise.

    ``ValueError`` (unlike the flavor renderers, which never raise).
    """
    if flavor == "full":
        return render_run_report(run)
    if flavor == "shareable":
        return render_shareable_report(run)
    raise ValueError(
        f"unknown report flavor: {flavor!r} (expected one of {', '.join(REPORT_FLAVORS)})"
    )
