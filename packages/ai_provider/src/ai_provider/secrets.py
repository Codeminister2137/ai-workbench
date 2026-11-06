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
from collections.abc import Collection, Iterator
from pathlib import Path
from typing import Literal

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


def _iter_assignments(text: str) -> Iterator[tuple[str, str]]:
    """Yield ``(name, value)`` pairs for each valid assignment line."""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export") and len(line) > 6 and line[6].isspace():
            line = line[6:].lstrip()
            if not line or "=" not in line:
                continue
        name, _, value = line.partition("=")
        name = name.strip()
        value = value.strip()
        if not name or not name.replace("_", "").isalnum():
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        yield name, value


def parse_dotenv_lines(text: str) -> dict[str, str]:
    """Parse ``NAME=VALUE`` lines; skips blanks, comments, malformed rows.

    Values may be single- or double-quoted; quotes are stripped. No escape
    processing and no ``$`` expansion, so file content cannot execute.

    A single optional leading ``export `` prefix (the word ``export``
    followed by whitespace) is stripped before parsing, so
    ``export FOO=bar`` loads ``FOO``. A bare ``export`` with no
    assignment is skipped.

    Inline comments are not stripped: values keep any trailing
    `` # comment`` text. This leniency is intentional because ``#`` is
    legal inside passwords and stripping would corrupt credentials.

    Duplicate keys resolve last-wins: later lines overwrite earlier ones.
    """
    values: dict[str, str] = {}
    for name, value in _iter_assignments(text):
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


def read_secret_key(path: Path, name: str, *, label: str) -> str:
    """Read a single secret VALUE from a dotenv file.

    Unlike load_dotenv which returns names only, this returns the VALUE
    itself. It is for launcher scripts that pass credentials to clients —
    never log the return.

    Exactly-one semantics: the file at ``path`` is read as utf-8-sig and
    ``name`` must appear exactly once with a non-empty value. Raises
    ValueError mentioning the label and path when the file is missing,
    the key is missing, the value is empty, or the key is duplicated.
    """
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise ValueError(f"{label}: secret {name!r} missing: file not found: {path}") from exc
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"{label}: cannot read secret {name!r} from {path}: {exc}") from exc
    matches = [value for key, value in _iter_assignments(text) if key == name]
    if not matches:
        raise ValueError(f"{label}: secret {name!r} not found in {path}")
    if len(matches) > 1:
        raise ValueError(f"{label}: duplicate secret {name!r} in {path}")
    value = matches[0]
    if not value:
        raise ValueError(f"{label}: secret {name!r} is empty in {path}")
    return value


def read_dotenv_values(
    path: Path,
    names: Collection[str] | None = None,
    *,
    missing: Literal["empty", "raise"] = "empty",
) -> dict[str, str]:
    """Read dotenv VALUES into a dict (last-wins).

    Unlike load_dotenv which skips empty values, empty values are KEPT
    here — callers decide how to handle them.

    When ``names`` is given only those names are returned. On a missing
    file, return {} when missing="empty", else re-raise FileNotFoundError
    naming the path. Other OSError also yields {}.
    """
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except FileNotFoundError as exc:
        if missing == "raise":
            raise FileNotFoundError(f"dotenv file not found: {path}") from exc
        return {}
    except (OSError, UnicodeError):
        return {}
    wanted: set[str] | None = set(names) if names is not None else None
    values: dict[str, str] = {}
    for key, value in _iter_assignments(text):
        if wanted is not None and key not in wanted:
            continue
        values[key] = value
    return values
