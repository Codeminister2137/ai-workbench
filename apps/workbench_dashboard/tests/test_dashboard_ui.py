from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

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
    assert (
        len(nav_links) == 16
    )  # +intake, +restrictions, +fleet, +providers, +help, +backlog, +knowme, +workflows
    for tag in nav_links:
        assert "title=" in tag, f"nav link without title: {tag}"


def test_dynamic_buttons_have_titles() -> None:
    """Every button rendered by app.js templates carries a tooltip title."""
    js = _read("app.js")
    buttons = re.findall(r"<button\b[^>]*>", js)
    assert (
        len(buttons) == 31
    )  # +report/rename/delete/submit/create/cancel/run-request/staged-approve/staged-reject/dictate/intake-approve/draft-plan/drain/reopen/providers-refresh/propose/backlog-groom/backlog-promote +8 workflow composer
    for tag in buttons:
        assert "title=" in tag, f"button without title: {tag}"


def test_dynamic_inputs_and_selects_have_titles() -> None:
    """Text inputs/selects in templates have titles (radios use labels)."""
    js = _read("app.js")
    inputs = [tag for tag in re.findall(r"<input\b[^>]*>", js) if 'type="radio"' not in tag]
    assert (
        len(inputs) == 29
    )  # +rename/create-form inputs, +5 list filters, +idea plan link, +task propose, +backlog filter/decision/create-title/create-ref, +restriction toggle, +8 workflow composer
    for tag in inputs:
        assert "title=" in tag, f"input without title: {tag}"
    selects = re.findall(r"<select\b[^>]*>", js)
    assert (
        len(selects) == 15
    )  # +create selects, +run-request pickers, +runs/inbox project filters, +agent-queue assignee, +backlog groom/create-source, +inbox close kind, +4 workflow composer
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


def test_backlog_tab_grooms_and_promotes() -> None:
    """Backlog list/detail groom items and file inbox briefs on demand."""
    js = _read("app.js")
    html = _read("index.html")
    assert 'data-view="backlog"' in html
    assert 'id="backlog-badge"' in html
    assert 'data-create="backlog"' in html
    assert "renderBacklog" in js
    assert "/api/backlog" in js
    assert 'id="promote-btn"' in js
    assert "/promote" in js
    assert "open_backlog" in js


def test_workflows_tab_composes_and_validates() -> None:
    """Workflows list links a composer that validates and saves new copies."""
    js = _read("app.js")
    html = _read("index.html")
    assert 'data-view="workflows"' in html
    assert "renderWorkflows" in js
    assert "/api/workflows/options" in js
    assert "/api/workflows/validate" in js
    assert 'id="wf-save"' in js
    assert "Save new copy" in js


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
    assert "Meta server + browser fallback" in js
    assert "no engine wired" not in js
    assert "Web Speech v1 live" not in js


def test_dictate_slices_and_falls_back() -> None:
    """Dictate auto-slices at 55 s and falls back to browser speech."""
    js = _read("app.js")
    assert "recorder.start(55000)" in js
    assert "transcribeSegment" in js
    assert "dictateViaBrowser" in js
    assert "window.SpeechRecognition || window.webkitSpeechRecognition" in js
    assert "Dictated via browser fallback" in js


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


def test_run_detail_shows_fanout_indicator() -> None:
    """Run detail shows one Fan-out indicator with a graceful fallback."""
    js = _read("app.js")
    assert "<strong>Fan-out:</strong>" in js
    assert 'run.fanout_effective || run.fanout_policy || "unknown"' in js


def test_runs_list_shows_fanout_pill() -> None:
    """Runs list rows carry the same fan-out indicator as the detail."""
    js = _read("app.js")
    assert 'fan-out: ${esc(r.fanout_effective || r.fanout_policy || "unknown")}' in js


def test_chat_thread_has_run_request_button() -> None:
    """Chat threads queue agent runs explicitly; the receipt shows fan-out."""
    js = _read("app.js")
    assert 'id="run-request-btn"' in js
    assert 'title="Queue this message as an agent run (needs inbox approval)"' in js
    assert "/run-request" in js
    assert "Run queued (fan-out: " in js
    assert "queue agent runs for approval from a thread" in js


