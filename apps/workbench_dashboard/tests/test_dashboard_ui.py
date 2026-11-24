from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

WEB_DIR = Path(__file__).parent.parent / "web"


def _read(name: str) -> str:
    return (WEB_DIR / name).read_text(encoding="utf-8")


def test_knowme_groups_entries_without_rewriting_facts() -> None:
    driver = r"""
const assert = require('assert');
const source = require('fs').readFileSync(process.argv[1], 'utf8');
const renderer = source.slice(source.indexOf('async function renderKnowme()'),
  source.indexOf('async function renderRestrictions()'));
const esc = eval('(' + source.slice(source.indexOf('function esc('),
  source.indexOf('\n}', source.indexOf('function esc(')) + 2) + ')');
const view = {innerHTML: ''};
const location = {hash: '#/knowme'};
let entries = [
  {category: 'career', text: 'Earlier role', source: 'import'},
  {category: 'skills', text: 'Python\nSQL <script>', source: '<import>'},
  {category: 'note', text: 'Unclassified fact', source: 'note'},
  {category: 'skills', text: 'Testing', source: 'interview'},
];
let requested;
const api = async (path) => {requested = path; return {count: 70, entries};};
eval(renderer);
(async () => {
  await renderKnowme();
  const html = view.innerHTML;
  assert(html.indexOf('<h2>Skills (2)') < html.indexOf('<h2>Career path (1)'));
  assert(html.indexOf('<h2>Career path (1)') < html.indexOf('<h2>Notes (1)'));
  assert(html.indexOf('Python') < html.indexOf('Testing'));
  assert(html.includes('Python\nSQL &lt;script&gt;'));
  assert(html.includes('Source: &lt;import&gt;'));
  assert(html.includes('Showing 4 of 70'));
  assert.equal((html.match(/<li>/g) || []).length, 4);
  location.hash = '#/knowme?category=skills';
  entries = entries.filter(e => e.category === 'skills');
  await renderKnowme();
  assert.equal(requested, '/api/knowme?category=skills');
  assert(view.innerHTML.includes('aria-current="page">Skills'));
  assert(!view.innerHTML.includes('<h2>Career path'));
  entries = [];
  await renderKnowme();
  assert(view.innerHTML.includes('No entries in this view'));
  assert(!view.innerHTML.includes('<section'));
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
    _run_node_driver(driver)
    assert "white-space: pre-wrap" in _read("app.css")


def _node_driver() -> str:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for card rendering")
    return node


def _run_node_driver(driver: str) -> None:
    """Run an app.js assertion driver with shared Node discovery and diagnostics."""
    result = subprocess.run(
        [_node_driver(), "-e", driver, str(WEB_DIR / "app.js")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_spend_card_renders_dollars_policy_editor_and_adjust() -> None:
    driver = r"""
const assert = require('assert');
const source = require('fs').readFileSync(process.argv[1], 'utf8');
const esc = eval('(' + source.slice(source.indexOf('function esc('),
  source.indexOf('\n}', source.indexOf('function esc(')) + 2) + ')');
const fns = source.slice(source.indexOf('function spendDollars'),
  source.indexOf('function collectSpendPolicyRules'));
eval(fns);
const spend = {configured: true, open_reservations: 0, records: 1,
  buckets: [{id: 'g', provider: 'meta', kind: 'allowance_expiring',
    balance_cents: 8836, granted_cents: 15000, status: 'active'}],
  policy_scopes: ['global', 'meta'],
  policy: {rules: [{scope: 'meta', prepaid_allowed: true, max_prepaid_cents: 500}],
    prepaid_spent_total_cents: 100}};
const html = spendCardHtml(spend);
assert(html.includes('$88.36 left of $150.00'), 'buckets in dollars');
assert(html.includes('meta: prepaid allowed, cap $5.00 total'), 'rule dollars');
assert(html.includes('Prepaid spent: $1.00 total'), 'prepaid total');
assert(html.includes('id="spend-policy-form"'), 'policy form');
assert(html.includes('<option value="meta" selected>meta</option>'), 'scope select');
assert(html.includes('value="5.00"'), 'cap input dollars');
assert(html.includes('id="spend-adjust-form"'), 'adjust form');
assert(html.includes('name="remaining"'), 'remaining input');
const off = spendCardHtml({configured: false});
assert(off.includes('denied by default'), 'unconfigured denial');
"""
    _run_node_driver(driver)


def test_provider_card_renders_quota_windows() -> None:
    driver = r"""
const assert = require('assert');
const source = require('fs').readFileSync(process.argv[1], 'utf8');
const esc = eval('(' + source.slice(source.indexOf('function esc('),
  source.indexOf('\n}', source.indexOf('function esc(')) + 2) + ')');
const dollars = source.slice(source.indexOf('function spendDollars'),
  source.indexOf('function spendPolicyScopes'));
const cards = source.slice(source.indexOf('function providerStatusPill'),
  source.indexOf('async function renderProviders'));
eval(dollars + '\n' + cards);
const codex = {route: 'codex', display: 'Codex', blurb: '', site_url: '',
  account_required: true, key_configured: true, reachable: true, auth_ok: true,
  model_count: null, sample_ids: [], latency_ms: null,
  checked_at: '2026-11-17T18:00:00+00:00', error: null,
  allowance_windows: [
    {bucket_id: 'codex', window: 'primary', used_percent: 9, resets_at_unix_seconds: 1794940759},
    {bucket_id: 'codex', window: 'secondary', used_percent: 17, resets_at_unix_seconds: 1795123314},
  ]};
const html = providerCardHtml(codex, []);
assert(html.includes('quota read'), 'codex pill');
assert(html.includes('5-hour'), 'primary label');
assert(html.includes('weekly'), 'secondary label');
assert(html.includes('9% used'), 'used percent');
assert(html.includes('Codex CLI login detected'), 'login line');
const down = providerCardHtml({...codex, reachable: false, key_configured: false,
  checked_at: '2026-11-17T18:00:00+00:00', allowance_windows: [], error: 'client_unavailable'}, []);
assert(down.includes('CLI unreachable'), 'down pill');
assert(down.includes('Quota windows: none reported'), 'empty quota');
const occ = {route: 'opencode_go', display: 'OpenCode', blurb: '', site_url: '',
  account_required: true, key_configured: true, reachable: true, auth_ok: true,
  model_count: 5, sample_ids: [], latency_ms: null, checked_at: '2026-11-17T18:00:00+00:00',
  error: null, allowance_windows: [
    {bucket_id: 'go_weekly', window: 'weekly', used_percent: 17, resets_at: '2026-11-24T00:00:00+00:00'},
  ]};
