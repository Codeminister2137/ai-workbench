"""Dashboard top bar: badges stay with tabs; mobile keeps one scrollable tab row."""

from __future__ import annotations

from pathlib import Path

CSS_PATH = Path(__file__).resolve().parents[1] / "apps" / "workbench_dashboard" / "web" / "app.css"


def _css() -> str:
    return CSS_PATH.read_text(encoding="utf-8")


def test_tab_links_never_wrap_badges_onto_their_own_line() -> None:
    assert (
        "nav a { margin-right: var(--wb-space-5); text-decoration: none; white-space: nowrap; }"
        in _css()
    )


def test_mobile_media_query_keeps_single_scrollable_tab_row() -> None:
    css = _css()
    assert "@media (max-width: 700px)" in css
    assert "header { flex-wrap: wrap;" in css
    assert "nav { flex: 1 1 100%; overflow-x: auto; white-space: nowrap;" in css
