"""Preview-first Python symbol rename tools with ephemeral guarded plans."""

from __future__ import annotations

import ast
import difflib
import hashlib
import importlib
import io
import json
import keyword
import os
import secrets
import stat
import tempfile
import threading
import time
import tokenize
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_agent.contracts import ToolCall, ToolCategory, ToolDefinition, ToolParameter, ToolResult
from ai_agent.tools.base import BaseTool, ToolContext

PLAN_TTL_SECONDS = 300
MAX_STORED_PLANS = 16
MAX_FILE_BYTES = 512_000
MAX_PLAN_BYTES = 2_000_000
MAX_DIFF_BYTES = 7_000
MAX_NAVIGATION_RESULTS = 100
MAX_NAVIGATION_SNIPPET_CHARS = 240
_JEDI_LOCK = threading.RLock()


@dataclass(frozen=True, slots=True)
class FileChange:
    path: Path
    original_sha256: str
    original_mode: int
    updated_bytes: bytes


@dataclass(frozen=True, slots=True)
class RenamePlan:
    handle: str
    digest: str
    diff: str
    changes: tuple[FileChange, ...]
    expires_at: float
    owner_id: str
    task_id: str | None


class RenamePlanStore:
    """Own short-lived immutable plans; nothing is persisted to disk."""

    def __init__(
        self,
        workspace: Path | None = None,
        *,
        owner_id: str | None = None,
        task_id: str | None = None,
        ttl_seconds: int = PLAN_TTL_SECONDS,
    ) -> None:
        self.workspace = workspace.resolve() if workspace is not None else None
        self.owner_id = owner_id or secrets.token_urlsafe(18)
        self.task_id = task_id
        self.ttl_seconds = ttl_seconds
        self._plans: OrderedDict[str, RenamePlan] = OrderedDict()
        self._lock = threading.RLock()

    def preview(
        self,
        path: str,
        line: int,
        column: int,
        new_name: str,
        context: ToolContext,
    ) -> RenamePlan:
        workspace = context.workspace_root.resolve()
        with self._lock:
            if self.workspace is None:
                self.workspace = workspace
            if self.workspace != workspace:
                raise ValueError("Rename plan workspace changed")
            target = _workspace_file(workspace, path)
            if target.suffix.lower() != ".py":
                raise ValueError("Semantic rename currently supports Python source files only")
            if not target.is_file():
                raise ValueError("Rename source must be an existing workspace file")
            if type(line) is not int or line < 1 or type(column) is not int or column < 1:
                raise ValueError("Symbol line and column must be positive one-based integers")
            if not new_name.isidentifier() or keyword.iskeyword(new_name):
                raise ValueError("New symbol name must be a non-keyword Python identifier")

            original_files = _read_source(target)
            source = original_files.decode("utf-8")
            _validate_syntax(source, target)
            _require_name_token(source, line, column)
            refactoring = _jedi_rename(source, target, workspace, line, column - 1, new_name)
            if tuple(refactoring.get_renames()):
                raise ValueError("File and module moves are not supported by preview rename")

            changes: list[FileChange] = []
            rendered: list[str] = []
            total_bytes = 0
            for changed_path, changed_file in sorted(
                refactoring.get_changed_files().items(), key=lambda item: str(item[0])
            ):
                if changed_path is None:
                    raise ValueError("Rename plan contains a change without a workspace file")
                file_path = _workspace_file(workspace, str(changed_path))
                if file_path.suffix.lower() != ".py" or not file_path.is_file():
                    raise ValueError("Rename plan includes a non-Python or missing file")
                original = _read_source(file_path)
                module_node = getattr(changed_file, "_module_node", None)
                get_original_code = getattr(module_node, "get_code", None)
                if not callable(get_original_code):
                    raise ValueError("Jedi did not expose the source snapshot for a changed file")
                jedi_original = get_original_code()
                if not isinstance(jedi_original, str) or original != jedi_original.encode("utf-8"):
                    raise ValueError(
                        "A changed Python file changed while Jedi was preparing preview"
                    )
                updated = changed_file.get_new_code().encode("utf-8")
                if len(original) > MAX_FILE_BYTES or len(updated) > MAX_FILE_BYTES:
                    raise ValueError("A changed Python file exceeds the 512 KB preview limit")
                old_text = original.decode("utf-8")
                new_text = updated.decode("utf-8")
                _validate_syntax(old_text, file_path)
                _validate_syntax(new_text, file_path)
                if original == updated:
                    continue
                relative = file_path.relative_to(workspace).as_posix()
                rendered.extend(
                    difflib.unified_diff(
                        old_text.splitlines(keepends=True),
                        new_text.splitlines(keepends=True),
                        fromfile=relative,
                        tofile=relative,
                    )
                )
                changes.append(
                    FileChange(
                        file_path,
                        hashlib.sha256(original).hexdigest(),
                        stat.S_IMODE(file_path.stat().st_mode),
                        updated,
                    )
                )
                total_bytes += len(original) + len(updated)
                if len(changes) > 32 or total_bytes > MAX_PLAN_BYTES:
                    raise ValueError("Rename exceeds the bounded 32-file / 2 MB plan limit")

            diff = "".join(rendered)
            if not changes:
                raise ValueError("Jedi found no safe changes for the selected symbol")
            if len(diff.encode("utf-8")) > MAX_DIFF_BYTES:
                raise ValueError("Complete rename diff exceeds the 7 KB review limit")

            handle = secrets.token_urlsafe(24)
            digest_input = [
                {
                    "path": change.path.relative_to(workspace).as_posix(),
                    "original_sha256": change.original_sha256,
                    "updated_sha256": hashlib.sha256(change.updated_bytes).hexdigest(),
                }
                for change in changes
            ]
            digest = hashlib.sha256(
                (self.owner_id + (self.task_id or "") + diff + repr(digest_input)).encode("utf-8")
            ).hexdigest()
            plan = RenamePlan(
                handle,
                digest,
                diff,
                tuple(changes),
                time.monotonic() + self.ttl_seconds,
                self.owner_id,
                self.task_id,
            )
            self._discard_expired()
            while len(self._plans) >= MAX_STORED_PLANS:
                self._plans.popitem(last=False)
            self._plans[handle] = plan
            return plan

    def get(self, handle: str, context: ToolContext) -> RenamePlan | None:
        with self._lock:
            self._discard_expired()
            plan = self._plans.get(handle)
            if (
                plan is None
                or self.workspace != context.workspace_root.resolve()
                or plan.owner_id != self.owner_id
                or plan.task_id != self.task_id
                or time.monotonic() >= plan.expires_at
            ):
                return None
            return plan

    def consume(self, handle: str, context: ToolContext) -> RenamePlan:
        with self._lock:
            plan = self.get(handle, context)
            if plan is None:
                raise ValueError("Rename plan is missing, expired, already used, or out of scope")
            del self._plans[handle]
            return plan

    def bind_task(self, task_id: str) -> None:
        """Bind this owner-local plan store once its task identity is known."""
        with self._lock:
            if self.task_id not in (None, task_id):
                raise ValueError("Rename plan task identity changed")
            self.task_id = task_id

    def _discard_expired(self) -> None:
        now = time.monotonic()
        for handle, plan in tuple(self._plans.items()):
            if now >= plan.expires_at:
                del self._plans[handle]


