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


def test_intake_form_wiring_matches_script() -> None:
    """Every element id form.js touches exists on both contact pages."""
    script = (ROOT / "form.js").read_text(encoding="utf-8")
    touched = set(re.findall(r'(?:el|val)\("([^"]+)"\)', script))
    assert len(touched) >= 15
    for page in (ROOT / "kontakt.html", ROOT / "en" / "contact.html"):
        text = page.read_text(encoding="utf-8")
        assert "form.js" in text, page
        for element_id in touched:
            assert f'id="{element_id}"' in text, (page, element_id)
