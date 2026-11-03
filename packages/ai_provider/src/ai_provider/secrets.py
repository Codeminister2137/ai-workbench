"""Local secret-store loader: repo-root ``.env`` into process env.

The ``.env`` file is the local secret store. It is gitignored, owner-only
on disk, and must never be pasted into prompts, transcripts, logs, or
reports. All provider code reads credentials from process environment;
this loader is the single harness that fills process env from the store
without ever exposing values to callers: it returns loaded NAMES only.

Rules enforced here, not by convention:
- no shell expansion, no imports, no prints of values;
- missing store is not an error (callers fall back to ambient env);
- existing process env wins by default, so CI/owner exports keep
  precedence and nothing here can silently downgrade a credential.
"""

from __future__ import annotations

import os
from pathlib import Path

STORE_FILENAME = ".env"


def _store_path(root: Path | None) -> Path:
    if root is not None:
        return Path(root) / STORE_FILENAME
    here = Path(__file__).resolve()
    package_root = here.parent.parent.parent.parent.parent
    for candidate in (package_root, Path.cwd()):
        if (candidate / STORE_FILENAME).exists():
            return candidate / STORE_FILENAME
    return package_root / STORE_FILENAME


def parse_dotenv_lines(text: str) -> dict[str, str]:
    """Parse ``NAME=VALUE`` lines; skips blanks, comments, malformed rows.

    Values may be single- or double-quoted; quotes are stripped. No escape
    processing and no ``$`` expansion, so file content cannot execute.
    """
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip()
        value = value.strip()
        if not name or not name.replace("_", "").isalnum():
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[name] = value
    return values


def load_dotenv(root: Path | None = None, *, override: bool = False) -> tuple[str, ...]:
    """Load the secret store into process env; return loaded NAMES only.

    Returns an empty tuple when the store file is absent. Never returns,
    logs, or prints credential values.
    """
    path = _store_path(root)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ()
    except (OSError, UnicodeError):
        return ()
    loaded: list[str] = []
    for name, value in parse_dotenv_lines(text).items():
        if not value:
            continue
        if not override and os.environ.get(name):
            continue
        os.environ[name] = value
        loaded.append(name)
    return tuple(loaded)