def test_inbox_badge_polls_live_open_count() -> None:
    """The nav badge refreshes from /api/inbox on the ~10s cadence."""
    js = _read("app.js")
    assert "inboxPollTimer" in js
    assert "stopInboxPoll" in js
    assert "startInboxPoll" in js
    assert "pollInboxBadge" in js
    assert 'api("/api/inbox")' in js
    assert 't.status === "open"' in js
    assert "document.hidden" in js
    assert "10000" in js
    assert "startInboxPoll();" in js


def test_inbox_badge_never_auto_answers() -> None:
    """Badge refresh is a read-only GET; opening the inbox just re-renders."""
    js = _read("app.js")
    assert "inboxAckSeq" not in js
    assert "AckSeq" not in js
    # The poll path only reads; answers happen solely through the answer form.
    assert js.count("/answer") == 1  # the inbox answer-form POST only


def test_run_detail_polls_receipts_contract() -> None:
    """Run detail fetches GET /api/runs/{id}/receipts and degrades gracefully."""
    js = _read("app.js")
    assert '"/receipts"' in js
    assert "data.receipts" in js
    assert 'id="receipts-list"' in js
    assert "renderReceiptsInto" in js
    assert "No receipts yet." in js
    assert "Loading receipts..." in js
    assert "<h3>Events and receipts</h3>" in js


def test_receipts_render_collapsed_turn_groups() -> None:
    """Receipts render as collapsed per-turn disclosures, never a raw dump."""
    js = _read("app.js")
    assert "receiptHtml" in js
    assert '<details class="turn">' in js
    assert '"Turn " + rec.turn' in js
    css = _read("app.css")
    assert "details.turn" in css


def test_run_detail_auto_refreshes_while_visible() -> None:
    """Run detail re-reads status + receipts every ~10s; stops on navigate."""
    js = _read("app.js")
    assert "runDetailPollTimer" in js
    assert "stopRunDetailPoll" in js
    assert "startRunDetailPoll" in js
    assert "refreshRunDetail" in js
    assert 'id="run-status"' in js
    assert '"#/runs/" + id' in js
    assert "stopRunDetailPoll();" in js  # render() stops it on navigation


def test_plan_detail_renders_phase_checklist() -> None:
    """Plan detail shows a phase header + checklist with a graceful fallback."""
    js = _read("app.js")
    assert "phaseChecklistHtml" in js
    assert "plan.phases" in js
    assert 'id="phase-checklist"' in js
    assert "<strong>Phase:</strong>" in js
    assert "<h3>Phase checklist</h3>" in js
    assert "No phases recorded yet." in js
    css = _read("app.css")
    assert ".checklist" in css


def test_run_detail_renders_synthesis_and_diff() -> None:
    """Run detail shows Did/Found/Next synthesis and the diff when present."""
    js = _read("app.js")
    assert "synthesisHtml" in js
    assert 'id="run-synthesis"' in js
    assert '"Did"' in js and '"Found"' in js and '"Next"' in js
    assert "<h3>Diff</h3>" in js
    assert 'id="run-diff"' in js
    assert "run.diff" in js


def test_run_approval_links_to_inbox_only() -> None:
    """Approve/Reject affordance is a link to the inbox answer flow, nothing else."""
    js = _read("app.js")
    assert "run.inbox_id" in js
    assert '"#/inbox/${esc(run.inbox_id)}"' in js
    assert "Review approval in inbox" in js
    assert 'title="Approve or reject via the linked inbox task"' in js
    # No bare run/plan approve endpoint; staged-file approval is approve-staged.
    assert "/approve-staged" in js
    approvals = [line for line in js.splitlines() if '/approve"' in line]
    assert len(approvals) == 1 and "/api/intake/" in approvals[0]  # intake→draft-plan only
    assert "/reject" not in js


def test_chat_thread_has_project_picker() -> None:
    """Run requests can target a registered project; empty roots hide the picker."""
    js = _read("app.js")
    assert 'id="project-picker"' in js
    assert 'title="Project for the next run request (optional)"' in js
    assert 'id="project-note"' in js
    assert "loadProjectPicker" in js
    assert 'api("/api/work-roots")' in js
    assert "No project roots configured" in js
    assert "runs stay unscoped" in js
    assert "JSON.stringify({text, project, plan})" in js
    assert "No project (unscoped run)" in js


