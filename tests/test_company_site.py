"""Company site skeleton: draft banners, working internal links."""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1] / "company-site"


def test_site_pages_carry_draft_banner_and_sound_links() -> None:
    pages = sorted(ROOT.rglob("*.html"))
    assert len(pages) == 8
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


PL_PAGES = ["index.html", "uslugi.html", "kontakt.html", "prywatnosc.html"]
EN_PAGES = ["en/index.html", "en/services.html", "en/contact.html", "en/privacy.html"]


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
    for needle in ["Czego nie robimy", "SOW", "RODO", "30–50%", "najlżejszego pasującego"]:
        assert needle in services, needle
    en_services = (ROOT / "en" / "services.html").read_text(encoding="utf-8")
    assert "lightest fix that fits" in en_services
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


def test_form_lead_uses_p7_vocabulary() -> None:
    """form.js leads carry P7 identity keys for the enrichment step."""
    script = (ROOT / "form.js").read_text(encoding="utf-8")
    for needle in (
        'format_version: "1.0.0"',
        "project_id: projectId(",
        "created_at: utcStamp(",
        'capture_method: "human"',
    ):
        assert needle in script, needle
    # Strict UTC shape (no millis) satisfies schema.json + both validators.
    assert '.replace(/\\.\\d{3}Z$/, "Z")' in script


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


def test_placeholders_indexed() -> None:
    """Every PLACEHOLDER(ID) marker in HTML has a ## ID index entry."""
    index = (ROOT / "PLACEHOLDERS.md").read_text(encoding="utf-8")
    found: set[str] = set()
    for page in sorted(ROOT.rglob("*.html")):
        for marker in re.findall(r"PLACEHOLDER\(([A-Z_]+)\)", page.read_text(encoding="utf-8")):
            found.add(marker)
            assert f"## {marker}" in index, (page, marker)
    # COMPANY_NAME resolved 26.11 (BeskidLogic); the rest still gate launch.
    assert found >= {"CONTACT_EMAIL", "SERVICE_CITIES"}


def test_brand_and_seller_identity_final() -> None:
    """Brand BeskidLogic + NIP/REGON on every page (owner 26.11)."""
    for page in sorted(ROOT.rglob("*.html")):
        text = page.read_text(encoding="utf-8")
        assert "BeskidLogic" in text, page
        assert "5482782178" in text, page
        assert "546248869" in text, page
        assert "Mickiewicza 25, 43-430 Skoczów" in text, page
        assert "Firma IT" not in text, page
        assert "IT studio" not in text, page


def test_privacy_notice_covers_controller_rights_and_routes() -> None:
    """RODO notice: controller, local-only claims, rights, UODO path."""
    pl = (ROOT / "prywatnosc.html").read_text(encoding="utf-8")
    for needle in [
        "Jakub Jaworski BeskidLogic",
        "wysyła je na nasz serwer",
        "numer referencyjny",
        "w całości w Twojej przeglądarce",
        "art. 6 ust. 1 lit. b RODO",
        "24 miesiące",
        "Prezesa Urzędu Ochrony Danych Osobowych",
        "Nie profilujemy",
    ]:
        assert needle in pl, needle
    en = (ROOT / "en" / "privacy.html").read_text(encoding="utf-8")
    for needle in [
        "Jakub Jaworski BeskidLogic",
        "sends it to our server",
        "reference number",
        "entirely in your browser",
        "Art. 6(1)(b)",
        "24 months",
        "UODO",
        "do not profile",
    ]:
        assert needle in en, needle


def test_every_page_links_privacy_notice() -> None:
    """The notice is one click from anywhere (Art. 5 accessible place)."""
    for rel in PL_PAGES:
        assert 'href="prywatnosc.html"' in (ROOT / rel).read_text(encoding="utf-8"), rel
    for rel in EN_PAGES:
        assert 'href="privacy.html"' in (ROOT / rel).read_text(encoding="utf-8"), rel