class RenamePreviewTool(BaseTool):
    """Create a non-mutating, bounded preview of a Python symbol rename."""

    def __init__(self, plans: RenamePlanStore) -> None:
        self.plans = plans

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            "rename_preview",
            (
                "Preview a Python symbol rename without changing files. Give path, "
                "one-based line/column on the identifier, and a new identifier. "
                "Review the complete diff, then pass its plan_id to rename_apply."
            ),
            ToolCategory.READ,
            (
                ToolParameter("path", "string", "Existing Python file inside the workspace"),
                ToolParameter("line", "integer", "One-based source line"),
                ToolParameter("column", "integer", "One-based column on the identifier"),
                ToolParameter("new_name", "string", "New non-keyword Python identifier"),
            ),
        )

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        path = arguments.get("path")
        line = arguments.get("line")
        column = arguments.get("column")
        new_name = arguments.get("new_name")
        if (
            not isinstance(path, str)
            or type(line) is not int
            or type(column) is not int
            or not isinstance(new_name, str)
        ):
            raise ValueError("Rename path/new_name must be strings and line/column integers")
        plan = self.plans.preview(path, line, column, new_name, context)
        paths = [
            change.path.relative_to(context.workspace_root.resolve()).as_posix()
            for change in plan.changes
        ]
        return ToolResult(
            self.definition.name,
            (
                f"Preview plan_id={plan.handle} plan_sha256={plan.digest}\n"
                f"Changed files: {', '.join(paths)}\n"
                "No files were changed. Review the complete diff below; apply only with "
                "rename_apply(plan_id=...) under the selected write-approval policy.\n" + plan.diff
            ),
            metadata={
                "plan_id": plan.handle,
                "plan_sha256": plan.digest,
                "files": paths,
                "expires_in_seconds": self.plans.ttl_seconds,
                "applied": False,
            },
        )


