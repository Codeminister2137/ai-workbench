"""Agent-mode chat turns via Mai sessions (interactive Mai, slice A).

Ask mode (default) keeps the read-only inspection relay. Agent mode runs
the turn through a Mai subprocess inside a persistent per-chat scratch
worktree branched from the live checkout: edits never touch the shared
tree until the owner explicitly applies staged files. The Mai coding
session binds to the chat session across turns (conversational loop);
each turn captures the staged diff into the transcript for review.

Slice A enforces scoped rules in code: agent turns require the
``chat_agent_enabled`` master switch, run with Mai's trusted_local
policy, and stage everything. Ask-always approvals, YOLO auto-apply
and presence routing are slice B.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

CHAT_MODES = ("ask", "agent")
CHAT_WORKTREE_DIRNAME = ".tmp/chat-worktrees"
CHAT_BASE_BRANCH = "develop"


def progress_path(data_dir: Path, session_id: str, message_id: str) -> Path:
    """Resolve a turn's local activity file, rejecting path separators."""
    for value in (session_id, message_id):
        if not value or any(not (ch.isalnum() or ch == "-") for ch in value):
            raise ValueError("Invalid progress identifier")
    return data_dir / "chat-progress" / f"{session_id}_{message_id}.jsonl"


class ProgressWriter:
    """Best-effort local stdout activity; failures must not interrupt a turn."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def append(self, line: str) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"ts": datetime.now(UTC).isoformat(), "line": line}) + "\n")
        except (OSError, ValueError):
            pass


def read_progress(path: Path | str) -> list[str]:
    """Return at most the last 200 valid activity lines, tolerating partial writes."""
    lines: deque[str] = deque(maxlen=200)
    try:
        with Path(path).open(encoding="utf-8", errors="replace") as stream:
            for raw in stream:
                try:
                    row = json.loads(raw)
                    if isinstance(row, dict) and isinstance(row.get("line"), str):
                        lines.append(row["line"])
                except ValueError:
                    continue
    except (OSError, ValueError):
        pass
    return list(lines)


class ChatAgentError(RuntimeError):
    """Agent turn setup failed; nothing executed."""


REPORT_MARKERS = ("### Agent report", "## **SUMMARY**")
_COMMAND_RE = re.compile(
    r"external_agent_activity:\s+command_execution\s+"
    r"(?P<status>in_progress|completed|failed)\s+-\s+command:\s+(?P<rest>.+)$"
)
_QUOTED_HEAD_RE = re.compile(r'\s*("(?:[^"\\]|\\.)*")\s*(?P<tail>.*)$')


def _clean_command(rest: str) -> str:
    """Decode Mai's command rendering: a JSON-quoted exe plus raw args."""
    match = _QUOTED_HEAD_RE.match(rest)
    if match is None:
        return rest.strip()
    try:
        head = json.loads(match.group(1))
    except ValueError:
        return rest.strip()
    if not isinstance(head, str):
        return rest.strip()
    tail = match.group("tail").strip()
    return f"{head} {tail}".strip() if tail else head.strip()


_ACTIVITY_PREFIXES = (
    "external_agent_activity",
    "=== Repo Coding Assistant ===",
    "=== External agent diagnostics ===",
    "coding_session_id:",
)


@dataclass(slots=True, frozen=True)
class AgentTurnView:
    """Readable split of one agent-turn transcript for the chat UI."""

    report: str
    commands: tuple[dict[str, str], ...]
    has_agent_markers: bool


def split_agent_transcript(content: str) -> AgentTurnView:
    """Split Mai stdout into a clean report plus the executed commands.

    The report is Mai's own closing section (``### Agent report`` or the
    ``## **SUMMARY**`` closeout); without either marker the full text is
    the report. Commands come from Mai's ``command_execution`` activity
    lines, collapsed to the last status seen per command. Anything
    unrecognized stays in the full transcript, never dropped.
    """
    text = content or ""
    report = text
    marker_seen = False
    for marker in REPORT_MARKERS:
        index = text.find(marker)
        if index != -1:
            report = text[index:].strip()
            marker_seen = True
            break
    seen: dict[str, str] = {}
    activity_seen = marker_seen
    for line in text.splitlines():
        stripped = line.strip()
        if not activity_seen and stripped.startswith(_ACTIVITY_PREFIXES):
            activity_seen = True
        match = _COMMAND_RE.search(line)
        if match is None:
            continue
        command = _clean_command(match.group("rest"))
        if not command:
            continue
        seen[command] = match.group("status")
    commands = tuple({"command": command, "status": status} for command, status in seen.items())
    return AgentTurnView(
        report=report.strip(),
        commands=commands,
        has_agent_markers=activity_seen or bool(commands),
    )


@dataclass(slots=True, frozen=True)
class ChatWorktree:
    """Persistent scratch checkout for one agent-mode chat session."""

    path: Path
    branch: str
    base_commit: str