const ohtml = providerCardHtml(occ, []);
assert(ohtml.includes('weekly'), 'opencode label');
assert(ohtml.includes('17% used'), 'opencode used');
"""
    _run_node_driver(driver)


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
    assert len(nav_links) == 23  # 19 + modules tab + E2E tab + jobs (spend merged into providers)
    for tag in nav_links:
        assert "title=" in tag, f"nav link without title: {tag}"


def test_dynamic_buttons_have_titles() -> None:
    """Every button rendered by app.js templates carries a tooltip title."""
    js = _read("app.js")
    buttons = re.findall(r"<button\b[^>]*>", js)
    assert (
        len(buttons) == 64
    )  # +doc pin; +fanout apply; +delete-inbox-btn +e2e submit +chat mode/apply/approve +notes save +agent-check run +agent-config save +spend-policy add/save/remove +spend-adjust record +backlog to-task +jobs submit +report acknowledge +id lookup +bug dialog (2) +orchestrator query
    for tag in buttons:
        assert "title=" in tag, f"button without title: {tag}"


def test_dynamic_inputs_and_selects_have_titles() -> None:
    """Text inputs/selects in templates have titles (radios use labels)."""
    js = _read("app.js")
    inputs = [tag for tag in re.findall(r"<input\b[^>]*>", js) if 'type="radio"' not in tag]
    assert (
        len(inputs) == 69
    )  # +bad-test checkbox; +agent-enable checkbox; +spend-policy prepaid/cap (scope is a select); +spend-adjust remaining; step radios excluded; +jobs form (6); +id lookup; +bug report view/consent (2)
    for tag in inputs:
        assert "title=" in tag, f"input without title: {tag}"
    selects = re.findall(r"<select\b[^>]*>", js)
    assert (
        len(selects) == 29
    )  # +restrictions fan-out; +run fanout; +landing-page select; +agent policy; +spend-policy scope; +spend-adjust allowance; +jobs work-mode/type
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


def test_run_detail_fanout_control_for_pending_runs() -> None:
    """Run detail offers a fan-out selector on queued/paused runs only."""
    js = _read("app.js")
    assert 'id="fanout-select"' in js
    assert 'id="fanout-apply-btn"' in js
    assert 'title="Fan-out policy for this run"' in js
    assert 'title="Apply fan-out policy to this run"' in js
    assert '"/api/runs/" + encodeURIComponent(id) + "/fanout"' in js
    assert 'run.status === "queued" || run.status === "paused"' in js
    assert "Fan-out updated" in js


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


def test_projects_tab_manages_books() -> None:
    """Projects list/detail registers roots and files manuscript checks."""
    js = _read("app.js")
    html = _read("index.html")
    assert 'data-view="projects"' in html
    assert "renderProjects" in js
    assert "/manuscript" in js
    assert "Request check" in js
    assert "do not rewrite prose" not in js  # framing lives server-side


def test_meetings_tab_uploads_and_confirms_analysis() -> None:
    """Meetings list/detail uploads audio and gates analysis on confirmation."""
    js = _read("app.js")
    html = _read("index.html")
    assert 'data-view="meetings"' in html
    assert "renderMeetings" in js
    assert "/api/meetings/transcribe" in js
    assert "/analyze" in js
    assert "external model providers" in js


def test_ideas_remains_accessible_in_library() -> None:
    """Ideas remains reachable after the Home status card is replaced."""
    js = _read("app.js")
    assert "untriaged." not in js
    assert 'data-view="ideas"' in _read("index.html")


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
    assert 'title="Queue this message as an agent run (owner pre-approved)"' in js
    assert "/run-request" in js
    assert "Run queued (fan-out: " in js
    assert "queue pre-approved agent runs from a thread" in js


def test_inbox_badge_polls_live_attention_count() -> None:
    """The nav badge refreshes the status attention count on the ~10s cadence."""
    js = _read("app.js")
    assert "inboxPollTimer" in js
    assert "stopInboxPoll" in js
    assert "startInboxPoll" in js
    assert "pollInboxBadge" in js
    assert 'api("/api/status")' in js
    assert "await refreshBadge();" in js
    assert "status.attention_inbox ?? status.open_inbox" in js
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


def test_plans_list_shows_kind_and_linked_plans() -> None:
    """Roadmaps sort first with a kind pill; detail links child plans."""
    js = _read("app.js")
    assert 'kindOf(a) === "roadmap"' in js
    assert "<h3>Linked plans</h3>" in js
    assert "/api/plans?parent_plan_id=" in js


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


def test_e2e_tab_checks_and_submits() -> None:
    """E2E list/detail files per-behavior verdicts; reports show warnings."""
    html = _read("index.html")
    assert 'data-view="e2e"' in html
    assert 'id="e2e-badge"' in html
    js = _read("app.js")
    assert "renderE2E" in js
    assert 'name === "e2e"' in js
    assert "/api/e2e/tasks" in js
    assert "/api/e2e/reports" in js
    assert 'id="e2e-form"' in js
    assert "Submit E2E results" in js
    assert 'value="pass"> Pass' in js
    assert 'value="fail"> Fail' in js
    assert "Every behavior needs a pass/fail verdict" in js
    assert "not re-tested" not in js  # warning text is server-rendered data
    assert "open_e2e" in js
    assert "Record: what changed" in js
    assert "How to test" in js
    assert "Expected:" in js
    assert "Look at:" in js
    assert "Every step needs a pass/fail verdict" in js
    assert "Flag bad test design" in js
    assert 'input[name="badtest-' in js
    assert "Describe what is wrong with the test" in js
    assert 'data-agent-check="${esc(entry.id)}:' in js
    assert "Run this exact command agent-side and attach the output" in js
    assert "Agent evidence attached — review it, then verdict" in js
    assert ".st-bad-test" in _read("app.css")
    assert "Draft — waiting on pointers" in js
    assert "Recent verdicts for this area (all merges)" in js
    assert "Previously:" not in js
    assert "whatHtml(entry, true)" in js  # subjects on every item, not just the first
    assert "renderE2EReminders" in js
    assert "Test needed while you are here" in js
    assert "view.append(card)" in js  # reminders sit below tab content, never on top
    assert "data-save-notes" in js
    assert "Jot down what you observe" in js


def test_chat_agent_mode_toggle_and_staged() -> None:
    """Chat offers Ask/Agent toggle plus staged review/apply when enabled."""
    js = _read("app.js")
    assert "mode-ask-btn" in js
    assert "mode-agent-btn" in js
    assert "/mode" in js
    assert "Staged files" in js
    assert "data-apply" in js
    assert "apply-all-btn" in js
    assert "/apply" in js
    assert "agent_enabled" in js
    assert "approve-turn-btn" in js
    assert "reject-turn-btn" in js
    assert "Parked turn" in js
    assert "__chatHeartbeat" in js
    assert "chat-working-line" in js
    assert "Agent working in scratch worktree" in js
    assert "prefers-reduced-motion" in js


def test_documents_view_key_pins() -> None:
    """Documents rows carry pin toggles wired to the pins endpoint."""
    js = _read("app.js")
    assert 'data-pin-doc="${esc(d.id)}"' in js
    assert '"/api/documents/pins"' in js
    assert "Key documents updated" in js
    assert "Pin as key document" in js


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
    """Ideas list filters Triage/Decided boxes; decided-only keeps the mark."""
    js = _read("app.js")
    assert 'filterBoxes("ideas-filters"' in js
    assert '"new,reviewing"' in js
    assert '["new", "reviewing"]' in js
    assert "archive-only" in js
    assert 'name="plan"' in js
    assert "plan_id: ev.target.plan.value || null" in js


def test_documents_archive_tab_and_pill() -> None:
    """Documents list filters Current/Archived boxes on the archived flag."""
    js = _read("app.js")
    assert 'filterBoxes("documents-filters"' in js
    assert "d.archived" in js
    assert ">archived</span>" in js


def test_plans_and_runs_archive_tabs() -> None:
    """Plans and Runs lists filter boxes over their terminal statuses."""
    js = _read("app.js")
    assert 'filterBoxes("plans-filters"' in js
    assert 'p.status === "complete"' in js
    assert 'filterBoxes("runs-filters"' in js
    assert '"failed,running,queued,paused,waiting,approved"' in js


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
    assert "Queue a one-shot run" in js
    assert "recurring Windows tasks, a separate thing" in js


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
    assert "tick Closed to see the archive" in js


def test_chat_send_refreshes_thread_on_failure() -> None:
    """Failed turns still re-render the thread (messages are saved anyway)."""
    js = _read("app.js").replace("\r\n", "\n")
    assert "} finally {\n      if (timer) clearInterval(timer);" in js
    assert "if (progressTimer) clearInterval(progressTimer);\n      render();" in js
    assert "payload.error || payload.failure_reason ||" in js


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
    assert '["closed", "Closed"' in js


def test_inbox_checkbox_filters_default_human_attention() -> None:
    """Inbox mixes Who/State/Kind checkboxes; default is human attention, no reports."""
    js = _read("app.js")
    assert 'filterBoxes("inbox-filters"' in js
    assert '"human,open,followup,decision,clarification,order,task"' in js
    assert '"human,open,answered,followup"' not in js
    assert 'data-f="${t}"' in js
    for token, label in (
        ("human", "Human"),
        ("ai", "AI"),
        ("open", "Open"),
        ("answered", "Answered"),
        ("followup", "Needs follow-up"),
        ("closed", "Closed"),
        ("decision", "Decisions"),
        ("clarification", "Clarifications"),
        ("order", "Approval requests"),
        ("task", "Tasks"),
        ("report", "Reports"),
    ):
        assert f'["{token}", "{label}"' in js
    assert "status=queue" not in js
    assert "status=attention" not in js


def test_e2e_checkbox_filters_default_attention_no_ai() -> None:
    """E2E mixes checklist/report checkboxes; default open/failed, drafts opt-in."""
    js = _read("app.js")
    assert 'filterBoxes("e2e-filters"' in js
    assert '"open,fail"' in js
    assert '"open,draft,fail"' not in js
    for token, label in (
        ("open", "Open"),
        ("draft", "Drafts"),
        ("submitted", "Submitted"),
        ("fail", "Failed"),
        ("pass", "Passed"),
    ):
        assert f'["{token}", "{label}"' in js
    assert js.count('["ai", "AI"') == 1  # inbox only; E2E is human by design


def test_all_list_tabs_share_filter_helper() -> None:
    """Every tabbed list uses filterBoxes with an attention default."""
    js = _read("app.js")
    assert "function filterBoxes(id, groups, picked)" in js
    assert "function bindFilterBoxes(id, base, param)" in js
    assert "function pickedTokens(param, fallback)" in js
    for view, default in (
        ("inbox", "human,open,followup,decision,clarification,order,task"),
        ("e2e", "open,fail"),
        ("plans", "active"),
        ("runs", "failed,running,queued,paused,waiting,approved"),
        ("ideas", "new,reviewing"),
        ("backlog", "proposed,ready,doing,blocked"),
        ("workflows", "active"),
        ("documents", "current"),
    ):
        assert f'filterBoxes("{view}-filters"' in js
        assert f'"{default}"' in js
    assert "status=archive" not in js
    css = _read("app.css")
    assert ".fgroup" in css


def test_system_retains_spend_card() -> None:
    """System retains the Spend card and its empty state."""
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


def test_home_scheduled_card_uses_live_state() -> None:
    js = _read("app.js")
    assert "No scheduler yet" not in js
    assert "status.drain_scheduler" in js
    assert "<h2>Upcoming work</h2>" in js
    assert 'api("/api/fleet")' in js


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
    """Spend card shows order, prepaid total, and rules."""
    js = _read("app.js")
    assert "spend.policy" in js
    assert "prepaid-if-allowed" in js
    assert "Prepaid spent" in js


def test_providers_view_markers_present() -> None:
    """Providers route, cards, refresh action, and nav link exist."""
    js = _read("app.js")
    assert "renderProviders" in js
    # Route dispatch uses the bare name; the only hash literal is the #/spend shim.
    assert js.count("#/providers") == 1
    assert 'name === "spend"' in js
    assert 'name === "providers"' in js
    assert "/api/providers" in js
    assert "/api/providers/refresh" in js
    assert "providers-refresh" in js
    assert "Log in / register at" in js
    assert "Allowances:" in js
    assert "b.provider === p.route" in js
    html = _read("index.html")
    assert 'data-view="providers"' in html


def test_spend_merged_into_providers() -> None:
    """Spend view merged: providers carry the spend card, #/spend redirects."""
    js = _read("app.js")
    html = _read("index.html")
    assert "renderSpend" not in js
    assert "spendCardHtml" in js
    assert 'location.replace("#/providers")' in js
    assert 'location.hash = "#/fleet"' not in js
    assert 'data-view="spend"' not in html


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
    assert "Fan-out defaults" in js
    assert 'data-scope="${scope}"' in js
    assert "setFanoutDefault(this)" in js
    assert '"/api/restrictions/fanout"' in js
    assert "Fan-out default updated" in js