class RenameApplyTool(BaseTool):
    """Apply a reviewed preview only after policy authorization and digest checks."""

    def __init__(self, plans: RenamePlanStore) -> None:
        self.plans = plans

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            "rename_apply",
            (
                "Apply one unexpired rename_preview plan. Under interactive policy, "
                "the exact complete diff is shown for fresh approval. Plans are "
                "one-use and expire after five minutes."
            ),
            ToolCategory.WRITE,
            (ToolParameter("plan_id", "string", "Opaque handle returned by rename_preview"),),
        )

    def approval_call(self, call: ToolCall) -> ToolCall | None:
        handle = call.arguments.get("plan_id")
        if not isinstance(handle, str):
            return None
        plan = self.plans.get(handle, ToolContext(self.plans.workspace or Path.cwd()))
        if plan is None:
            return None
        return ToolCall(
            call.name,
            {
                "plan_id": plan.handle,
                "plan_sha256": plan.digest,
                "complete_diff": plan.diff,
            },
            call.call_id,
        )

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        handle = arguments.get("plan_id")
        if not isinstance(handle, str):
            raise ValueError("A rename plan_id is required")
        plan = self.plans.consume(handle, context)
        if not plan.changes or len(plan.diff.encode("utf-8")) > MAX_DIFF_BYTES:
            raise ValueError("Rename plan is invalid or exceeds the review limit")

        for change in plan.changes:
            _workspace_file(context.workspace_root.resolve(), str(change.path))
            current = change.path.read_bytes()
            if hashlib.sha256(current).hexdigest() != change.original_sha256:
                raise ValueError(
                    "Rename plan is stale; "
                    f"{change.path.relative_to(context.workspace_root)} changed"
                )

        applied: list[dict[str, str]] = []
        try:
            for change in plan.changes:
                _workspace_file(context.workspace_root.resolve(), str(change.path))
                current = change.path.read_bytes()
                if hashlib.sha256(current).hexdigest() != change.original_sha256:
                    raise ValueError(
                        f"{change.path.relative_to(context.workspace_root)} changed during apply"
                    )
                _atomic_replace(change)
                applied.append(
                    {
                        "path": change.path.relative_to(
                            context.workspace_root.resolve()
                        ).as_posix(),
                        "sha256": hashlib.sha256(change.updated_bytes).hexdigest(),
                    }
                )
        except (OSError, ValueError) as exc:
            return ToolResult(
                self.definition.name,
                (
                    f"Rename apply failed after {len(applied)} of {len(plan.changes)} files. "
                    "No automatic rollback was attempted; inspect the listed effects and "
                    "reconcile the remaining files before creating a new preview. "
                    f"Failure: {exc}"
                ),
                is_error=True,
                metadata={"plan_sha256": plan.digest, "applied": applied},
            )
        return ToolResult(
            self.definition.name,
            f"Applied rename plan {plan.digest} to {len(applied)} files.",
            metadata={"plan_sha256": plan.digest, "applied": applied},
        )


