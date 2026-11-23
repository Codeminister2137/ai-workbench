"""Classify a git diff into ADR-087 merge tiers by changed file paths.

Usage::

    python scripts/check-merge-tier.py [base-ref]

If *base-ref* is omitted, the script uses the merge-base between the current
HEAD and ``develop``.  It prints one line per tier encountered in the diff and
a final verdict line:

    TIER 3  packages/ai_provider/secrets.py
    TIER 2  packages/ai_agent/new_feature.py
    TIER 1  docs/decisions/ADR-088.md
    VERDICT: Tier 3 — needs owner pre-approval before merge

Exit codes:

- ``0`` — Tier 1 only (agent may merge on green).
- ``1`` — Tier 2 present, no Tier 3 (agent drafts, owner uses then promotes).
- ``2`` — Tier 3 present (owner pre-approval required before merge).
- ``3`` — Script/git error.

Tier rules (ADR-087)
--------------------
Tier 3 — needs explicit pre-merge owner approval:
  * Secrets / auth / credentials (secrets.py, auth, login, credentials,
    tokens, passwords).
  * Money / billing (spend, billing, invoice, allowance, purchases).
  * Data deletion / migration (delete, migration, migrate).
  * Architecture (docs/architecture.md, cross-package contracts /
    ``__init__.py`` that cross package boundaries, shared interfaces).
  * External data routing (provider adapters, mail sending, webhooks,
    outbound HTTP routing).

Tier 2 — features / behavior changes:
  * Any application or library source file not covered by Tier 3 or Tier 1.

Tier 1 — agent merges on green:
  * Documentation only (docs/, *.md, *.rst, *.txt).
  * Tests (tests/, **/tests/, test_*.py, *_test.py).
  * Formatting / style changes (detected by extension or path only; the
    script cannot inspect content).
  * Internal tooling / scripts (scripts/, *.cfg, *.ini, *.toml, *.lock,
    pyproject.toml, .ruff.toml, .pre-commit-config.yaml, Makefile,
    Dockerfile, CI configuration).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import PurePosixPath

# ---------------------------------------------------------------------------
# Tier-3 patterns — secrets / auth / credentials
# ---------------------------------------------------------------------------
_T3_SECRETS = re.compile(
    r"""
    (^|/)                           # start or path separator
    (
        secrets?                    # secrets.py, secret_store.py, …
        | auth(?:entication|orization)?  # auth, authentication, authorization
        | login
        | credentials?
        | tokens?                   # token_store, etc.
        | password
        | api[_\-]?key
        | private[_\-]?key
        | \.env
    )
    (\.|$|/)                        # followed by extension, end, or separator
    """,
    re.VERBOSE | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Tier-3 patterns — money / billing
# ---------------------------------------------------------------------------
_T3_BILLING = re.compile(
    r"""
    (^|/)
    (
        spend
        | billing
        | invoice
        | allowance
        | purchases?
        | payment
        | stripe
        | pricing
    )
    (\.|$|/)
    """,
    re.VERBOSE | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Tier-3 patterns — data deletion / migration
# ---------------------------------------------------------------------------
_T3_DATA_OPS = re.compile(
    r"""
    (^|/)
    (
        migrat(?:e|ion|ions)
        | delete
        | deletion
        | drop[_\-]?table
        | purge
    )
    (\.|$|/)
    """,
    re.VERBOSE | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Tier-3 patterns — architecture / cross-package contracts
# ---------------------------------------------------------------------------
_T3_ARCHITECTURE = re.compile(
    r"""
    (^|/)
    (
        architecture           # docs/architecture.md
    )
    (\.|$|/)
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Cross-package __init__ or shared contract files
_T3_CROSS_PACKAGE_INIT = re.compile(
    r"^packages/[^/]+/[^/]+/__init__\.py$",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Tier-3 patterns — external data routing
# ---------------------------------------------------------------------------
_T3_ROUTING = re.compile(
    r"""
    (^|/)
    (
        adapter
        | webhook
        | outbound
        | mail[_\-]?send(?:er)?
        | smtp
        | sendgrid
        | provider[_\-]?route
        | egress
        | relay
    )
    (\.|$|/)
    """,
    re.VERBOSE | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Tier-1 patterns — docs / tests / tooling / formatting
# ---------------------------------------------------------------------------
_T1_PATHS = re.compile(
    r"""
    ^(
        docs/                           # documentation tree
        | tests/                        # workspace tests
        | apps/[^/]+/tests/             # app-scoped tests
        | packages/[^/]+/tests/         # package-scoped tests
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

_T1_EXTENSIONS = frozenset(
    {
        ".md",
        ".rst",
        ".txt",
        ".cfg",
        ".ini",
        ".toml",
        ".lock",
        ".yaml",
        ".yml",
        ".json",  # config JSON only — not data contracts (heuristic)
        ".dockerfile",
    }
)

_T1_FILENAMES = frozenset(
    {
        "makefile",
        "dockerfile",
        ".pre-commit-config.yaml",
        ".ruff.toml",
        "pyproject.toml",
        "setup.cfg",
        "setup.py",
        ".gitignore",
        ".gitattributes",
        "requirements.txt",
        "requirements-dev.txt",
    }
)

_T1_TEST_FILE = re.compile(
    r"(^|/)(test_[^/]+|[^/]+_test)\.py$",
    re.IGNORECASE,
)

_T1_SCRIPTS = re.compile(r"^scripts/", re.IGNORECASE)


def classify_path(path: str) -> int:
    """Return the ADR-087 tier (1, 2, or 3) for a single changed file path.

    Parameters
    ----------
    path:
        The file path as it appears in the diff (POSIX separators, relative to
        repo root).

    Returns
    -------
    int
        ``3`` if the path matches any Tier-3 rule, ``1`` if it matches any
        Tier-1 rule but no Tier-3 rule, otherwise ``2``.
    """
    # Normalise to forward slashes for consistent matching.
    p = path.replace("\\", "/").strip()

    # --- Tier 3 checks first (highest risk wins) ---
    if _T3_SECRETS.search(p):
        return 3
    if _T3_BILLING.search(p):
        return 3
    if _T3_DATA_OPS.search(p):
        return 3
    if _T3_ARCHITECTURE.search(p):
        return 3
    if _T3_CROSS_PACKAGE_INIT.match(p):
        return 3
    if _T3_ROUTING.search(p):
        return 3

    # --- Tier 1 checks ---
    if _T1_PATHS.match(p):
        return 1
    if _T1_TEST_FILE.search(p):
        return 1
    if _T1_SCRIPTS.match(p):
        return 1
    pure = PurePosixPath(p)
    if pure.suffix.lower() in _T1_EXTENSIONS:
        return 1
    if pure.name.lower() in _T1_FILENAMES:
        return 1

    # --- Tier 2 (default for application / library code) ---
    return 2


def get_changed_files(base_ref: str) -> list[str]:
    """Return the list of files changed between *base_ref* and HEAD.

    Parameters
    ----------
    base_ref:
        A git ref to diff against (branch, commit, or ``merge-base`` output).

    Returns
    -------
    list[str]
        Paths relative to the repository root, one per changed file.

    Raises
    ------
    subprocess.CalledProcessError
        When the git command fails.
    """
    result = subprocess.run(
        ["git", "diff", "--name-only", base_ref, "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def resolve_base_ref(branch: str = "develop") -> str:
    """Return the merge-base commit between HEAD and *branch*.

    Parameters
    ----------
    branch:
        The integration branch to find the merge-base with.

    Returns
    -------
    str
        The full SHA of the merge-base commit.

    Raises
    ------
    subprocess.CalledProcessError
        When the git command fails (e.g. branch does not exist).
    """
    result = subprocess.run(
        ["git", "merge-base", "HEAD", branch],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def classify_diff(files: list[str]) -> list[tuple[int, str]]:
    """Classify each path in *files* and return ``(tier, path)`` pairs.

    The list is sorted: Tier-3 entries first, then Tier-2, then Tier-1.

    Parameters
    ----------
    files:
        File paths relative to the repository root.

    Returns
    -------
    list[tuple[int, str]]
        Each entry is ``(tier_number, path)``, sorted by tier descending.
    """
    rated = [(classify_path(f), f) for f in files]
    rated.sort(key=lambda x: -x[0])
    return rated


def verdict(rated: list[tuple[int, str]]) -> tuple[int, str]:
    """Derive the overall verdict from a list of rated file paths.

    Parameters
    ----------
    rated:
        Output of :func:`classify_diff`.

    Returns
    -------
    tuple[int, str]
        ``(exit_code, verdict_text)`` where exit_code follows the module-level
        contract (0 = Tier 1, 1 = Tier 2, 2 = Tier 3, 3 = error).
    """
    if not rated:
        return 0, "VERDICT: Tier 1 — no changed files; agent may merge on green"
    top = rated[0][0]
    if top == 3:
        return 2, "VERDICT: Tier 3 — needs owner pre-approval before merge"
    if top == 2:
        return 1, "VERDICT: Tier 2 — agent drafts; owner uses then promotes develop→master"
    return 0, "VERDICT: Tier 1 — agent may merge on green"


def main(argv: list[str] | None = None) -> int:
    """Entry point for the merge-tier classifier.

    Parameters
    ----------
    argv:
        Argument list (defaults to ``sys.argv[1:]``).

    Returns
    -------
    int
        Exit code (0–3).
    """
    args = sys.argv[1:] if argv is None else argv

    try:
        if args:
            base_ref = args[0]
        else:
            base_ref = resolve_base_ref("develop")
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: could not resolve base ref — {exc.stderr.strip()}", file=sys.stderr)
        return 3

    try:
        files = get_changed_files(base_ref)
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: git diff failed — {exc.stderr.strip()}", file=sys.stderr)
        return 3

    rated = classify_diff(files)
    for tier, path in rated:
        print(f"TIER {tier}  {path}")

    code, text = verdict(rated)
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
