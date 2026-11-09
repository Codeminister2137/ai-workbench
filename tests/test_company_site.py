"""Company site skeleton: draft banners, working internal links."""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1] / "company-site"


def test_site_pages_carry_draft_banner_and_sound_links() -> None:
    pages = sorted(ROOT.rglob("*.html"))
    assert len(pages) == 6
    for page in pages:
        text = page.read_text(encoding="utf-8")
        lowered = text.lower()
        assert "draft" in lowered or "szkic" in lowered, page
        for link in re.findall(r'href="([^"]+)"', text):
            if link.startswith(("http", "mailto", "#")):
                continue
            assert (page.parent / link).exists(), (page, link)