def test_run_detail_renders_staged_review() -> None:
    """Run detail reviews staged diffs with titled approve/reject buttons."""
    js = _read("app.js")
    assert "<h3>Staged project changes</h3>" in js
    assert 'id="staged-list"' in js
    assert "renderStagedInto" in js
    assert '"/staged"' in js
    assert "No staged changes." in js
    assert "Loading staged changes..." in js
    assert "stagedFileHtml" in js
    assert 'id="staged-approve-btn"' in js
    assert 'title="Approve and apply these staged files to the project root"' in js
    assert 'id="staged-reject-btn"' in js
    assert 'title="Reject these staged files (nothing is applied)"' in js
    assert "/approve-staged" in js
    assert "Staged changes applied" in js
    assert "Staged changes rejected" in js
    assert "data-applied" in js
    css = _read("app.css")
    assert ".staged-file" in css


def test_chat_thread_has_dictate_button() -> None:
    """Chat threads dictate via the transcribe endpoint with honest failure copy."""
    js = _read("app.js")
    assert 'id="dictate-btn"' in js
    assert 'title="Dictate with the microphone (Meta server first, browser fallback)"' in js
    assert "/api/stt/transcribe" in js
    assert "MediaRecorder" in js
    assert "Stop (recording...)" in js
    assert "Dictation failed: " in js
    assert "type instead" in js


def test_documents_view_lists_and_previews() -> None:
    """Documents tab lists all roots with badges, previews markdown, opens files."""
    html = _read("index.html")
    assert 'data-view="documents"' in html
    js = _read("app.js")
    assert "renderDocuments" in js
    assert 'id="filter-documents"' in js
    assert 'id="documents-list"' in js
    assert '"/api/documents"' in js
    assert "/file" in js
    assert "Open file" in js
    assert "Private files never leave this PC" in js


def test_document_preview_renders_markdown() -> None:
    """Doc preview renders markdown into a wrapped container, not a raw dump."""
    html = _read("index.html")
    md_pos = html.find('<script src="md.js"></script>')
    app_pos = html.find('<script src="app.js"></script>')
    assert md_pos != -1 and app_pos != -1 and md_pos < app_pos
    js = _read("app.js")
    assert "<pre>${esc(full.content)}</pre>" not in js
    assert "mdToHtml(full.content)" in js
    assert 'class="doc-body"' in js
    css = _read("app.css")
    assert ".doc-body" in css
    assert "pre-wrap" in css
    assert "overflow-wrap" in css


def test_ideas_archive_tab_and_backlog_markers() -> None:
    """Ideas list has Active/Archive tabs; archive shows plan links or archive-only."""
    js = _read("app.js")
    assert '<a href="#/ideas">Active</a>' in js
    assert '<a href="#/ideas?status=archive">Archive</a>' in js
    assert '["adopted", "parked", "declined"]' in js
    assert "archive-only" in js
    assert 'name="plan"' in js
    assert "plan_id: ev.target.plan.value || null" in js


def test_documents_archive_tab_and_pill() -> None:
    """Documents list has Active/Archive tabs on the archived flag."""
    js = _read("app.js")
    assert '<a href="#/documents">Active</a>' in js
    assert '<a href="#/documents?status=archive">Archive</a>' in js
    assert "d.archived" in js
    assert ">archived</span>" in js


def test_plans_and_runs_archive_tabs() -> None:
    """Plans and Runs lists have Active/Archive tabs on terminal statuses."""
    js = _read("app.js")
    assert '<a href="#/plans">Active</a>' in js
    assert '<a href="#/plans?status=archive">Archive</a>' in js
    assert 'p.status === "complete"' in js
    assert '<a href="#/runs">Active</a>' in js
    assert '<a href="#/runs?status=archive">Archive</a>' in js
    assert '["completed", "cancelled", "merged"]' in js


def test_help_view_and_nav_link() -> None:
    """Help view renders the runbook checklist + troubleshooting; nav links it."""
    js = _read("app.js")
    assert "function renderHelp()" in js
    assert 'name === "help"' in js
    assert "docs/company-run.md" in js
    assert "Troubleshooting" in js
    html = _read("index.html")
    assert 'href="#/help"' in html


def test_schedule_propose_form_posts_to_endpoint() -> None:
    """Schedule view has a free-text propose form wired to /api/tasks/propose."""
    js = _read("app.js")
    assert 'id="propose-form"' in js
    assert "/api/tasks/propose" in js
    assert "Nothing runs until you approve it" in js


