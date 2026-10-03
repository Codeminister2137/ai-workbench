"""Local content fingerprints for repair evidence, including ignored reports."""

import hashlib
import os
from pathlib import Path

# Runtime bookkeeping must not turn an otherwise ineffective repair into progress.
_RUNTIME_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".pyright",
    ".uv-cache",
    ".idea",
    ".vscode",
    ".codex",
    ".tools",
    "logs",
}
_RUNTIME_SUFFIXES = {".log", ".sqlite", ".sqlite3", ".pyc", ".pyo"}


def workspace_fingerprints(root: Path) -> dict[str, str]:
    """Hash workspace files without following links or applying Git ignore rules.

    Reports remain visible even outside Git. Logs, databases, caches, and IDE
    bookkeeping are excluded. Read errors are explicit evidence, never silently
    interpreted as a successful edit. File contents remain local.
    """
    result: dict[str, str] = {}

    def on_error(error: OSError) -> None:
        result[f"!scan:{error.filename}"] = type(error).__name__

    for directory, dirs, files in os.walk(root, onerror=on_error, followlinks=False):
        dirs[:] = [
            name
            for name in dirs
            if name not in _RUNTIME_DIRS and not (Path(directory) / name).is_symlink()
        ]
        for name in files:
            path = Path(directory) / name
            if (
                path.is_symlink()
                or path.suffix in _RUNTIME_SUFFIXES
                or ".sqlite3-" in name
                or name == ".coverage"
            ):
                continue
            key = path.relative_to(root).as_posix()
            try:
                with path.open("rb") as stream:
                    result[key] = hashlib.file_digest(stream, "sha256").hexdigest()
            except OSError as error:
                result[key] = f"!unreadable:{type(error).__name__}"
    return result


def changed_paths(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """Identify additions, content changes, and deletions between checkpoints."""
    return sorted(key for key in before.keys() | after.keys() if before.get(key) != after.get(key))
