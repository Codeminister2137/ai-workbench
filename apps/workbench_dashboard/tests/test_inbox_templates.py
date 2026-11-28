"""Inbox filing templates stay structured and referenced.

Decision bodies filed as one unbroken paragraph are unreadable (inbox
bef5d8d1); agents must copy the sectioned templates instead of compressing
the AGENTS.md brief format. These tests pin the template files, their
required sections, and the AGENTS.md pointer.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TEMPLATES = ROOT / "docs" / "inbox-templates"

REQUIRED = {
    "decision.md": (
        "Decision needed:",
        "Why it matters:",
        "Options:",
        "Pros and cons:",
        "Technical recommendation:",
        "Question:",
    ),
    "closeout.md": ("Owner answered", "Implement the answer"),
    "task.md": ("Goal:", "Context:", "Scope:", "Done when:"),
}

ALSO_PRESENT = {
    "closeout.md": ("Note:",),
}

_FENCE = "```text"


def _body(name: str) -> str:
    text = (TEMPLATES / name).read_text(encoding="utf-8")
    start = text.index(_FENCE) + len(_FENCE)
    end = text.index("```", start)
    return text[start:end].strip("\n")


def test_template_files_exist() -> None:
    assert TEMPLATES.is_dir()
    for name in REQUIRED:
        assert (TEMPLATES / name).is_file(), name


def test_templates_carry_required_sections() -> None:
    for name, headers in REQUIRED.items():
        body = _body(name)
        for header in headers:
            assert header in body, f"{name} missing {header!r}"
        for header in ALSO_PRESENT.get(name, ()):
            assert header in body, f"{name} missing {header!r}"


def test_template_sections_split_by_blank_lines() -> None:
    for name, headers in REQUIRED.items():
        body = _body(name)
        assert "\n\n" in body, f"{name} is one blob"
        for header in headers:
            pattern = re.compile(r"(?:^|\n\n)[^\n]*" + re.escape(header))
            assert pattern.search(body), f"{name}: {header!r} not on a blank-line boundary"


def test_agents_references_templates() -> None:
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "docs/inbox-templates/decision.md" in agents
