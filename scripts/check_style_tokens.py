"""Enforce shared style tokens for the dashboard CSS.

``app.css`` must reference ``style-tokens.css`` via ``var(--wb-*)`` and hold
no raw color or length literals. Media-query widths stay literal because
``var()`` is invalid there. Mirrors the skill-registry gate: ``--check``
exits nonzero with the violation list.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parents[1] / "apps" / "workbench_dashboard" / "web"
APP_CSS = WEB_DIR / "app.css"
TOKENS_CSS = WEB_DIR / "style-tokens.css"

HEX_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")
RGB_RE = re.compile(r"rgba?\(")
LENGTH_RE = re.compile(r"\d+(?:\.\d+)?(?:px|rem)\b")
VAR_USE_RE = re.compile(r"var\((--wb-[a-z0-9-]+)\)")
VAR_DEF_RE = re.compile(r"(--wb-[a-z0-9-]+)\s*:")


def check() -> list[str]:
    """Return violation strings; empty means the CSS honors the tokens."""
    violations: list[str] = []
    app = APP_CSS.read_text(encoding="utf-8")
    tokens = TOKENS_CSS.read_text(encoding="utf-8")
    for lineno, line in enumerate(app.splitlines(), start=1):
        if "@media" in line:
            continue
        if HEX_RE.search(line) or RGB_RE.search(line):
            violations.append(f"app.css:{lineno}: raw color literal (use var(--wb-*))")
        if LENGTH_RE.search(line):
            violations.append(f"app.css:{lineno}: raw px/rem literal (use var(--wb-*))")
    defined = set(VAR_DEF_RE.findall(tokens))
    used_in_app = set(VAR_USE_RE.findall(app))
    used_in_tokens = set(VAR_USE_RE.findall(tokens))
    for name in sorted(used_in_app - defined):
        violations.append(f"app.css: {name} used but not defined in style-tokens.css")
    for name in sorted(defined - used_in_app - used_in_tokens):
        violations.append(f"style-tokens.css: {name} defined but never used")
    return violations


def main(argv: list[str]) -> int:
    if argv != ["--check"]:
        print("usage: check_style_tokens.py --check", file=sys.stderr)
        return 2
    violations = check()
    for item in violations:
        print(item)
    if violations:
        return 1
    print("style tokens ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