class PythonNavigateTool(BaseTool):
    """Resolve Python definitions or references within the workspace."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            "python_navigate",
            (
                "Find Python definitions or references for the identifier at a "
                "one-based line and column. Results are limited to Python files "
                "inside the workspace; install the optional rename-preview extra "
                "to enable Jedi-backed navigation."
            ),
            ToolCategory.READ,
            (
                ToolParameter("path", "string", "Existing Python file inside the workspace"),
                ToolParameter("line", "integer", "One-based source line"),
                ToolParameter("column", "integer", "One-based column on the identifier"),
                ToolParameter(
                    "operation",
                    "string",
                    "Resolve definitions or references",
                    enum_values=("definitions", "references"),
                ),
            ),
        )

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        path = arguments.get("path")
        line = arguments.get("line")
        column = arguments.get("column")
        operation = arguments.get("operation")
        if (
            not isinstance(path, str)
            or type(line) is not int
            or type(column) is not int
            or operation not in ("definitions", "references")
        ):
            raise ValueError(
                "Navigation requires a path, integer line/column, "
                "and definitions or references operation"
            )

        workspace = context.workspace_root.resolve()
        target = _workspace_file(workspace, path)
        if target.suffix.lower() != ".py" or not target.is_file():
            raise ValueError("Navigation source must be an existing workspace Python file")
        if line < 1 or column < 1:
            raise ValueError("Symbol line and column must be positive one-based integers")
        source = _read_source(target).decode("utf-8")
        _validate_syntax(source, target)
        _require_name_token(source, line, column)
        names = _jedi_navigate(source, target, workspace, line, column - 1, operation)

        results: list[dict[str, Any]] = []
        excluded = 0
        source_cache: dict[Path, list[str]] = {target: source.splitlines()}
        for name in names:
            module_path = getattr(name, "module_path", None)
            name_line = getattr(name, "line", None)
            name_column = getattr(name, "column", None)
            if module_path is None or type(name_line) is not int or type(name_column) is not int:
                excluded += 1
                continue
            try:
                result_path = _workspace_file(workspace, str(module_path))
                if result_path.suffix.lower() != ".py" or not result_path.is_file():
                    excluded += 1
                    continue
                result_lines = source_cache.get(result_path)
                if result_lines is None:
                    result_lines = _read_source(result_path).decode("utf-8").splitlines()
                    source_cache[result_path] = result_lines
            except (OSError, ValueError):
                excluded += 1
                continue

            if name_line < 1 or name_line > len(result_lines):
                excluded += 1
                continue
            snippet = result_lines[name_line - 1]
            if len(snippet) > MAX_NAVIGATION_SNIPPET_CHARS:
                snippet = snippet[:MAX_NAVIGATION_SNIPPET_CHARS] + "..."
            results.append(
                {
                    "path": result_path.relative_to(workspace).as_posix(),
                    "line": name_line,
                    "column": name_column + 1,
                    "name": str(getattr(name, "name", ""))[:160],
                    "description": str(getattr(name, "description", ""))[:160],
                    "snippet": snippet,
                }
            )

        truncated = len(results) > MAX_NAVIGATION_RESULTS
        results = results[:MAX_NAVIGATION_RESULTS]
        metadata = {
            "operation": operation,
            "results": results,
            "truncated": truncated,
            "excluded_outside_workspace_or_invalid": excluded,
        }
        return ToolResult(
            self.definition.name,
            json.dumps(metadata, ensure_ascii=False),
            metadata=metadata,
        )


def _jedi_rename(source: str, target: Path, workspace: Path, line: int, column: int, new_name: str):
    try:
        jedi = importlib.import_module("jedi")
    except ImportError as exc:
        raise RuntimeError(
            "Python rename preview requires the optional extra; run "
            "`python -m uv sync --extra rename-preview`."
        ) from exc
    with _JEDI_LOCK:
        project = jedi.Project(path=workspace, added_sys_path=[str(workspace)])
        script = jedi.Script(code=source, path=target, project=project)
        syntax_errors = script.get_syntax_errors()
        if syntax_errors:
            raise ValueError(f"Rename source has syntax errors: {syntax_errors[0]}")
        definitions = script.goto(
            line=line, column=column, follow_imports=False, follow_builtin_imports=False
        )
        if len(definitions) != 1:
            raise ValueError("Jedi could not resolve one unambiguous symbol at that position")
        refactoring = script.rename(line=line, column=column, new_name=new_name)
        if not hasattr(refactoring, "get_changed_files"):
            raise ValueError("Jedi returned an unsupported rename plan")
        return refactoring


def _jedi_navigate(
    source: str,
    target: Path,
    workspace: Path,
    line: int,
    column: int,
    operation: str,
):
    try:
        jedi = importlib.import_module("jedi")
    except ImportError as exc:
        raise RuntimeError(
            "Python navigation requires the optional extra; run "
            "`python -m uv sync --extra rename-preview`."
        ) from exc
    with _JEDI_LOCK:
        project = jedi.Project(path=workspace, added_sys_path=[str(workspace)])
        script = jedi.Script(code=source, path=target, project=project)
        syntax_errors = script.get_syntax_errors()
        if syntax_errors:
            raise ValueError(f"Navigation source has syntax errors: {syntax_errors[0]}")
        if operation == "definitions":
            return script.goto(
                line=line,
                column=column,
                follow_imports=True,
                follow_builtin_imports=False,
            )
        return script.get_references(line=line, column=column, include_builtins=False)


def _workspace_file(workspace: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = workspace / candidate
    candidate = Path(os.path.abspath(candidate))
    try:
        relative = candidate.relative_to(workspace)
    except ValueError as exc:
        raise ValueError(
            "Python semantic paths must remain inside the configured workspace"
        ) from exc
    current = workspace
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Python semantic tools do not follow symbolic links")
    if candidate.resolve() != candidate:
        raise ValueError("Python semantic path resolves outside its original workspace location")
    return candidate


def _read_source(path: Path) -> bytes:
    raw = path.read_bytes()
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("Python source file exceeds the 512 KB preview limit")
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Python semantic tools currently support UTF-8 source only") from exc
    return raw


def _validate_syntax(source: str, path: Path) -> None:
    try:
        ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        raise ValueError(
            f"Cannot analyze a file with syntax errors: {path.name}:{exc.lineno}"
        ) from exc


def _require_name_token(source: str, line: int, column: int) -> None:
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        selected = [
            token
            for token in tokens
            if token.type == tokenize.NAME
            and token.start[0] == line
            and token.start[1] <= column - 1 < token.end[1]
        ]
    except tokenize.TokenError as exc:
        raise ValueError("Could not tokenize the selected Python file") from exc
    if len(selected) != 1:
        raise ValueError("Select a Python identifier by its one-based line and column")


def _atomic_replace(change: FileChange) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=change.path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(change.updated_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, change.original_mode)
        os.replace(temporary, change.path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