def test_inbox_detail_has_delete_button_with_confirm() -> None:
    """Owners can delete an item from its detail view (two-click arm)."""
    js = _read("app.js")
    assert 'id="delete-inbox-btn"' in js
    assert "Permanently delete this inbox item" in js
    assert "Click again to confirm delete" in js
    assert 'encodeURIComponent(id) + "/delete"' in js


def test_inbox_followup_mark_stays_out_of_archive() -> None:
    """Follow-up closes are marked and filtered by their own checkbox."""
    js = _read("app.js")
    assert 'name="resolution_kind"' in js
    assert "No final answer" in js
    assert "const isFollowup = (t)" in js
    assert "picked.has(who(t))" in js
    assert "states(t).some((s) => picked.has(s))" in js
    assert "needs follow-up" in js
    assert "Marked for follow-up, kept in Active" in js


def test_tab_links_never_wrap_badges_onto_their_own_line() -> None:
    """Badges stay glued to their tab labels at every width."""
    css = _read("app.css")
    assert (
        "nav a { margin-right: var(--wb-space-5); text-decoration: none; white-space: nowrap; }"
        in css
    )


def test_mobile_media_query_keeps_single_scrollable_tab_row() -> None:
    """Under 700px the tab bar scrolls horizontally instead of stacking."""
    css = _read("app.css")
    assert "@media (max-width: 700px)" in css
    assert "header { flex-wrap: wrap;" in css
    assert "nav { flex: 1 1 100%; overflow-x: auto; white-space: nowrap;" in css


def test_module_routing_executes_landing_and_disabled_deep_links():
    js = _read("app.js")
    router = js[
        js.index("async function render() {") : js.index(
            'document.getElementById("create-btn").addEventListener'
        )
    ]
    driver = r"""
const assert = require('assert');
const fs = require('fs');
const source = fs.readFileSync(process.argv[1], 'utf8');
const router = source.slice(source.indexOf('async function render() {'), source.indexOf('document.getElementById("create-btn").addEventListener'));
const view = {innerHTML: ''};
const document = {querySelectorAll: () => [], querySelector: () => null};
let moduleSettings = {landing_page: 'runs', modules: [{id: 'overview', views: ['home'], activated: false}]};
let replaced = null;
const location = {hash: '', replace(url) { replaced = url; }};
const stopRunsPoll = () => {}, stopRunDetailPoll = () => {}, loadModules = async () => {};
const refreshBadge = () => {}, toast = () => {}, esc = String;
let rendered = '';
const renderRuns = async (id) => {rendered = 'runs:' + (id || '');};
const renderChatList = async () => {rendered = 'chat';};
const renderHome = async () => {rendered = 'home';};
eval(router);
(async () => {
 await render(); assert.equal(rendered, 'runs:');
 location.hash = '#/chat'; await render(); assert.equal(rendered, 'chat');
 location.hash = '#/runs/example'; await render(); assert.equal(rendered, 'runs:example');
 location.hash = '#/home'; await render(); assert(view.innerHTML.includes('Module inactive'));
 location.hash = '#/'; view.innerHTML = ''; await render(); assert(view.innerHTML.includes('Module inactive'));
 moduleSettings.modules[0].activated = true;
 for (const hash of ['#/', '#/?f=open', '#/home']) {
   location.hash = hash; rendered = ''; await render(); assert.equal(rendered, 'home');
 }
 location.hash = ''; rendered = ''; await render(); assert.equal(rendered, 'runs:');
 location.hash = '#/unknown'; view.innerHTML = ''; await render(); assert(view.innerHTML.includes('Not found'));
 location.hash = '#/spend'; await render(); assert.equal(replaced, '#/providers', 'alias replaces (no back-trap)');
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
    assert "moduleSettings.landing_page" in router
    _run_node_driver(driver)


def test_chat_live_progress_pins():
    js = _read("app.js")
    assert "setInterval(pollProgress, 2000)" in js
    assert "/progress?message_id=" in js
    # Raw stdout dump + /^Tool (\w+)/ checklist replaced 2026-11-18: Mai
    # emits external_agent_activity lines, so the feed humanizes those.
    assert "/^Tool (\\w+)/" not in js
    assert "humanizeActivity" in js
    assert "activity-feed" in js
    assert "aria-live" in js
    assert "Live staged files" in js
    assert "Live progress paused (reduced motion)." in js
    assert 'mode === "agent" && !reduceMotion' in js
    assert "clearInterval(progressTimer)" in js
    assert "if (progressStopped) return;" in js


def test_filter_changes_and_badge_execute():
    """Checkbox changes keep valid routes and explicit empty selections across reloads."""
    driver = r"""
const assert = require('assert');
const source = require('fs').readFileSync(process.argv[1], 'utf8');
const location = {hash: ''};
let change;
let checked = [];
const view = {querySelectorAll: selector => selector.endsWith(':checked') ? checked :
  [{addEventListener: (event, callback) => {assert.equal(event, 'change'); change = callback;}}]};