def test_dark_mode_follows_browser_setting() -> None:
    """Dark tokens activate via prefers-color-scheme; controls stay readable."""
    css = (ROOT / "style.css").read_text(encoding="utf-8")
    assert "color-scheme: light dark" in css
    assert "@media (prefers-color-scheme: dark)" in css
    dark = css.split("@media (prefers-color-scheme: dark)", 1)[1]
    for token in ("--paper:", "--ink:", "--muted:", "--line:", "--accent:"):
        assert token in dark, token
    assert ".button {" in dark


def test_chatbot_wired_on_all_pages() -> None:
    """Every page loads the deterministic FAQ bot (chatbot.js)."""
    assert (ROOT / "chatbot.js").is_file()
    for rel in PL_PAGES:
        assert '<script src="chatbot.js"></script>' in (ROOT / rel).read_text(encoding="utf-8"), rel
    for rel in EN_PAGES:
        assert '<script src="../chatbot.js"></script>' in (ROOT / rel).read_text(
            encoding="utf-8"
        ), rel


def test_chatbot_knowledge_grounded_in_site_copy() -> None:
    """Every KB entry cites a source page + exact quote found there.

    This is the mechanical no-invention rule: answers may only restate
    quoted site content (or the P7 knowledge bank for the fallback).
    """
    script = (ROOT / "chatbot.js").read_text(encoding="utf-8")
    pairs = re.findall(r'source(_en)?: "([^"]+)", quote(_en)?: "((?:[^"\\]|\\.)*)"', script)
    assert len(pairs) >= 16, f"expected 8 entries x PL/EN, got {len(pairs)}"
    ids = re.findall(r'\n\s+id: "([a-z]+)",', script)
    assert len(ids) == len(set(ids)) >= 8, ids
    for _suffix, source, _qsuffix, quote in pairs:
        page = (ROOT / source).read_text(encoding="utf-8")
        assert quote in page, (source, quote)


def test_chatbot_fallback_links_intake_form() -> None:
    """Unknown input falls back to the form link, never an invented answer."""
    script = (ROOT / "chatbot.js").read_text(encoding="utf-8")
    assert "nie znam odpowiedzi" in script.lower() or "Nie znam odpowiedzi" in script
    assert "rather than invent one" in script
    assert '"kontakt.html"' in script and '"contact.html"' in script
    # No network, no model, no eval: static matcher by construction.
    for banned in ["fetch(", "XMLHttpRequest", "eval(", "WebSocket"]:
        assert banned not in script, banned


def test_chatbot_styles_defined() -> None:
    css = (ROOT / "style.css").read_text(encoding="utf-8")
    for needle in [".chat-fab", ".chat-panel", ".chat-msgs", ".chat-form", ".chat-msg"]:
        assert needle in css, needle


def test_intake_collects_optional_client_phone() -> None:
    """Owner a1a7b4bf (email-only): the form collects the client's number."""
    script = (ROOT / "form.js").read_text(encoding="utf-8")
    assert 'phone: val("f-phone")' in script
    assert "PHONE_RE" in script and "badPhone" in script
    for page in (ROOT / "kontakt.html", ROOT / "en" / "contact.html"):
        text = page.read_text(encoding="utf-8")
        assert 'id="f-phone"' in text, page
        assert 'type="tel"' in text, page


def test_contact_pages_show_email_placeholder() -> None:
    pl = (ROOT / "kontakt.html").read_text(encoding="utf-8")
    assert "adres w przygotowaniu" in pl
    en = (ROOT / "en" / "contact.html").read_text(encoding="utf-8")
    assert "address pending" in en


def test_discovery_floor_pl_only() -> None:
    """D4 followup (owner B): PL publishes the remote-discovery floor; EN silent."""
    pl = (ROOT / "uslugi.html").read_text(encoding="utf-8")
    for needle in ["od 1 tys. z\u0142", "rozmowa wideo", "wyceniana osobno"]:
        assert needle in pl, needle
    en = (ROOT / "en" / "services.html").read_text(encoding="utf-8")
    for token in ["tys", "z\u0142", "PLN", "\u20ac", "EUR", "1,000", "1 000"]:
        assert token not in en, token
