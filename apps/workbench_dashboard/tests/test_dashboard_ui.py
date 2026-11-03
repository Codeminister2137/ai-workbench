from __future__ import annotations

import re
from pathlib import Path

WEB_DIR = Path(__file__).parent.parent / "web"


def _read(name: str) -> str:
    return (WEB_DIR / name).read_text(encoding="utf-8")


def test_create_menu_hidden_rule_collapses_menu() -> None:
    """The author `display: flex` must not override the `hidden` attribute."""
    css = _read("app.css")
    assert re.search(r"#create-menu\[hidden\]\s*\{\s*display\s*:\s*none\s*;\s*\}", css)


def test_create_button_toggles_menu_hidden() -> None:
    """The + New button flips the menu's `hidden` property (wiring guard)."""
    js = _read("app.js")
    assert 'getElementById("create-btn")' in js
    assert re.search(r'getElementById\("create-menu"\)\.hidden\s*=\s*!', js, re.DOTALL)


def test_chat_cancel_does_not_create_session() -> None:
    """Cancelling the chat-title prompt must abort before the create POST."""
    js = _read("app.js")
    assert 'prompt("Chat title:", "Dashboard chat") || "Dashboard chat"' not in js
    assert re.search(
        r'const picked = prompt\("Chat title:.*?\);\s+if \(picked === null\) return;',
        js,
        re.DOTALL,
    )
    assert 'const title = picked || "Dashboard chat";' in js


def test_viewing_idea_does_not_mutate() -> None:
    """Opening an idea detail never transitions status by itself."""
    js = _read("app.js")
    assert "await markIdeaSeen(id, payload.item);" not in js


def test_mark_seen_button_drives_transition() -> None:
    """An explicit Mark seen button (new ideas only) posts reviewing."""
    js = _read("app.js")
    assert 'id="mark-seen-btn"' in js
    assert 'item.status === "new" ? `' in js
    assert "markIdeaSeen(id, item)" in js
    assert 'item.status !== "new"' in js
    assert 'status: "reviewing"' in js


def test_static_controls_have_titles() -> None:
    """Every static button and nav link carries a tooltip title."""
    html = _read("index.html")
    for tag in re.findall(r"<button\b[^>]*>", html):
        assert "title=" in tag, f"button without title: {tag}"
    nav_links = re.findall(r"<a\b[^>]*data-view[^>]*>", html)
    assert len(nav_links) == 7
    for tag in nav_links:
        assert "title=" in tag, f"nav link without title: {tag}"


def test_dynamic_buttons_have_titles() -> None:
    """Every button rendered by app.js templates carries a tooltip title."""
    js = _read("app.js")
    buttons = re.findall(r"<button\b[^>]*>", js)
    assert len(buttons) == 7  # +report-btn (run detail)
    for tag in buttons:
        assert "title=" in tag, f"button without title: {tag}"


def test_dynamic_inputs_and_selects_have_titles() -> None:
    """Text inputs/selects in templates have titles (radios use labels)."""
    js = _read("app.js")
    inputs = [tag for tag in re.findall(r"<input\b[^>]*>", js) if 'type="radio"' not in tag]
    assert len(inputs) == 4
    for tag in inputs:
        assert "title=" in tag, f"input without title: {tag}"
    selects = re.findall(r"<select\b[^>]*>", js)
    assert len(selects) == 1
    for tag in selects:
        assert "title=" in tag, f"select without title: {tag}"


def test_plan_detail_renders_fields_not_json() -> None:
    """Plan detail shows title/status/source/body instead of a JSON dump."""
    js = _read("app.js")
    assert "JSON.stringify(payload.item" not in js
    assert "Source: ${esc(plan.source)}" in js
    assert "<pre>${esc(plan.body" in js


def test_run_detail_has_report_section_and_button() -> None:
    """Run detail shows a report or a titled Generate-report button."""
    js = _read("app.js")
    assert 'id="report-btn"' in js
    assert 'title="Ask for a completion report for this run"' in js
    assert "/report-request" in js


def test_ideas_label_explains_triage() -> None:
    """The status card tells the owner what triage means."""
    js = _read("app.js")
    assert "untriaged." not in js
    assert "adopt, park, or decline" in js


def test_inbox_form_keeps_note_and_submit_below_choices() -> None:
    """Choice + note are independent; one submit covers the whole form."""
    js = _read("app.js")
    assert "Add a note (optional)..." in js
    assert "the note expands your choice" in js
    assert ">Submit answer</button>" in js
    assert 'title="Record your choice and note"' in js
    assert "<strong>Note:</strong>" in js
