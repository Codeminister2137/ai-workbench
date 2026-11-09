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


PL_PAGES = ["index.html", "uslugi.html", "kontakt.html"]
EN_PAGES = ["en/index.html", "en/services.html", "en/contact.html"]


def test_pages_have_lang_structure_and_current_nav() -> None:
    for rel in PL_PAGES:
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert '<html lang="pl">' in text, rel
        assert text.count("<h1") == 1, rel
        assert 'aria-current="page"' in text, rel
    for rel in EN_PAGES:
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert '<html lang="en">' in text, rel
        assert text.count("<h1") == 1, rel
        assert 'aria-current="page"' in text, rel


def test_polish_pages_use_diacritics() -> None:
    must = {
        "index.html": ["Bielsko-Biała", "Żywiec", "najbardziej boli", "księgowość"],
        "uslugi.html": ["Łączenie", "wyłączeniami", "Czego nie robimy"],
        "kontakt.html": ["Imię i nazwisko", "Przedział budżetu"],
    }
    for rel, words in must.items():
        text = (ROOT / rel).read_text(encoding="utf-8")
        for word in words:
            assert word in text, (rel, word)


def test_no_placeholders_or_invented_team() -> None:
    banned = ["lorem", "TODO", "TBD", "our team", "nasz zespół", "Hungar", "HUF"]
    for page in sorted(ROOT.rglob("*.html")):
        lowered = page.read_text(encoding="utf-8").lower()
        for word in banned:
            assert word.lower() not in lowered, (page, word)


def test_offer_content_present() -> None:
    index = (ROOT / "index.html").read_text(encoding="utf-8")
    for needle in ["rozpoznanie", "stałej cenie", "Skoczów", "founding client"]:
        assert needle in index, needle
    services = (ROOT / "uslugi.html").read_text(encoding="utf-8")
    for needle in ["Czego nie robimy", "SOW", "RODO", "30–50%"]:
        assert needle in services, needle
    en_index = (ROOT / "en" / "index.html").read_text(encoding="utf-8")
    for needle in ["fixed price", "founding-client", "Skoczów"]:
        assert needle in en_index, needle


def test_stylesheet_defines_system() -> None:
    css = (ROOT / "style.css").read_text(encoding="utf-8")
    for needle in ["--accent", ".hero", ".lines", ".steps", ".faq", "@media", "focus-visible"]:
        assert needle in css, needle
    assert "#faf8f4" not in css  # no cream wash (taste rule)


def test_form_script_has_diacritics_and_budgets() -> None:
    script = (ROOT / "form.js").read_text(encoding="utf-8")
    assert "krótki tytuł" in script
    assert "Budżet i podsumowanie" in script
    assert "10–30k" in script  # grounding §9 PLN buckets


def test_pricing_copy_matches_intake_buckets() -> None:
    """FAQ ladder mirrors the form.js buckets; quotes stay confidential by default."""
    script = (ROOT / "form.js").read_text(encoding="utf-8")
    assert "10\u201330k" in script and "30\u201380k" in script  # PLN buckets, grounding \u00a79
    pl = (ROOT / "index.html").read_text(encoding="utf-8")
    for needle in [
        "10 tys. z\u0142",
        "10\u201330 tys. z\u0142",
        "30\u201380 tys. z\u0142",
        "nie publikujemy cennika",
    ]:
        assert needle in pl, needle
    en = (ROOT / "en" / "index.html").read_text(encoding="utf-8")
    for needle in ["\u20ac2k", "\u20ac2\u20135k", "\u20ac5\u201315k", "no price list"]:
        assert needle in en, needle
    pl_terms = (ROOT / "uslugi.html").read_text(encoding="utf-8")
    assert "poufna z zasady" in pl_terms
    en_terms = (ROOT / "en" / "services.html").read_text(encoding="utf-8")
    assert "confidential by default" in en_terms
