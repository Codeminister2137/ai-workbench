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


def test_create_cancel_never_posts() -> None:
    """Cancel backs out without POSTing; empty titles never POST either."""
    js = _read("app.js")
    assert 'id="create-cancel"' in js
    assert "history.back()" in js
    assert 'if (!title) { toast("Title is required", false); return; }' in js


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
    assert len(buttons) == 11  # +report/rename/delete/submit/create/cancel
    for tag in buttons:
        assert "title=" in tag, f"button without title: {tag}"


def test_dynamic_inputs_and_selects_have_titles() -> None:
    """Text inputs/selects in templates have titles (radios use labels)."""
    js = _read("app.js")
    inputs = [tag for tag in re.findall(r"<input\b[^>]*>", js) if 'type="radio"' not in tag]
    assert len(inputs) == 13  # +rename/create-form inputs, +4 list filters
    for tag in inputs:
        assert "title=" in tag, f"input without title: {tag}"
    selects = re.findall(r"<select\b[^>]*>", js)
    assert len(selects) == 3  # +inbox-type/idea-origin create selects
    for tag in selects:
        assert "title=" in tag, f"select without title: {tag}"


def test_plan_detail_renders_fields_not_json() -> None:
    """Plan detail shows title/status/source/body instead of a JSON dump."""
    js = _read("app.js")
    assert "JSON.stringify(payload.item" not in js
    assert "Source: ${esc(plan.source)}" in js
    assert "<pre>${gtext(plan.body" in js


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


def test_no_blocking_dialogs_in_create_flow() -> None:
    """Creation uses inline forms; no prompt()/confirm() may block the page."""
    js = _read("app.js")
    assert "prompt(" not in js
    assert "confirm(" not in js
    assert "renderCreate" in js
    assert 'id="create-cancel"' in js
    assert "Title is required" in js


def test_create_form_marks_required_and_optional() -> None:
    js = _read("app.js")
    assert "Title *" in js
    assert "(required)" in js
    assert "(optional)" in js


def test_inbox_detail_keeps_full_record() -> None:
    """Detail has fixed sections; the options recap only shows once closed."""
    js = _read("app.js")
    assert "<h3>Request</h3>" in js
    assert "<h3>Decision record</h3>" in js
    assert "<h3>Your choices</h3>" in js
    assert "No answer recorded yet." in js
    assert '(item.options || []).length && item.status === "closed"' in js
    assert "<strong>Note:</strong>" in js
    assert "Archive" in js


def test_glossary_explains_codes_on_hover() -> None:
    js = _read("app.js")
    assert "GLOSSARY" in js
    assert "<abbr title=" in js
    assert "gtext(plan.title" in js


def test_status_pills_have_css() -> None:
    css = _read("app.css")
    assert ".pill" in css
    assert ".st-new" in css
    assert ".st-closed" in css


def test_chat_thread_has_rename_and_two_click_delete() -> None:
    js = _read("app.js")
    assert 'id="rename-form"' in js
    assert "/rename" in js
    assert 'id="delete-btn"' in js
    assert "Confirm delete?" in js
    assert "/delete" in js


def test_ideas_list_shows_date() -> None:
    js = _read("app.js")
    assert "created_at" in js


def test_list_views_have_filter_boxes() -> None:
    """Plans/Runs/Inbox/Ideas lists filter client-side over fetched items."""
    js = _read("app.js")
    assert "function filterList(listId, query)" in js
    assert 'id="filter-plans"' in js
    assert 'title="Filter plans by text"' in js
    assert 'id="filter-runs"' in js
    assert 'title="Filter runs by text"' in js
    assert 'id="filter-inbox"' in js
    assert 'title="Filter inbox by text"' in js
    assert 'id="filter-ideas"' in js
    assert 'title="Filter ideas by text"' in js
    assert 'id="plans-list"' in js
    assert 'id="runs-list"' in js
    assert 'id="inbox-list"' in js
    assert 'id="ideas-list"' in js


def test_runs_list_auto_refresh_polls_while_visible() -> None:
    """Runs list re-polls /api/runs every ~10s; paused when hidden."""
    js = _read("app.js")
    assert "runsPollTimer" in js
    assert "stopRunsPoll" in js
    assert "startRunsPoll" in js
    assert "setInterval" in js
    assert "10000" in js
    assert "document.hidden" in js
    assert "prevFilter" in js
