"""Company templates keep review markers and carry no real client data."""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "docs" / "company-templates"
LEGAL = {"sow-template.md", "nda-template.md", "contract-template.md", "invoice-template.md"}
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
LONG_DIGITS_RE = re.compile(r"\d{7,}")


def test_templates_carry_markers_and_no_real_data() -> None:
    files = sorted(TEMPLATES.glob("*-template.md"))
    assert len(files) == 5, [path.name for path in files]
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "[OWNER]" in text, path.name
        assert "DRAFT" in text, path.name
        assert not EMAIL_RE.search(text), f"{path.name}: real email?"
        assert not LONG_DIGITS_RE.search(text), f"{path.name}: real number?"
        if path.name in LEGAL:
            assert "[TO-VERIFY]" in text, path.name