def test_md_renderer_cases() -> None:
    """The doc markdown renderer covers blocks, inline code, links, and XSS."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required to execute the renderer")
    md_js = WEB_DIR / "md.js"
    assert md_js.is_file(), "web/md.js must exist for the documents preview"
    driver = (
        "const { mdToHtml } = require(process.argv[1]);\n"
        "const assert = require('assert');\n"
        "assert.strictEqual(mdToHtml('# Hi'), '<h1>Hi</h1>');\n"
        "assert.strictEqual(mdToHtml('# Hi\\r\\n\\r\\nBody\\r\\n'), '<h1>Hi</h1><p>Body</p>');\n"
        "assert.strictEqual(\n"
        "  mdToHtml('**b** and `c`'),\n"
        "  '<p><strong>b</strong> and <code>c</code></p>',\n"
        ");\n"
        "assert.strictEqual(\n"
        "  mdToHtml('[t](https://x.example/a)'),\n"
        '  \'<p><a href="https://x.example/a" rel="noopener">t</a></p>\',\n'
        ");\n"
        "assert.ok(!mdToHtml('[x](javascript:alert(1))').includes('javascript:'));\n"
        "assert.ok(!mdToHtml('[x](javascript:alert(1))').includes('<a '));\n"
        "assert.ok(mdToHtml('```\\n<a>\\n```').includes('&lt;a&gt;'));\n"
        "assert.ok(!mdToHtml('<img src=x onerror=y>').includes('<img'));\n"
        "assert.strictEqual(\n"
        "  mdToHtml('- a\\n- b'),\n"
        "  '<ul><li>a</li><li>b</li></ul>',\n"
        ");\n"
        "assert.strictEqual(\n"
        "  mdToHtml('- aaa\\nbbb\\n- c'),\n"
        "  '<ul><li>aaa bbb</li><li>c</li></ul>',\n"
        ");\n"
        "assert.strictEqual(\n"
        "  mdToHtml('- a\\n\\npara'),\n"
        "  '<ul><li>a</li></ul><p>para</p>',\n"
        ");\n"
        "assert.ok(mdToHtml('a'.repeat(500)).includes('a'.repeat(500)));\n"
        "assert.strictEqual(\n"
        "  mdToHtml('| a | b |\\n|---|---|\\n| 1 | 2 |'),\n"
        "  '<table><thead><tr><th>a</th><th>b</th></tr></thead>'\n"
        "    + '<tbody><tr><td>1</td><td>2</td></tr></tbody></table>',\n"
        ");\n"
        "console.log('md cases ok');\n"
    )
    proc = subprocess.run(
        [node, "-e", driver, str(md_js)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_inbox_supports_owner_tasks() -> None:
    """Task items are creatable and carry do-the-steps guidance, no new controls."""
    js = _read("app.js")
    assert '<option value="task">task</option>' in js
    assert 'item.type === "task"' in js
    assert "answer Done with a note" in js
    assert "Never paste secrets here" in js
    assert "assigns decisions and tasks to the inbox" in js


def test_chat_send_refreshes_thread_on_failure() -> None:
    """Failed turns still re-render the thread (messages are saved anyway)."""
    js = _read("app.js").replace("\r\n", "\n")
    assert "} finally {\n      render();\n      btn.disabled = false;" in js


def test_create_form_disables_submit_while_creating() -> None:
    """Double-clicking Create cannot create duplicate items."""
    js = _read("app.js")
    assert 'ev.target.querySelector("button[type=submit]")' in js
    assert "createBtn.disabled = true;" in js
    assert "createBtn.disabled = false;" in js


def test_restrictions_view_is_read_only_overview() -> None:
    """Restrictions tab defines dimensions without fabricating live posture."""
    html = _read("index.html")
    assert 'data-view="restrictions"' in html
    js = _read("app.js")
    assert "renderRestrictions" in js
    assert 'name === "restrictions"' in js
    for dimension in (
        "Outbound network",
        "Filesystem writes",
        "Secret handling",
        "Subprocess execution",
        "Delegation scope",
        "Human approval gates",
    ):
        assert dimension in js
    assert js.count("not yet evaluated") == 7  # intro + one per dimension
    assert "Would be fed by" in js


def test_sticky_header_is_opaque() -> None:
    css = _read("app.css")
    m = re.search(r"header\s*\{[^}]*\}", css, re.DOTALL)
    assert m, "header rule not found"
    rule = m.group(0)
    assert "background: var(--wb-color-surface)" in rule
    tokens = _read("style-tokens.css")
    assert "--wb-color-surface: Canvas" in tokens
    assert "background: inherit" not in rule
    assert "z-index" in rule


def test_inbox_close_form_and_reopen_markers() -> None:
    """Detail page records outcomes on close and offers reopen when closed."""
    js = _read("app.js")
    assert 'id="close-form"' in js
    assert 'name="resolution"' in js
    assert "/close" in js and "resolution:" in js
    assert 'id="reopen-btn"' in js
    assert "/reopen" in js
    assert "<h3>Outcome</h3>" in js
    assert "#/inbox?status=archive" in js


def test_home_shows_spend_card() -> None:
    """Home renders a Spend card backed by /api/spend with an empty state."""
    js = _read("app.js")
    assert "<h2>Spend</h2>" in js
    assert 'await api("/api/spend")' in js
    assert "No spend grants configured" in js


def test_fleet_tab_markers() -> None:
    """Fleet tab is wired: nav, route, live endpoint, sections."""
    js = _read("app.js")
    html = _read("index.html")
    assert 'data-view="fleet"' in html
    assert 'name === "fleet"' in js
    assert 'await api("/api/fleet")' in js
    assert "<h2>Watchdog tasks</h2>" in js
    assert "<h2>Active runs</h2>" in js
    assert "<h2>Sleep guard</h2>" in js


def test_schedule_tab_markers() -> None:
    """Schedule tab is wired: nav, route, live endpoint, sections."""
    js = _read("app.js")
    html = _read("index.html")
    assert 'data-view="schedule"' in html
    assert 'name === "schedule"' in js
    assert "async function renderSchedule()" in js
    assert "<h2>Upcoming</h2>" in js
    assert "<h2>Recurring</h2>" in js
    assert "sleep guard due" in js


def test_run_failure_banner_markers() -> None:
    """Run detail shows a failure banner fed by the derived failure field."""
    js = _read("app.js")
    css = _read("app.css")
    assert "run.failure" in js
    assert "Run failed" in js
    assert "No reason recorded." in js
    assert ".st-failed" in css


def test_inbox_and_idea_bodies_preserve_line_breaks() -> None:
    """Long bodies must not collapse into one block (owner readability fix)."""
    css = _read("app.css")
    assert re.search(r"\.inbox-body\s*\{\s*white-space\s*:\s*pre-wrap\s*;\s*\}", css)
    js = _read("app.js")
    assert js.count('<p class="inbox-body">') >= 3  # request, outcome, idea
    assert "<p>${gtext(item.body" not in js
    assert "<p>${gtext(item.resolution)}" not in js


def test_spend_card_renders_policy() -> None:
    """Spend card shows order, prepaid-today, and rules."""
    js = _read("app.js")
    assert "spend.policy" in js
    assert "prepaid-if-allowed" in js
    assert "Prepaid today" in js


def test_providers_view_markers_present() -> None:
    """Providers route, cards, refresh action, and nav link exist."""
    js = _read("app.js")
    assert "renderProviders" in js
    assert "#/providers" not in js  # route dispatch uses the bare name
    assert 'name === "providers"' in js
    assert "/api/providers" in js
    assert "/api/providers/refresh" in js
    assert "providers-refresh" in js
    assert "Log in / register at" in js
    html = _read("index.html")
    assert 'data-view="providers"' in html


def test_schedule_and_fleet_use_readable_times_and_explanations() -> None:
    """fmtTime helper exists and schedule/fleet render it plus explanations."""
    js = _read("app.js")
    assert "function fmtTime(value)" in js
    assert "fmtTime(t.next_run)" in js
    assert "fmtTime(f.sleep.due_utc)" in js
    assert "fmtTime(t.last_run)" in js
    assert "t.explain" in js
    assert "f.sleep.explain" in js
    assert "f.dashboard.explain" in js
    assert "f.ollama.explain" in js


def test_restrictions_renders_live_subprocess_counts() -> None:
    """Restrictions tab fetches /api/restrictions for live run counts."""
    js = _read("app.js")
    assert "async function renderRestrictions()" in js
    assert "/api/restrictions" in js
    assert "run request(s) recorded" in js
    assert "not yet evaluated" in js


def test_inbox_followup_mark_stays_out_of_archive() -> None:
    """Follow-up closes are marked and excluded from the archive tab."""
    js = _read("app.js")
    assert 'name="resolution_kind"' in js
    assert "No final answer" in js
    assert "const isFollowup = (t)" in js
    assert 't.status === "closed" && !isFollowup(t)' in js
    assert '(t.status !== "closed" || isFollowup(t))' in js
    assert "needs follow-up" in js
    assert "Marked for follow-up, kept in Active" in js