eval(source.slice(source.indexOf('function bindFilterBoxes('), source.indexOf('/* Project filter')));
for (const base of ['inbox', 'ideas', 'documents', 'plans', 'runs', 'backlog', 'workflows', 'e2e']) {
  const param = base === 'e2e' ? 's' : 'f';
  location.hash = '#/' + base;
  assert.deepEqual([...pickedTokens(param, 'open,followup')], ['open', 'followup']);
  bindFilterBoxes(base + '-filters', base, param);
  checked = [{dataset: {f: 'open'}}]; change();
  assert.equal(location.hash, '#/' + base + '?' + param + '=open');
  assert.deepEqual([...pickedTokens(param, 'open,followup')], ['open']);
  checked = []; change();
  assert.equal(location.hash, '#/' + base + '?' + param + '=');
  assert.equal(pickedTokens(param, 'open,followup').size, 0);
  // Reading again models a fresh render/reload from the same hash.
  assert.equal(pickedTokens(param, 'open,followup').size, 0);
}
const badge = {}, ideasBadge = {}, backlogBadge = {}, e2eBadge = {};
let attention = 3;
const api = async path => {
  assert.equal(path, '/api/status');
  return {attention_inbox: attention, open_inbox: 9};
};
eval(source.slice(source.indexOf('async function refreshBadge()'), source.indexOf('const GLOSSARY')));
eval(source.slice(source.indexOf('async function pollInboxBadge()'), source.indexOf('function startInboxPoll()')));
(async () => {
  await pollInboxBadge(); assert.equal(badge.textContent, 3); assert.equal(badge.hidden, false);
  attention = 0; await pollInboxBadge(); assert.equal(badge.hidden, true);
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
    _run_node_driver(driver)


def test_reminder_entries_separated_execute():
    """Reminder cards separate entries with a rule, never one run-on block."""
    driver = r"""
const assert = require('assert');
const source = require('fs').readFileSync(process.argv[1], 'utf8');
const E2E_REMINDER_VIEWS = ['inbox'];
let html = '';
const card = {className: '', id: '',
  set innerHTML(v) { html = v; }, querySelectorAll: () => []};
const view = {append: () => {}};
const document = {createElement: () => card};
const esc = (s) => String(s ?? '');
const api = async () => ({items: [
  {behavior: 'b1', item_id: 'i1', task_id: 't1',
   steps: [{action: 'a1', expected: 'e1'}]},
  {behavior: 'b2', item_id: 'i2', task_id: 't2',
   steps: [{action: 'a2', expected: 'e2'}]},
]});
eval(source.slice(source.indexOf('async function renderE2EReminders('),
  source.indexOf('document.getElementById("create-btn")')));
(async () => {
  await renderE2EReminders('inbox');
  assert(html.includes('b1') && html.includes('b2'));
  assert(html.includes('a1') && html.includes('a2'));
  assert.equal((html.match(/<hr>/g) || []).length, 1);
  assert(html.indexOf('<hr>') > html.indexOf('b1'));
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
    _run_node_driver(driver)


def test_receipts_keep_open_state_across_refreshes():
    """Unchanged receipts skip re-render; changed ones restore open entries."""
    driver = r"""
const assert = require('assert');
const source = require('fs').readFileSync(process.argv[1], 'utf8');
const esc = (s) => String(s ?? '');
let receipts = [{kind: 'r1'}, {kind: 'r2'}];
const api = async () => ({receipts});
let writes = 0;
const opened = [];
const details = (text) => ({
  querySelector: () => ({textContent: text}),
  setAttribute: (k) => { if (k === 'open') opened.push(text); },
});
let current = [];
const list = {
  dataset: {},
  set innerHTML(v) { writes++; this._html = v; },
  querySelectorAll: (sel) => sel === 'details.open' ? current.filter((d) => d._open) : current,
};
const document = {getElementById: () => list};
eval(source.slice(source.indexOf('function receiptHtml('), source.indexOf('/* Project picker')));
(async () => {
  await renderReceiptsInto('x');
  assert.equal(writes, 1);
  await renderReceiptsInto('x');
  assert.equal(writes, 1);  // unchanged data: no rewrite, reader undisturbed
  current = [Object.assign(details('r1'), {_open: true}),
    Object.assign(details('r2'), {_open: false})];
  receipts = [{kind: 'r1'}, {kind: 'r2'}, {kind: 'r3'}];
  await renderReceiptsInto('x');
  assert.equal(writes, 2);
  assert.deepEqual(opened, ['r1']);  // previously open entry restored
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
    _run_node_driver(driver)


def test_e2e_detail_return_preserves_list_selection():
    """Checklist/report navigation retains filters, including an empty selection."""
    driver = r"""
const assert = require('assert');
const source = require('fs').readFileSync(process.argv[1], 'utf8');
const location = {hash: ''};
const view = {innerHTML: '', querySelectorAll: () => []};
const document = {getElementById: () => null, querySelectorAll: () => []};
const esc = String, gtext = String, fmtTime = String;
const filterBoxes = () => '', bindFilterBoxes = () => {};
const task = {id: 'task', title: 'Checklist', status: 'submitted', report_id: 'report', items: []};
const report = {id: 'report', title: 'Report', overall: 'pass', items: []};
const api = async path => path.endsWith('/tasks') ? {items: [task]} :
  path.endsWith('/reports') ? {items: [report]} :
  {item: path.includes('/reports/') ? report : task};
eval(source.slice(source.indexOf('function pickedTokens('), source.indexOf('/* Project filter')));
eval(source.slice(source.indexOf('async function renderE2E('), source.indexOf('async function renderInbox(')));
(async () => {
  for (const query of ['', '?s=submitted,pass', '?s=']) {
    const suffix = query ? '?s=' + encodeURIComponent(query.slice(3)) : '';
    location.hash = '#/e2e' + query;
    await renderE2E();
    if (query.includes('submitted')) {
      assert(view.innerHTML.includes('href="#/e2e/task' + suffix + '"'));
      assert(view.innerHTML.includes('href="#/e2e/report/report' + suffix + '"'));
    }
    location.hash = '#/e2e/task' + suffix;
    await renderE2E('task');
    assert(view.innerHTML.includes('href="#/e2e' + suffix + '">All checklists'));
    assert(view.innerHTML.includes('href="#/e2e/report/report' + suffix + '"'));
    location.hash = '#/e2e/report/report' + suffix;
    await renderE2E('report/report');
    assert(view.innerHTML.includes('href="#/e2e' + suffix + '">All checklists'));
    location.hash = '#/e2e' + suffix;
    await renderE2E();
    assert.deepEqual([...pickedTokens('s', 'open,fail')],
      query === '' ? ['open', 'fail'] : query === '?s=' ? [] : ['submitted', 'pass']);
  }
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
    _run_node_driver(driver)


def test_runs_explains_scheduler_cadence_and_failure_states() -> None:
    driver = r"""
const assert = require('assert');
const fs = require('fs');
const source = fs.readFileSync(process.argv[1], 'utf8');
eval(source.slice(source.indexOf('function drainSchedulerText('), source.indexOf('async function renderRuns(')));
assert.match(drainSchedulerText(undefined), /status unavailable/);
assert.match(drainSchedulerText({started: false}), /Automatic drain is off.*Drain now/);
const active = drainSchedulerText({started: true, interval_seconds: 300, ticks: 7, errors: 0});
assert.match(active, /up to one queued run per tick/);
assert.match(active, /First tick after 300s/);
assert.match(active, /wait 300s after the previous drain finishes/);
assert.match(active, /Finished ticks: 7; tick errors: 0/);
assert.match(active, /Drain paused/);
assert.match(drainSchedulerText({started: true, errors: 2, last_error: 'RuntimeError: boom'}), /tick errors: 2. Last error: RuntimeError: boom/);
"""
    _run_node_driver(driver)
    js = _read("app.js")
    assert 'drainStatus = (await api("/api/status")).drain_scheduler' in js
    assert "${esc(drainSchedulerText(drainStatus))}" in js


def test_projects_goals_carry_registry_provenance() -> None:
    """Goals section names its source so static entries don't look hard-coded."""
    js = _read("app.js")
    assert "docs/goals/registry.json" in js
    assert "registered project directories appear under Work roots" in js


def test_inbox_project_filter_lives_in_url() -> None:
    """Project filter is URL state so bare #/inbox shows the badge set."""
    js = _read("app.js")
    assert "inboxProjectFilter" not in js
    assert 'get("project")' in js
    assert 'params.set("project"' in js
    assert "params.delete" in js
    assert "params.toString()" in js


def test_allowance_empty_states_are_honest() -> None:
    """Empty buckets explain themselves instead of rendering blank."""
    js = _read("app.js")
    assert "Allowances: no usage recorded yet." in js
    assert "No spend buckets yet" in js


def test_e2e_report_shows_agent_evidence_and_mismatch() -> None:
    """Report view renders per-step agent evidence plus mismatch pills."""
    js = _read("app.js")
    assert "Agent check" in js
    assert "evidence_summary" in js
    assert "Agent output" in js
    assert "agent_check_mismatches" in js
    assert "agent mismatch" in js


def test_chat_agent_controls_present() -> None:
    """Chat thread exposes the agent enable switch and policy selector."""
    js = _read("app.js")
    assert "Agent mode is off" in js
    assert 'id="agent-enable"' in js
    assert 'id="agent-policy"' in js
    assert 'id="agent-save-btn"' in js
    assert "/api/chat/agent-config" in js
    assert '"scoped", "ask-always", "yolo"' in js


def test_run_report_renders_readable_markdown() -> None:
    """Run reports render headers/lists/bold, never raw markdown or markup."""
    driver = r"""
const assert = require('assert');
const source = require('fs').readFileSync(process.argv[1], 'utf8');
eval(source.slice(source.indexOf('function esc('), source.indexOf('/* Readable local')));
const html = mdHtml('# Title (r1)\nStatus: **completed**\n\n## Tools used\n- read_file\n- grep\n\n<script>alert(1)</script>');
assert(html.includes('<h4>Title (r1)</h4>'));
assert(html.includes('<h5>Tools used</h5>'));
assert(html.includes('<strong>completed</strong>'));
assert(html.includes('<li>read_file</li>'));
assert(!html.includes('<script>'));
assert(html.includes('&lt;script&gt;'));
"""
    _run_node_driver(driver)
    assert "mdHtml(run.report)" in _read("app.js")


def test_inbox_divergence_banner_explains_badge_gap() -> None:
    driver = r"""
const assert = require('assert');
const source = require('fs').readFileSync(process.argv[1], 'utf8');
const grab = (name) => eval('(' + source.slice(source.indexOf('function ' + name + '('),
  source.indexOf('\n}', source.indexOf('function ' + name + '(')) + 2) + ')');
const esc = grab('esc');
const gtext = grab('gtext');
const filterBoxes = grab('filterBoxes');
const pickedTokens = grab('pickedTokens');
const bindFilterBoxes = grab('bindFilterBoxes');
const projectOptions = async () => '<option value="">All projects</option>';
eval(source.slice(source.indexOf('const ID_ROUTES'), source.indexOf('function truncate(')));
const renderer = source.slice(source.indexOf('async function renderInbox('),
  source.indexOf('async function markIdeaSeen('));
eval(renderer);
const view = {innerHTML: '', querySelectorAll: () => []};
const location = {hash: '#/inbox'};
const document = {getElementById: () => ({addEventListener() {}})};
const items = [
  {id: 'o1', title: 'Open one', type: 'task', status: 'open', assignee: 'owner'},
  {id: 'a1', title: 'Answered one', type: 'task', status: 'answered', assignee: 'owner'},
  {id: 'a2', title: 'Answered two', type: 'task', status: 'answered', assignee: 'owner'},
  {id: 'f1', title: 'Follow-up', type: 'task', status: 'closed', assignee: 'owner', resolution_kind: 'followup'},
  {id: 'x1', title: 'AI job', type: 'task', status: 'open', assignee: 'agent'},
  {id: 'x2', title: 'Archived', type: 'task', status: 'closed', assignee: 'owner'},
];
const api = async (path) => ({items, attention_ids: ['f1', 'o1', 'a1', 'a2']});
const shown = (html) => (html.match(/<li>/g) || []).length;
(async () => {
  await renderInbox(undefined);
  assert.equal(shown(view.innerHTML), 2);
  assert(!view.innerHTML.includes('Answered one'));
  assert(!view.innerHTML.includes('AI job'));
  assert(!view.innerHTML.includes('inbox/x2'));
  const html = view.innerHTML;
  assert(html.indexOf('Follow-up') < html.indexOf('Open one'), 'attention order verbatim');
  location.hash = '#/inbox?f=human,open,followup';
  await renderInbox(undefined);
  assert.equal(shown(view.innerHTML), 2);
  assert(view.innerHTML.includes('2 attention items hidden by filters'), 'banner counts hidden');
  assert(view.innerHTML.includes('closed,decision,clarification,order,task,report">Show all'), 'banner offers archive and all kinds');
  location.hash = '#/inbox?project=p1';
  await renderInbox(undefined);
  assert(view.innerHTML.includes('Project filter active'), 'project divergence noted');
  assert.equal(shown(view.innerHTML), 2, 'project defaults match global defaults');
  location.hash = '#/inbox?f=human,answered,task';
  await renderInbox(undefined);
  assert.equal(shown(view.innerHTML), 2, 'answered remains available explicitly');
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
    _run_node_driver(driver)


def test_inbox_kind_filter_hides_reports_by_default() -> None:
    driver = r"""
const assert = require('assert');
const source = require('fs').readFileSync(process.argv[1], 'utf8');
const grab = (name) => eval('(' + source.slice(source.indexOf('function ' + name + '('),
  source.indexOf('\n}', source.indexOf('function ' + name + '(')) + 2) + ')');
const esc = grab('esc');
const gtext = grab('gtext');
const filterBoxes = grab('filterBoxes');
const pickedTokens = grab('pickedTokens');
const bindFilterBoxes = grab('bindFilterBoxes');
const projectOptions = async () => '<option value="">All projects</option>';
eval(source.slice(source.indexOf('const ID_ROUTES'), source.indexOf('function truncate(')));
const renderer = source.slice(source.indexOf('async function renderInbox('),
  source.indexOf('async function markIdeaSeen('));
eval(renderer);
const view = {innerHTML: '', querySelectorAll: () => []};
const location = {hash: '#/inbox'};
const document = {getElementById: () => ({addEventListener() {}})};
const items = [
  {id: 'd1', title: 'Decide this', type: 'decision', status: 'open', assignee: 'owner'},
  {id: 'r1', title: 'Chain report', type: 'report', status: 'open', assignee: 'owner'},
  {id: 't1', title: 'Do that', type: 'task', status: 'open', assignee: 'owner'},
  {id: 'f1', title: 'Future kind', type: 'memo', status: 'open', assignee: 'owner'},
];
const api = async (path) => ({items, attention_ids: ['d1', 'r1', 't1', 'f1']});
const shown = (html) => (html.match(/<li>/g) || []).length;
(async () => {
  await renderInbox(undefined);
  assert.equal(shown(view.innerHTML), 3, 'default hides the report only');
  assert(!view.innerHTML.includes('Chain report'), 'report hidden');
  assert(view.innerHTML.includes('Future kind'), 'unknown kind fails open');
  assert(view.innerHTML.includes('Reports hide by default'), 'banner explains the gap');
  assert(!view.innerHTML.includes('Show all'), 'no looping reset link');
  location.hash = '#/inbox?f=human,open,followup,decision,clarification,order,task,report';
  await renderInbox(undefined);
  assert.equal(shown(view.innerHTML), 4, 'ticking Reports reveals it');
  location.hash = '#/inbox?f=human,open,report';
  await renderInbox(undefined);
  assert.equal(shown(view.innerHTML), 2, 'kind narrows; unknown kind still fails open');
  assert(view.innerHTML.includes('Chain report'));
  location.hash = '#/inbox?f=human,open';
  await renderInbox(undefined);
  assert.equal(shown(view.innerHTML), 3, 'old bookmark without kinds uses defaults');
  assert(!view.innerHTML.includes('Chain report'), 'report still hidden');
  assert(view.innerHTML.includes('data-f="task" title="Work items to do or supervise" checked'),
    'default kind boxes render checked');
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
    _run_node_driver(driver)


def test_inbox_detail_renders_notes_with_line_breaks() -> None:
    driver = r"""
const assert = require('assert');
const source = require('fs').readFileSync(process.argv[1], 'utf8');
const grab = (name) => eval('(' + source.slice(source.indexOf('function ' + name + '('),
  source.indexOf('\n}', source.indexOf('function ' + name + '(')) + 2) + ')');
const esc = grab('esc');
const gtext = grab('gtext');
const filterBoxes = grab('filterBoxes');
const pickedTokens = grab('pickedTokens');
const bindFilterBoxes = grab('bindFilterBoxes');
const projectOptions = async () => '<option value="">All projects</option>';
eval(source.slice(source.indexOf('const ID_ROUTES'), source.indexOf('function truncate(')));
const renderer = source.slice(source.indexOf('async function renderInbox('),
  source.indexOf('async function markIdeaSeen('));
eval(renderer);
const view = {innerHTML: '', querySelectorAll: () => []};
const location = {hash: '#/inbox/x1'};
const document = {getElementById: () => ({addEventListener() {}})};
const item = {id: 'x1', title: 'T', type: 'task', status: 'open', body: 'b',
  answer: 'A', note: 'first\nsecond', notes: 'alpha\nbeta', options: [], context_refs: []};
const api = async (path) => ({item});
(async () => {
  await renderInbox('x1');
  const html = view.innerHTML;
  assert(html.includes('<h3>Notes</h3>'), 'notes section renders');
  assert(html.includes('alpha\nbeta'), 'notes keep line breaks');
  assert(html.includes('<p class="inbox-body"><strong>Note:</strong> first\nsecond</p>'),
    'answer note preserves breaks');
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
    _run_node_driver(driver)


def test_jobs_view_renders_review_form() -> None:
    driver = r"""
const assert = require('assert');
const source = require('fs').readFileSync(process.argv[1], 'utf8');
const grab = (name) => eval('(' + source.slice(source.indexOf('function ' + name + '('),
  source.indexOf('\n}', source.indexOf('function ' + name + '(')) + 2) + ')');
const esc = grab('esc');
const gtext = grab('gtext');
const renderer = source.slice(source.indexOf('async function renderJobs('),
  source.indexOf('async function renderInvoices('));
eval(renderer);
const view = {innerHTML: '', querySelectorAll: () => []};
const document = {getElementById: () => ({addEventListener() {}})};
(async () => {
  await renderJobs();
  const html = view.innerHTML;
  assert(html.includes('<h1>Job match review</h1>'), 'title renders');
  assert(html.includes('id="jobs-form"'), 'form renders');
  assert(html.includes('name="required_skills"'), 'skills field renders');
  assert(html.includes('id="jobs-result"'), 'result target renders');
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
    _run_node_driver(driver)


def test_humanize_activity_translates_mai_lines() -> None:
    driver = r"""
const assert = require('assert');
const source = require('fs').readFileSync(process.argv[1], 'utf8');
const grab = (name) => eval('(' + source.slice(source.indexOf('function ' + name + '('),
  source.indexOf('\n}', source.indexOf('function ' + name + '(')) + 2) + ')');
const humanizeActivity = grab('humanizeActivity');
const truncate = grab('truncate');
assert.equal(
  humanizeActivity('external_agent_activity: command_execution completed - command: "git status"'),
  'Done: git status');
assert.equal(
  humanizeActivity('external_agent_activity item.completed: Checked the tree.'),
  'Checked the tree.');
assert.equal(humanizeActivity('external_agent_activity: turn.started'), 'Turn started.');
assert.equal(humanizeActivity('coding_session_id: abc'), null);
assert.equal(humanizeActivity('route_id: openai/x'), null);
assert.equal(humanizeActivity('Some plain narration.'), 'Some plain narration.');
assert.equal(truncate('abcdef', 4), 'abcd…');
"""
    _run_node_driver(driver)


def test_chat_thread_renders_agent_turn_commands_above_report() -> None:
    driver = r"""
const assert = require('assert');
const source = require('fs').readFileSync(process.argv[1], 'utf8');
const grab = (name) => eval('(' + source.slice(source.indexOf('function ' + name + '('),
  source.indexOf('\n}', source.indexOf('function ' + name + '(')) + 2) + ')');
const esc = grab('esc');
const gtext = grab('gtext');
const truncate = grab('truncate');
const renderer = source.slice(source.indexOf('async function renderChatThread('),
  source.indexOf('async function renderInbox('));
eval(renderer);
const view = {innerHTML: '', querySelectorAll: () => []};
const location = {hash: '#/chat/x1'};
const el = () => ({addEventListener() {}, dataset: {}, value: '', checked: false});
const document = {getElementById: el, createElement: () => ({})};
const window = {};
const setInterval = () => 0;
const clearInterval = () => {};
const toast = () => {};
const render = () => {};
const loadProjectPicker = async () => {};
const loadPlanPicker = async () => {};
const api = async (path) => {
  if (path.includes('/messages')) return {messages: [
    {role: 'user', content: 'do it'},
    {role: 'assistant', content: 'noise\n### Agent report\nAll clean.', provider: 'mai', model: 'm',
     agent_turn: {report: '### Agent report\nAll clean.',
       commands: [{command: 'git status', status: 'completed'}]}},
  ], pending_turn: null};
  if (path === '/api/plans') return {items: []};
  if (path === '/api/chat/agent-config') return {enabled: false, approval: 'scoped'};
  return {sessions: [{id: 'x1', title: 'T', mode: 'ask'}], agent_enabled: false};
};
(async () => {
  await renderChatThread('x1');
  const html = view.innerHTML;
  const cmds = html.indexOf('Commands (1)');
  const report = html.indexOf('All clean.');
  const full = html.indexOf('<details><summary>Full transcript (');
  assert(cmds !== -1 && report !== -1 && full !== -1, 'commands, report, transcript render');
  assert(cmds < report && report < full, 'commands above report above transcript toggle');
  assert(html.includes('git status'), 'command text renders');
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
    _run_node_driver(driver)


def test_chat_thread_collapses_long_turns_and_links_plan() -> None:
    driver = r"""
const assert = require('assert');
const source = require('fs').readFileSync(process.argv[1], 'utf8');
const grab = (name) => eval('(' + source.slice(source.indexOf('function ' + name + '('),
  source.indexOf('\n}', source.indexOf('function ' + name + '(')) + 2) + ')');
const esc = grab('esc');
const gtext = grab('gtext');
const renderer = source.slice(source.indexOf('async function renderChatThread('),
  source.indexOf('async function renderInbox('));
eval(renderer);
const view = {innerHTML: '', querySelectorAll: () => []};
const location = {hash: '#/chat/x1'};
const el = () => ({addEventListener() {}, dataset: {}, value: '', checked: false});
const document = {getElementById: el, createElement: () => ({})};
const window = {};
const setInterval = () => 0;
const clearInterval = () => {};
const toast = () => {};
const render = () => {};
const loadProjectPicker = async () => {};
const loadPlanPicker = async () => {};
const longBody = 'Lead paragraph here.\n\n' + 'x'.repeat(700);
const api = async (path) => {
  if (path.includes('/messages')) return {messages: [
    {role: 'user', content: 'do it'},
    {role: 'assistant', content: 'short answer', provider: 'ollama', model: 'm'},
    {role: 'assistant', content: longBody, provider: 'ollama', model: 'm'},
  ], pending_turn: null};
  if (path === '/api/plans') return {items: [
    {id: 'p1', title: 'Chat plan', status: 'active', source: 'chat:x1'},
    {id: 'p2', title: 'Other', status: 'active', source: 'manual'},
  ]};
  if (path === '/api/chat/agent-config') return {enabled: false, approval: 'scoped'};
  return {sessions: [{id: 'x1', title: 'T', mode: 'ask'}], agent_enabled: false};
};
(async () => {
  await renderChatThread('x1');
  const html = view.innerHTML;
  assert(html.includes('<details><summary>Full turn ('), 'long turn collapses');
  assert(html.includes('Lead paragraph here.'), 'lead stays visible');
  assert(!html.includes('<details><summary>Full turn (12 chars)'), 'short stays flat');
  assert(html.includes('href="#/plans/p1"'), 'plan banner links chat plan');
  assert(!html.includes('#/plans/p2'), 'unrelated plans excluded');
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
    _run_node_driver(driver)


def test_chat_thread_scrolls_to_input_on_open() -> None:
    driver = r"""
const assert = require('assert');
const source = require('fs').readFileSync(process.argv[1], 'utf8');
const grab = (name) => eval('(' + source.slice(source.indexOf('function ' + name + '('),
  source.indexOf('\n}', source.indexOf('function ' + name + '(')) + 2) + ')');
const esc = grab('esc');
const gtext = grab('gtext');
const truncate = grab('truncate');
const renderer = source.slice(source.indexOf('async function renderChatThread('),
  source.indexOf('async function renderInbox('));
eval(renderer);
const view = {innerHTML: '', querySelectorAll: () => []};
const location = {hash: '#/chat/x1'};
const scrolled = [];
const el = (id) => ({addEventListener() {}, dataset: {}, value: '', checked: false,
  scrollIntoView: id === 'chat-form' ? ((opts) => scrolled.push(opts)) : undefined});
const document = {getElementById: el, createElement: () => ({})};
const window = {};
const setInterval = () => 0;
const clearInterval = () => {};
const toast = () => {};
const render = () => {};
const loadProjectPicker = async () => {};
const loadPlanPicker = async () => {};
const api = async (path) => {
  if (path.includes('/messages')) return {messages: [
    {role: 'user', content: 'hi'},
  ], pending_turn: null};
  if (path === '/api/plans') return {items: []};
  if (path === '/api/chat/agent-config') return {enabled: false, approval: 'scoped'};
  return {sessions: [{id: 'x1', title: 'T', mode: 'ask'}], agent_enabled: false};
};
(async () => {
  await renderChatThread('x1');
  assert(scrolled.length === 1, 'input scrolled into view once on open');
  assert(scrolled[0] && scrolled[0].block === 'end', 'scrolled to end');
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
    _run_node_driver(driver)
    css = (WEB_DIR / "app.css").read_text(encoding="utf-8")
    assert "#chat-form" in css and "position: sticky" in css


def test_inbox_detail_renders_acknowledge_for_reports() -> None:
    driver = r"""
const assert = require('assert');
const source = require('fs').readFileSync(process.argv[1], 'utf8');
const grab = (name) => eval('(' + source.slice(source.indexOf('function ' + name + '('),
  source.indexOf('\n}', source.indexOf('function ' + name + '(')) + 2) + ')');
const esc = grab('esc');
const gtext = grab('gtext');
const filterBoxes = grab('filterBoxes');
const pickedTokens = grab('pickedTokens');
const bindFilterBoxes = grab('bindFilterBoxes');
const projectOptions = async () => '<option value="">All projects</option>';
eval(source.slice(source.indexOf('const ID_ROUTES'), source.indexOf('function truncate(')));
const renderer = source.slice(source.indexOf('async function renderInbox('),
  source.indexOf('async function markIdeaSeen('));
eval(renderer);
const view = {innerHTML: '', querySelectorAll: () => []};
const location = {hash: '#/inbox/r1'};
const document = {getElementById: () => ({addEventListener() {}})};
const item = {id: 'r1', title: 'Chain report: X', type: 'report', status: 'open',
  body: '## Initial\nsrc', created_by: 'supervisor', options: [], context_refs: []};
const api = async (path) => ({item});
(async () => {
  await renderInbox('r1');
  const html = view.innerHTML;
  assert(html.includes('id="ack-btn"'), 'acknowledge button renders');
  assert(!html.includes('id="answer-form"'), 'reports take no answers');
  assert(!html.includes('id="close-form"'), 'reports take no closes');
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
    _run_node_driver(driver)


def test_bundled_services_render_in_fleet_and_projects() -> None:
    import json
    import sys

    sys.path.insert(0, str(WEB_DIR.parent))
    from dashboard_web_app import bundled_services

    rows = bundled_services(WEB_DIR.parents[2], {"branch": "develop", "commit": "abc1234"})
    assert len(rows) == 4
    node = _node_driver()
    driver = r"""
const assert = require('assert');
const source = require('fs').readFileSync(process.argv[1], 'utf8');
const rows = JSON.parse(process.argv[2]);
const grab = (name) => eval('(' + source.slice(source.indexOf('function ' + name + '('),
  source.indexOf('\n}', source.indexOf('function ' + name + '(')) + 2) + ')');
const esc = grab('esc');
const fmtTime = grab('fmtTime');
const serviceRowsHtml = grab('serviceRowsHtml');
const view = {innerHTML: '', querySelectorAll: () => []};
const document = {getElementById: () => ({addEventListener() {}})};
const moduleActive = () => false;
const location = {hash: '#/projects'};
const gtext = esc;
const fleet = {tasks: [], runs: [], agents: {runs: []}, sleep: {active: false},
  services: rows, dashboard: {}, ollama: {up: false}};
const api = async (path) => {
  if (path === '/api/projects') return {projects: [], services: rows};
  if (path === '/api/fleet') return {fleet};
  if (path === '/api/sleep') return {active: false};
  throw Error('Unexpected request: ' + path);
};
eval(source.slice(source.indexOf('async function renderProjects('),
  source.indexOf('async function renderMeetings(')));
eval(source.slice(source.indexOf('async function renderFleet('),
  source.indexOf('async function flipToggle(')));
(async () => {
  for (const render of [renderFleet, renderProjects]) {
    await render();
    for (const row of rows) {
      assert(view.innerHTML.includes('<strong>' + esc(row.name) + '</strong>'));
      assert(view.innerHTML.includes(esc(row.explain)));
    }
    assert.equal((view.innerHTML.match(/>bundled</g) || []).length, 4);
    assert.equal((view.innerHTML.match(/develop@abc1234/g) || []).length, 4);
  }
  const escaped = serviceRowsHtml([{kind: 'bundled', name: '<script>',
    version: '<v>', explain: '<img onerror=alert(1)>'}]);
  assert(!escaped.includes('<script>'));
  assert(escaped.includes('&lt;img onerror=alert(1)&gt;'));
  assert(serviceRowsHtml([{name: 'server', up: true}]).includes('>up<'));
  assert(serviceRowsHtml([{name: 'server', up: false}]).includes('>down<'));
  assert.equal(serviceRowsHtml(), '');
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
    result = subprocess.run(
        [node, "-e", driver, str(WEB_DIR / "app.js"), json.dumps(rows)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_fleet_flags_dead_end_runs() -> None:
    driver = r"""
const assert = require('assert');
const source = require('fs').readFileSync(process.argv[1], 'utf8');
const grab = (name) => eval('(' + source.slice(source.indexOf('function ' + name + '('),
  source.indexOf('\n}', source.indexOf('function ' + name + '(')) + 2) + ')');
const esc = grab('esc');
const fmtTime = grab('fmtTime');
const serviceRowsHtml = grab('serviceRowsHtml');
const renderer = source.slice(source.indexOf('async function renderFleet('),
  source.indexOf('async function flipToggle('));
eval(renderer);
const view = {innerHTML: '', querySelectorAll: () => []};
const location = {hash: '#/fleet'};
const document = {getElementById: () => ({addEventListener() {}})};
const fleet = {tasks: [], runs: [],
  agents: {runs: [
    {id: 'a', title: 'dead run', verdict: 'dead-end', reason: 'no triage task', status: 'failed'},
    {id: 'b', title: 'ok run', verdict: 'ok', reason: '', status: 'running'},
  ]},
  sleep: {active: false}, services: [], dashboard: {}, ollama: {up: false}};
const api = async (path) => path === '/api/sleep' ? {active: false} : {fleet};
(async () => {
  await renderFleet();
  const html = view.innerHTML;
  assert(html.includes('>dead-end<'), 'dead-end verdict renders');
  assert(html.includes('no triage task'), 'dead-end reason renders');
  assert(!html.includes('No stuck, broken, or dead-end runs.'), 'flagged list not empty');
  assert(!html.includes('>ok<'), 'ok runs stay unflagged');
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
    _run_node_driver(driver)


def test_link_ids_links_refs_and_bare_ids_without_nesting() -> None:
    driver = r"""
const assert = require('assert');
const source = require('fs').readFileSync(process.argv[1], 'utf8');
const grab = (name) => eval('(' + source.slice(source.indexOf('function ' + name + '('),
  source.indexOf('\n}', source.indexOf('function ' + name + '(')) + 2) + ')');
const esc = grab('esc');
eval(source.slice(source.indexOf('const ID_ROUTES'), source.indexOf('function refLink(')));
const full = 'f05e3226dd8440fc816e03cd89c6c431';
const out = linkIds('see run:8fad37897a5b and item ' + full + ' plus beefcake here');
assert(out.includes('<a href="#/runs/8fad37897a5b"'), 'kind ref links directly');
assert(out.includes('<a href="#/lookup/' + full + '"'), 'bare id links to lookup');
assert(!out.includes('beefcake<'), 'short hex words stay text');
const nested = linkIds('<a href="#/inbox/x">see ' + full + '</a>');
assert.equal((nested.match(/<a /g) || []).length, 1, 'never nests anchors');
const attr = linkIds('<span title="' + full + '">t</span>');
assert(!attr.includes('#/lookup'), 'attributes stay untouched');
const apollo = 'https://knowledge.apollo.io/hc/en-us/articles/4416173158541-Use-Apollo-API';
const ext = (u) => `<a href="${u}" target="_blank" rel="noopener">${u}</a>`;
assert.equal(linkIds(esc(apollo)), ext(apollo));
const query = 'https://example.com/' + full + '?a=1&b=2#section';
const escaped = esc(query);
assert.equal(linkIds(escaped), ext(escaped));
assert.equal(linkIds('(' + apollo + ').'), `(${ext(apollo)}).`);
const balanced = 'https://example.com/wiki/API_(version)';
assert.equal(linkIds(balanced), ext(balanced));
const already = `<a href="${apollo}">${apollo}</a>`;
assert.equal(linkIds(already), already, 'existing external anchors are preserved');
assert.equal(linkIds(linkIds(apollo)), linkIds(apollo), 'repeated rendering is stable');
const quoted = linkIds(esc('"' + apollo + '" <script>alert(1)</script>'));
assert(quoted.includes(`&quot;${ext(apollo)}&quot;`));
assert(!quoted.includes('<script>'), 'escaped input stays escaped');
assert.equal(linkIds('javascript:alert(1)'), 'javascript:alert(1)');
const multiple = linkIds(apollo + ' http://example.org/docs. run:8fad37897a5b');
assert.equal((multiple.match(/<a /g) || []).length, 3, 'URLs and item refs coexist');
"""
    _run_node_driver(driver)


def test_inbox_detail_renders_ref_hyperlinks() -> None:
    driver = r"""
const assert = require('assert');
const source = require('fs').readFileSync(process.argv[1], 'utf8');
const grab = (name) => eval('(' + source.slice(source.indexOf('function ' + name + '('),
  source.indexOf('\n}', source.indexOf('function ' + name + '(')) + 2) + ')');
const esc = grab('esc');
const gtext = grab('gtext');
const filterBoxes = grab('filterBoxes');
const pickedTokens = grab('pickedTokens');
const bindFilterBoxes = grab('bindFilterBoxes');
const projectOptions = async () => '<option value="">All projects</option>';
eval(source.slice(source.indexOf('const ID_ROUTES'), source.indexOf('function truncate(')));
const renderer = source.slice(source.indexOf('async function renderInbox('),
  source.indexOf('async function renderLookup('));
eval(renderer);
const view = {innerHTML: '', querySelectorAll: () => []};
const location = {hash: '#/inbox/x1'};
const document = {getElementById: () => ({addEventListener() {}})};
const apollo = 'https://knowledge.apollo.io/hc/en-us/articles/4416173158541-Use-Apollo-API';
const item = {id: 'x1', title: 'T', type: 'task', status: 'open', body: 'see f05e3226dd8440fc816e03cd89c6c431 ' + apollo,
  options: [], context_refs: ['inbox:abc12345', 'run:8fad37897a5b', 'branch:develop', 'bogus', apollo]};
const api = async (path) => ({item});
(async () => {
  await renderInbox('x1');
  const html = view.innerHTML;
  assert(html.includes('<a href="#/inbox/abc12345"'), 'inbox ref links');
  assert(html.includes('<a href="#/runs/8fad37897a5b"'), 'run ref links');
  assert(html.includes('<li>branch:develop</li>'), 'unrouted ref stays text');
  assert(html.includes('<li>bogus</li>'), 'bare word stays text');
  assert(html.includes('<a href="#/lookup/f05e3226dd8440fc816e03cd89c6c431"'), 'body id links');
  assert.equal(html.split(`<a href="${apollo}" target="_blank" rel="noopener">${apollo}</a>`).length - 1, 2, 'body and context URL link in full');
  assert(!html.includes('#/lookup/4416173158541'), 'article ID never routes internally');
  assert(html.includes('id="lookup-go"') === false, 'detail has no lookup field');
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
    _run_node_driver(driver)


def test_lookup_view_resolves_and_disambiguates() -> None:
    driver = r"""
const assert = require('assert');
const source = require('fs').readFileSync(process.argv[1], 'utf8');
const grab = (name) => eval('(' + source.slice(source.indexOf('function ' + name + '('),
  source.indexOf('\n}', source.indexOf('function ' + name + '(')) + 2) + ')');
const esc = grab('esc');
const gtext = grab('gtext');
const renderer = source.slice(source.indexOf('async function renderLookup('),
  source.indexOf('async function markIdeaSeen('));
eval(renderer);
const view = {innerHTML: '', querySelectorAll: () => []};
let replaced = null;
const location = {hash: '#/lookup/abc', replace(url) { replaced = url; this.hash = url; }};
let rendered = 0;
const render = async () => { rendered++; };
let matches = [];
const api = async (path) => ({matches});
(async () => {
  await renderLookup('');
  assert(view.innerHTML.includes('Find item by ID'), 'empty token explains');
  await renderLookup('deadbeef');
  assert(view.innerHTML.includes('No inbox, run, idea, or plan matches'), 'missing explains');
  matches = [{kind: 'run', id: 'r1', title: 'R', status: 'queued', url: '#/runs/r1'}];
  await renderLookup('r1');
  assert.equal(replaced, '#/runs/r1', 'single match replaces (Back skips the lookup URL)');
  assert.equal(rendered, 1, 'navigation re-renders');
  matches = [{kind: 'inbox', id: 'a', title: 'A', status: 'open', url: '#/inbox/a'},
    {kind: 'run', id: 'b', title: 'B', status: 'failed', url: '#/runs/b'}];
  await renderLookup('ab');
  assert(view.innerHTML.includes('2 matches'), 'ambiguous lists');
  assert(view.innerHTML.includes('#/inbox/a') && view.innerHTML.includes('#/runs/b'), 'both link');
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
    _run_node_driver(driver)


def test_bug_report_builder_requires_description_and_gates_activity() -> None:
    driver = r"""
const assert = require('assert');
const source = require('fs').readFileSync(process.argv[1], 'utf8');
const start = source.indexOf('function buildBugReport(');
const end = source.indexOf('\n}', start) + 2;
eval(source.slice(start, end));
assert.equal(buildBugReport({description: '  '}), null, 'blank rejected');
const recent = [{at: 't', method: 'GET', path: '/api/inbox'}];
const withConsent = buildBugReport({view: '#/runs', description: 'It broke\nmore',
  consent: true, recent, userAgent: 'UA', version: 'v1'});
assert.equal(withConsent.title, 'Bug: It broke', 'title from first line');
assert.equal(withConsent.assignee, 'agent', 'agent triages');
assert.equal(withConsent.metadata.bug_report, true, 'marked');
assert(withConsent.body.includes('view: #/runs'), 'view captured');
assert(withConsent.body.includes('GET /api/inbox'), 'activity attached');
const without = buildBugReport({view: '#/x', description: 'oops', consent: false, recent: []});
assert(without.body.includes('withheld by reporter'), 'withhold noted');
assert(!without.body.includes('recent actions'), 'no activity leaked');
const evil = buildBugReport({description: '<script>alert(1)</script>', consent: false, recent: []});
assert(evil.body.includes('<script>alert(1)</script>'), 'raw text kept for server escape');
"""
    _run_node_driver(driver)


def test_bug_dialog_preserves_view_on_cancel_submit_and_failure() -> None:
    driver = r"""
const assert = require('assert');
const source = require('fs').readFileSync(process.argv[1], 'utf8');
const code = source.slice(source.indexOf('function buildBugReport('),
  source.indexOf('function renderCreate('));
let current = null, posts = [], fail = false, pending;
const location = {hash: '#/create/idea'};
const draft = {value: 'unsaved idea'};
const view = {draft};
Object.defineProperty(view, "innerHTML", {set() {throw new Error("underlying view replaced");}});
const trigger = {isConnected: true, focused: false, focus() {this.focused = true;}};
const recentApiPaths = [{method: 'GET', path: '/api/runs'}];
const navigator = {userAgent: 'test'};
const fieldRow = (label, field) => field;
const toast = () => {};
const api = async (path, options) => {
  posts.push({path, payload: JSON.parse(options.body)});
  if (fail) throw new Error('offline');
  if (pending) await pending;
  return {id: 'report'};
};
function element() {
  return {value: '', checked: false, disabled: false, handlers: {},
    addEventListener(name, fn) {this.handlers[name] = fn;}};
}
const document = {
  activeElement: trigger,
  getElementById(id) {return id === 'bug-dialog' ? current : null;},
  body: {append(dialog) {current = dialog;}},
  createElement(tag) {
    assert.equal(tag, 'dialog');
    const nodes = {};
    const dialog = element();
    dialog.setAttribute = () => {};
    dialog.querySelector = (id) => nodes[id] ||= element();
    dialog.querySelector('#bug-form').querySelector = dialog.querySelector;
    dialog.showModal = () => {dialog.open = true;};
    dialog.remove = () => {current = null;};
    dialog.close = () => {dialog.open = false; dialog.handlers.close();};
    return dialog;
  },
};
eval(code);
const submit = () => current.querySelector('#bug-form').handlers.submit({preventDefault() {}});
const unchanged = () => {
  assert.equal(location.hash, '#/create/idea');
  assert.strictEqual(view.draft, draft);
  assert.equal(draft.value, 'unsaved idea');
};
(async () => {
  openBugReport();
  assert(current.open);
  assert.equal(current.querySelector('#bug-view').value, location.hash);
  const first = current;
  openBugReport();
  assert.strictEqual(current, first, 'one dialog');
  current.querySelector('#bug-cancel').handlers.click();
  assert.equal(current, null);
  assert(trigger.focused);
  unchanged();
  openBugReport();
  current.close(); // Native Escape closes the modal through the same close event.
  unchanged();
  openBugReport();
  await submit();
  assert.equal(posts.length, 0, 'blank report rejected');
  current.querySelector('#bug-description').value = 'Broken';
  fail = true;
  await submit();
  assert(current.open, 'failure retains dialog');
  assert.equal(current.querySelector('#bug-error').textContent, 'offline');
  assert.equal(current.querySelector('#bug-description').value, 'Broken');
  assert.equal(current.querySelector('button[type=submit]').disabled, false);
  assert.equal(posts[0].payload.assignee, 'agent');
  assert.equal(posts[0].payload.metadata.view, location.hash);
  assert(!posts[0].payload.body.includes('GET /api/runs'), 'consent defaults off');
  unchanged();
  fail = false;
  let resolve;
  pending = new Promise(r => {resolve = r;});
  current.querySelector('#bug-consent').checked = true;
  const saving = submit();
  await submit();
  assert.equal(posts.length, 2, 'duplicate submit blocked');
  resolve();
  await saving;
  assert.equal(current, null, 'success closes dialog');
  assert(posts[1].payload.body.includes('GET /api/runs'));
  unchanged();
})().catch(err => {console.error(err); process.exitCode = 1;});
"""
    _run_node_driver(driver)
    js = _read("app.js")
    assert 'addEventListener("click", openBugReport)' in js
    assert "#/create/bug" not in js
    assert 'sessionStorage.getItem("bugView")' not in js


def test_orchestrator_renders_escaped_catalog_and_rejections() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for Orchestrator rendering")
    driver = r"""
const assert = require('assert');
const source = require('fs').readFileSync(process.argv[1], 'utf8');
const esc = eval('(' + source.slice(source.indexOf('function esc('),
  source.indexOf('\n}', source.indexOf('function esc(')) + 2) + ')');
const view = {innerHTML: ''};
const results = {innerHTML: ''};
let submit;
const fields = {};
const form = {
  elements: {namedItem: name => fields[name] ||= {}},
  addEventListener: (event, callback) => {submit = callback;},
};
const document = {getElementById: id => id === 'orchestrator-query' ? form : results};
const api = async () => ({
  routes: [], reasons: [], message: 'No eligible routes',
  rejected: [{route_id: '<route>', reason: 'Privacy <blocked>'}],
  catalog: [{route_id: '<route>', provider: 'local', model: '<model>',
    quality: 'standard', cost_tier: 'local_only', capabilities: ['chat'], notes: '<script>unsafe</script>'}],
  options: {capabilities: ['chat'], cost_tiers: ['local_only'], privacy: ['local_only']},
});
eval(source.slice(source.indexOf('async function renderOrchestrator()')));
(async () => {
  await renderOrchestrator();
  assert(view.innerHTML.includes('does not interpret natural-language'));
  assert(results.innerHTML.includes('No eligible routes'));
  assert(results.innerHTML.includes('Privacy &lt;blocked&gt;'));
  assert(results.innerHTML.includes('&lt;script&gt;unsafe&lt;/script&gt;'));
  assert(!results.innerHTML.includes('<script>'));
  assert(fields.capability.innerHTML.includes('chat'));
  assert(submit);
})().catch(err => {console.error(err); process.exit(1);});
"""
    subprocess.run([node, "-e", driver, str(WEB_DIR / "app.js")], check=True)