def _git(repo: Path, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except OSError as exc:
        raise ChatAgentError(f"git unavailable: {exc}") from exc
    if proc.returncode != 0:
        raise ChatAgentError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    # Trailing newline only: porcelain output has significant leading columns.
    return proc.stdout.rstrip("\n")


def ensure_chat_worktree(repo_root: Path | str, session_id: str) -> ChatWorktree:
    """Get-or-create the scratch worktree for one chat session (fail-closed)."""
    repo = Path(repo_root).resolve()
    if not (repo / ".git").exists():
        raise ChatAgentError(f"not a git checkout: {repo}")
    short = "".join(ch for ch in str(session_id) if ch.isalnum())[:12]
    if not short:
        raise ChatAgentError("session id has no usable characters")
    branch = f"chat/{short}"
    target = repo / CHAT_WORKTREE_DIRNAME / short
    if target.exists():
        registered = _git(repo, "worktree", "list", "--porcelain").replace("\\", "/")
        if target.as_posix() not in registered:
            raise ChatAgentError(f"stale directory blocks chat worktree: {target}")
        # develop is merge-only, so the fork point is the creation base.
        base = _git(repo, "merge-base", branch, CHAT_BASE_BRANCH).strip()
        return ChatWorktree(path=target, branch=branch, base_commit=base)
    if _git(repo, "branch", "--list", branch):
        raise ChatAgentError(f"chat branch already exists: {branch}")
    target.parent.mkdir(parents=True, exist_ok=True)
    _git(repo, "worktree", "add", "-b", branch, str(target), CHAT_BASE_BRANCH)
    config_src = repo / "user-config.toml"
    if not config_src.is_file():
        _git(repo, "worktree", "remove", "--force", str(target))
        _git(repo, "branch", "-D", branch)
        raise ChatAgentError(f"user-config.toml missing in {repo}; cannot isolate chat")
    shutil.copy2(config_src, target / "user-config.toml")
    base_commit = _git(target, "rev-parse", "HEAD").strip()
    return ChatWorktree(path=target, branch=branch, base_commit=base_commit)


def staged_files(worktree: Path | str) -> list[dict[str, str]]:
    """Changed paths in the chat worktree (porcelain status, no contents)."""
    out = _git(Path(worktree), "status", "--porcelain=v1", "--untracked-files=all")
    staged: list[dict[str, str]] = []
    for line in out.splitlines():
        if len(line) < 4:
            continue
        code, path = line[:2].strip(), line[3:].strip().strip('"')
        if path:
            staged.append({"path": path, "status": code or "??"})
    return staged


def build_chat_prompt(transcript_digest: str, turn_text: str) -> str:
    """Instruction for one agent turn: context plus the request.

    Staged-write convention is explicit: the agent edits files in its
    workspace, and the host diffs and reviews them afterwards. Nothing
    is applied to the shared checkout without the owner saying so.
    """
    return (
        "You are Mai, acting inside one dashboard chat turn.\n"
        "Edit files directly in your workspace when the request needs code; "
        "the host diffs your worktree afterwards and the owner reviews "
        "before anything lands in the shared checkout. Never push, merge, "
        "publish, send mail, or touch credentials.\n"
        "Close every turn with a synthesis block in exactly this shape:\n"
        "Did: <what changed this turn>\n"
        "Found: <key findings>\n"
        "Next: <immediate next step>\n"
        "Needs owner: <decisions/inputs needed, or 'nothing'>\n\n"
        f"Conversation so far (digest):\n{transcript_digest}\n\n"
        f"Current request:\n{turn_text}\n"
    )


def apply_staged(
    repo_root: Path | str,
    worktree: ChatWorktree,
    paths: list[str],
) -> dict[str, list[str] | dict[str, str]]:
    """Copy staged worktree files into the live checkout (fail-closed).

    Each path applies only when the live file still matches the worktree
    base (nobody touched it meanwhile) and the worktree copy differs.
    Deletes and renames are refused in slice A; directory escapes and
    protected areas (``.git``, ``.venv``, data dirs) are always refused.
    """
    repo = Path(repo_root).resolve()
    applied: list[str] = []
    refused: dict[str, str] = {}
    for raw in paths:
        rel = str(raw).replace("\\", "/").lstrip("/")
        if not rel or rel.startswith((".", "..")) or "/.git/" in f"/{rel}/" or rel == ".git":
            refused[raw] = "path escapes the checkout or targets .git"
            continue
        if rel.startswith((".venv/", "apps/workbench_dashboard/data/", "data/")):
            refused[raw] = "protected area is never applied"
            continue
        live = repo / rel
        staged = worktree.path / rel
        if not staged.is_file():
            refused[raw] = "not a staged file (deletes/renames unsupported)"
            continue
        try:
            base_bytes = subprocess.run(
                ["git", "-C", str(repo), "show", f"{worktree.base_commit}:{rel}"],
                capture_output=True,
                timeout=60,
            )
        except OSError as exc:
            raise ChatAgentError(f"git unavailable: {exc}") from exc
        base_exists = base_bytes.returncode == 0
        staged_bytes = staged.read_bytes()
        if live.exists():
            if not base_exists or live.read_bytes() != base_bytes.stdout:
                refused[raw] = "live file changed since worktree base; re-review first"
                continue
            if staged_bytes == base_bytes.stdout:
                refused[raw] = "worktree copy identical to base; nothing to apply"
                continue
        elif base_exists:
            refused[raw] = "live file deleted since base; re-review first"
            continue
        live.parent.mkdir(parents=True, exist_ok=True)
        live.write_bytes(staged_bytes)
        applied.append(rel)
    return {"applied": applied, "refused": refused}
