"use strict";
/* Dashboard UI: hash routing, one create menu, a visible receipt for every action. */

const view = document.getElementById("view");
const toasts = document.getElementById("toasts");
const badge = document.getElementById("inbox-badge");
const ideasBadge = document.getElementById("ideas-badge");

function toast(message, ok) {
  const el = document.createElement("div");
  el.className = "toast " + (ok === false ? "err" : "ok");
  el.textContent = message;
  toasts.appendChild(el);
  setTimeout(() => el.remove(), 6000);
}

async function api(path, options) {
  let response;
  try {
    response = await fetch(path, options);
  } catch (err) {
    throw new Error("Request failed: " + err.message);
  }
  let payload = null;
  try {
    payload = await response.json();
  } catch (err) {
    throw new Error("Bad server reply on " + path + " (HTTP " + response.status + ")");
  }
  if (!response.ok || payload.ok === false) {
    throw new Error(payload.error || ("HTTP " + response.status + " on " + path));
  }
  return payload;
}

function esc(text) {
  return String(text).replace(/[&<>"']/g, (ch) => (
    {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[ch]
  ));
}

/* Readable local timestamps; falls back to the raw value when unparseable. */
function fmtTime(value) {
  if (!value) return "?";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleString();
}

async function refreshBadge() {
  try {
    const status = await api("/api/status");
    if (status.open_inbox > 0) {
      badge.textContent = status.open_inbox;
      badge.hidden = false;
    } else {
      badge.hidden = true;
    }
    if (status.new_ideas > 0) {
      ideasBadge.textContent = status.new_ideas;
      ideasBadge.hidden = false;
    } else {
      ideasBadge.hidden = true;
    }
  } catch (err) {
    badge.hidden = true;
    ideasBadge.hidden = true;
  }
}

const GLOSSARY = {
  D4: "Dashboard batch: +New menu, Mark-seen badge, chat cancel, tooltips",
  W1: "Edge finding: ide_bridge httpx import (false positive, reverted)",
  W2: "Edge finding: external agent without try/finally orphans live agents",
  W3: "Edge finding: agent timeout_seconds is inactivity-only",
  W4: "Edge finding: malformed poll JSON bypassed cancel-on-abandon (fixed)",
  H1: "Edge finding: hosted runs queued but never drained",
  M1: "Edge finding: failed live inference dropped the chat message",
  STT: "Speech-to-text dictation (Meta server + browser fallback; auto-slices at 55 s)",
  R1: "Backlog: company offering drafts",
  R2: "Backlog: Codeministry name + legality research",
  R3: "Backlog: marketing + social bots research",
  T0: "L3 ladder tier 0 (smoke)",
  T1: "L3 ladder tier 1",
  T2: "L3 ladder tier 2",
  T3: "L3 ladder tier 3 (full)",
  L3: "Live L3 capability ladder",
  BYOK: "Bring your own key: provider API key on top of OpenRouter",
};
function gloss(term) {
  if (Object.hasOwn(GLOSSARY, term)) return GLOSSARY[term];
  if (/^W\d+$/.test(term)) return "Edge finding — see the edge-round1-workbench plan";
  if (/^[HM]\d+$/.test(term)) return "Edge finding — see the edge-round1-operator plan";
  return term;
}
function gtext(s) {
  return esc(s).replace(
    /\b(D4|W\d+|H\d+|M\d+|STT|R[1-3]|T[0-3]|L3|BYOK)\b/g,
    (m) => `<abbr title="${gloss(m)}">${m}</abbr>`);
}

/* Client-side list filter over already-fetched items (no backend change). */
function filterList(listId, query) {
  const q = String(query || "").trim().toLowerCase();
  document.querySelectorAll("#" + listId + " li").forEach((li) => {
    li.hidden = q !== "" && !li.textContent.toLowerCase().includes(q);
  });
}

/* Project filter shared by the Runs and Inbox list views. */
let runsProjectFilter = "";
let inboxProjectFilter = "";
async function projectOptions(selected) {
  try {
    const data = await api("/api/projects");
    const opts = (data.projects || []).map((p) =>
      `<option value="${esc(p.id)}"${p.id === selected ? " selected" : ""}>${gtext(p.name)}</option>`).join("");
    return `<option value="">All projects</option>` + opts;
  } catch (err) { return `<option value="">All projects</option>`; }
}

/* Runs list auto-refresh: poll /api/runs every ~10s while the view is visible. */
let runsPollTimer = null;
function stopRunsPoll() {
  if (runsPollTimer) { clearInterval(runsPollTimer); runsPollTimer = null; }
}
function startRunsPoll() {
  if (runsPollTimer) return;
  runsPollTimer = setInterval(async () => {
    if (document.hidden) return;
    const hash = location.hash || "";
    if (hash !== "#/runs" && !hash.startsWith("#/runs?")) return;
    try { await renderRuns(); } catch (err) { /* next tick retries */ }
  }, 10000);
}

/* Inbox badge: honest live open count from /api/inbox every ~10s.
   Best-effort read-only refresh; opening the inbox just re-renders,
   it never answers or acknowledges anything. */
let inboxPollTimer = null;
function stopInboxPoll() {
  if (inboxPollTimer) { clearInterval(inboxPollTimer); inboxPollTimer = null; }
}
async function pollInboxBadge() {
  try {
    const payload = await api("/api/inbox");
    const open = (payload.items || []).filter((t) => t.status === "open").length;
    if (open > 0) {
      badge.textContent = open;
      badge.hidden = false;
    } else {
      badge.hidden = true;
    }
  } catch (err) { /* keep the last badge; next tick retries */ }
}
function startInboxPoll() {
  if (inboxPollTimer) return;
  pollInboxBadge();
  inboxPollTimer = setInterval(async () => {
    if (document.hidden) return;
    await pollInboxBadge();
  }, 10000);
}

/* Run detail auto-refresh: re-read status + receipts every ~10s while
   the detail view is visible. Stopped on navigation (see render()). */
let runDetailPollTimer = null;
function stopRunDetailPoll() {
  if (runDetailPollTimer) { clearInterval(runDetailPollTimer); runDetailPollTimer = null; }
}
async function refreshRunDetail(id) {
  try {
    const payload = await api("/api/runs/" + encodeURIComponent(id));
    const run = payload.item;
    const statusEl = document.getElementById("run-status");
    if (statusEl) statusEl.textContent = [run.status, run.branch, run.commit].filter(Boolean).join(" · ");
    await renderReceiptsInto(id);
    await renderStagedInto(id);
  } catch (err) { /* next tick retries; never break the page */ }
}
function startRunDetailPoll(id) {
  if (runDetailPollTimer) return;
  runDetailPollTimer = setInterval(async () => {
    if (document.hidden) return;
    const here = (location.hash || "").split("?")[0];
    if (here !== "#/runs/" + id) return;
    await refreshRunDetail(id);
  }, 10000);
}

/* Events/receipts section: GET /api/runs/{id}/receipts -> {ok, receipts:[...]}.
   Missing endpoint (404) or empty list renders a graceful placeholder. */
function receiptHtml(r) {
  const rec = r && typeof r === "object" ? r : {};
  const title = rec.title || rec.kind || rec.type || "receipt";
  const turn = rec.turn != null ? "Turn " + rec.turn + " — " : "";
  const when = rec.created_at_utc || rec.created_at || rec.at || rec.ts || "";
  const body = rec.body || rec.message || rec.detail || rec.text || "";
  return `<details class="turn"><summary>${esc(turn + title)}`
    + `${when ? ` <span class="muted">${esc(when)}</span>` : ""}</summary>`
    + `<div>${body ? esc(body) : esc(JSON.stringify(rec))}</div></details>`;
}
async function renderReceiptsInto(id) {
  const list = document.getElementById("receipts-list");
  if (!list) return;
  let receipts = null;
  try {
    const data = await api("/api/runs/" + encodeURIComponent(id) + "/receipts");
    receipts = Array.isArray(data.receipts) ? data.receipts : [];
  } catch (err) { receipts = null; }
  if (!receipts || !receipts.length) {
    list.innerHTML = '<p class="muted">No receipts yet.</p>';
    return;
  }
  list.innerHTML = receipts.map(receiptHtml).join("");
}

/* Project picker: GET /api/work-roots -> {ok, roots:[{id,path,display_name}]}.
   Empty roots or a failed fetch hides the picker with an honest note and
   run requests stay unscoped. */
async function loadProjectPicker() {
  const picker = document.getElementById("project-picker");
  const note = document.getElementById("project-note");
  if (!picker || !note) return;
  let roots = null;
  try {
    const data = await api("/api/work-roots");
    roots = Array.isArray(data.roots) ? data.roots : [];
  } catch (err) { roots = null; }
  if (roots === null) {
    picker.hidden = true;
    note.textContent = "Project list unavailable — runs stay unscoped.";
    return;
  }
  if (!roots.length) {
    picker.hidden = true;
    note.textContent = "No project roots configured — runs stay unscoped.";
    return;
  }
  picker.hidden = false;
  note.textContent = "";
  picker.innerHTML = '<option value="">No project (unscoped run)</option>'
    + roots.map((r) => `<option value="${esc(r.id)}">${esc(r.display_name || r.path)}</option>`).join("");
}

async function loadPlanPicker() {
  const picker = document.getElementById("plan-picker");
  const note = document.getElementById("plan-note");
  if (!picker || !note) return;
  let plans = null;
  try {
    const data = await api("/api/plans");
    plans = Array.isArray(data.items) ? data.items : [];
  } catch (err) { plans = null; }
  if (plans === null) {
    picker.hidden = true;
    note.textContent = "Plan list unavailable - run stays unlinked.";
    return;
  }
  if (!plans.length) {
    picker.hidden = true;
    note.textContent = "No plans on file - run stays unlinked.";
    return;
  }
  picker.hidden = false;
  note.textContent = "";
  picker.innerHTML = '<option value="">No plan (unlinked run)</option>'
    + plans.map((p) => `<option value="${esc(p.id)}">${esc(p.title || p.id)}</option>`).join("");
}

/* Staged project changes: GET /api/runs/{id}/staged -> {ok, files:[...]}.
   Missing endpoint (404) or empty list renders a graceful placeholder. */
function stagedFileHtml(f) {
  const file = f && typeof f === "object" ? f : {};
  const rel = file.relpath || "file";
  const diff = file.diff || "(no diff available)";
  return `<div class="staged-file"><h4>${esc(rel)}</h4><pre>${esc(diff)}</pre></div>`;
}
async function renderStagedInto(id) {
  const list = document.getElementById("staged-list");
  if (!list) return;
  let files = null;
  try {
    const data = await api("/api/runs/" + encodeURIComponent(id) + "/staged");
    files = Array.isArray(data.files) ? data.files : [];
  } catch (err) { files = null; }
  if (files === null) {
    list.innerHTML = '<p class="muted">Staged changes unavailable.</p>';
    return;
  }
  if (!files.length) {
    list.innerHTML = '<p class="muted">No staged changes.</p>';
    return;
  }
  const applied = list.dataset.applied === "1";
  list.innerHTML = files.map(stagedFileHtml).join("")
    + (applied
      ? '<p class="muted">Applied — see the project root for current files.</p>'
      : `<p><button id="staged-approve-btn" title="Approve and apply these staged files to the project root">Approve and apply</button>
        <button id="staged-reject-btn" title="Reject these staged files (nothing is applied)">Reject staged</button></p>`);
  if (!applied) wireStagedButtons(id);
}
async function decideStaged(id, approved) {
  try {
    await api("/api/runs/" + encodeURIComponent(id) + "/approve-staged", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({approved}),
    });
    toast(approved ? "Staged changes applied" : "Staged changes rejected", true);
    render();
  } catch (err) {
    toast(err.message, false);
  }
}
function wireStagedButtons(id) {
  const approveBtn = document.getElementById("staged-approve-btn");
  if (approveBtn) approveBtn.addEventListener("click", () => decideStaged(id, true));
  const rejectBtn = document.getElementById("staged-reject-btn");
  if (rejectBtn) rejectBtn.addEventListener("click", () => decideStaged(id, false));
}

/* P4 turn synthesis: Did/Found/Next line when the record carries it. */
function synthesisHtml(run) {
  if (typeof run.synthesis === "string" && run.synthesis.trim()) {
    return `<p id="run-synthesis">${gtext(run.synthesis.trim())}</p>`;
  }
  const parts = [["Did", run.did], ["Found", run.found], ["Next", run.next]]
    .filter(([, v]) => typeof v === "string" && v.trim());
  if (!parts.length) return "";
  return `<p id="run-synthesis">${parts.map(([k, v]) =>
    `<strong>${k}:</strong> ${gtext(v.trim())}`).join(" · ")}</p>`;
}

/* P4 phase header + checklist from the plan record; graceful when absent. */
function phaseChecklistHtml(plan) {
  const phases = Array.isArray(plan.phases) ? plan.phases : [];
  if (!phases.length) return '<p class="muted">No phases recorded yet.</p>';
  const rows = phases.map((p) => {
    const ph = p && typeof p === "object" ? p : {};
    const name = ph.title || ph.name || "phase";
    const st = ph.status || "pending";
    return `<li>${gtext(name)} <span class="pill st-${esc(st.replace(/\s+/g, "-"))}">${esc(st)}</span></li>`;
  }).join("");
  return `<ul class="plain checklist" id="phase-checklist">${rows}</ul>`;
}

async function renderHome() {
  const status = await api("/api/status");
  const plan = status.current_plan
    ? `<a href="#/plans/${esc(status.current_plan.id)}">${esc(status.current_plan.title || status.current_plan.id)}</a>`
    : '<span class="muted">No plan yet</span>';
  let spend = "";
  try {
    const sp = await api("/api/spend");
    const policy = sp.spend.policy || { rules: [], prepaid_spent_today_cents: 0 };
    const policyRules = policy.rules.map((r) =>
      `<li>${esc(r.scope)}: prepaid ${r.prepaid_allowed ? "allowed" : "blocked"}` + (r.max_prepaid_cents_per_day == null ? "" : `, cap ${esc(r.max_prepaid_cents_per_day)}&#162;/day`) + `</li>`).join("");
    spend = sp.spend.configured
      ? `<ul class="plain">${sp.spend.buckets.map((b) =>
          `<li><span class="pill" title="Allowance status">${esc(b.status)}</span> ${esc(b.provider)} ${esc(b.kind)} — ${esc(b.balance_cents)}/${esc(b.granted_cents)}¢</li>`).join("")}</ul>
        <p class="muted">${esc(sp.spend.open_reservations)} open reservation(s), ${esc(sp.spend.records)} record(s).</p>
        <p class="muted">Order: free &#8594; expiring &#8594; prepaid-if-allowed. Prepaid today: ${esc(policy.prepaid_spent_today_cents)}&#162;.</p>
        <ul class="plain">${policyRules}</ul>`
      : '<p class="muted">No spend grants configured — billable calls are denied by default.</p>';
  } catch (err) {
    spend = '<p class="muted">Spend unavailable: ' + esc(err.message) + "</p>";
  }
  const runs = status.recent_runs.length
    ? status.recent_runs.map((r) =>
        `<li><a href="#/runs/${esc(r.id)}">${esc(r.title || r.id)}</a> <span class="muted">${esc(r.status || "")}</span></li>`).join("")
    : '<li class="muted">No runs recorded</li>';
  view.innerHTML = `
    <h1>${esc(status.title)}</h1>
    <p class="muted">Backend: ${esc(status.provider)} / ${esc(status.model)}</p>
    <div class="columns">
      <div>
        <div class="card"><h2>Active plan</h2><p>${plan}</p>
          <p class="muted">${esc(status.plan_total)} plan(s) on file. <a href="#/plans">All plans</a></p></div>
        <div class="card"><h2>Recent runs</h2><ul class="plain">${runs}</ul></div>
        <div class="card"><h2>Evidence</h2>
          <p>${status.evidence.available
            ? `${esc(status.evidence.passed)} passed / ${esc(status.evidence.routes)} routes. <a href="#/runs">Details in Runs</a>`
            : 'No route snapshots yet. Run the provider probe/eval CLIs to populate.'}</p></div>
      </div>
      <div>
        <div class="card"><h2>Inbox</h2>
          <p>${status.open_inbox} open task(s). <a href="#/inbox">Open inbox</a></p></div>
        <div class="card"><h2>Spend</h2>${spend}</div>
        <div class="card"><h2>Ideas</h2>
          <p>${status.new_ideas} new — triage each in Ideas (adopt, park, or decline). <a href="#/ideas">Open ideas</a></p></div>
        <div class="card"><h2>Chat</h2>
          <form class="inline" id="quick-chat"><input type="text" name="text" placeholder="Ask the supervisor..." title="Ask the supervisor (starts a new chat)" required>
          <button type="submit" title="Start a chat with this question">Send</button></form></div>
        <div class="card"><h2>Scheduled</h2>
          <p class="muted">No scheduler yet — see P5. <a href="#/schedule">Schedule view</a></p></div>
      </div>
    </div>`;
  document.getElementById("quick-chat").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const text = ev.target.text.value.trim();
    if (!text) return;
    try {
      const session = await api("/api/chat/sessions", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({title: text.slice(0, 60)}),
      });
      toast("Chat started", true);
      location.hash = "#/chat/" + session.id + "?q=" + encodeURIComponent(text);
    } catch (err) {
      toast(err.message, false);
    }
  });
}

async function renderChatList() {
  const payload = await api("/api/chat/sessions");
  const items = payload.sessions.length
    ? payload.sessions.map((s) =>
        `<li><a href="#/chat/${esc(s.id)}">${esc(s.title)}</a>
         <span class="muted">${esc(s.updated_at_utc)} · ${esc(s.privacy_class)}</span></li>`).join("")
    : '<li class="muted">No chats yet — use + New.</li>';
  view.innerHTML = `<h1>Chat</h1>
    <p class="muted">Supervisor answers; queue agent runs for approval from a thread. Full transcripts stay local.</p>
    <ul class="plain">${items}</ul>`;
}

async function renderChatThread(id, initial) {
  const payload = await api("/api/chat/sessions/" + encodeURIComponent(id) + "/messages");
  const msgs = payload.messages.map((m) =>
    `<div class="msg"><span class="role">${esc(m.role)}</span>
     <span class="muted">${m.provider ? esc(m.provider + "/" + (m.model || "")) : ""}</span>
     <div>${esc(m.content)}</div></div>`).join("");
  const sessions = await api("/api/chat/sessions");
  const found = (sessions.sessions || []).find((s) => s.id === id) || {};
  view.innerHTML = `<h1>Chat: ${esc(found.title || id)}</h1><p><a href="#/chat">All chats</a></p>
    <form id="rename-form" class="inline"><input type="text" name="title" value="${esc(found.title || "")}" title="Chat title">
    <button type="submit" title="Rename this chat">Rename</button></form>
    <p><button id="delete-btn" title="Delete this chat and its transcript">Delete chat</button>
    <button type="button" id="draft-plan-btn" title="Draft a proposed plan from this chat transcript">Draft plan</button></p>
    <div id="thread">${msgs || '<p class="muted">No messages yet.</p>'}</div>
    <form class="inline" id="chat-form"><input type="text" name="text" placeholder="Message..." title="Message the supervisor" required>
    <button type="submit" title="Send message">Send</button>
    <button type="button" id="run-request-btn" title="Queue this message as an agent run (needs inbox approval)">Request run</button>
    <button type="button" id="dictate-btn" title="Dictate with the microphone (Meta server first, browser fallback)">Dictate</button></form>
    <p><select id="project-picker" title="Project for the next run request (optional)"></select>
    <span id="project-note" class="muted"></span></p>
    <p><select id="plan-picker" title="Plan this run implements (optional)"></select>
    <span id="plan-note" class="muted"></span></p>`;
  document.getElementById("rename-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const title = ev.target.title.value.trim();
    if (!title) { toast("Title must not be empty", false); return; }
    try {
      await api("/api/chat/sessions/" + encodeURIComponent(id) + "/rename", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({title}),
      });
      toast("Chat renamed", true);
      render();
    } catch (err) {
      toast(err.message, false);
    }
  });
  document.getElementById("draft-plan-btn").addEventListener("click", async () => {
    try {
      const out = await api("/api/chat/sessions/" + encodeURIComponent(id) + "/draft-plan", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: "{}",
      });
      toast("Draft plan opened: " + out.plan.id, true);
      location.hash = "#/plans/" + encodeURIComponent(out.plan.id);
    } catch (err) {
      toast(err.message, false);
    }
  });
  const deleteBtn = document.getElementById("delete-btn");
  deleteBtn.addEventListener("click", async () => {
    if (deleteBtn.dataset.armed !== "1") {
      deleteBtn.dataset.armed = "1";
      deleteBtn.textContent = "Confirm delete?";
      return;
    }
    try {
      await api("/api/chat/sessions/" + encodeURIComponent(id) + "/delete", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: "{}",
      });
      toast("Chat deleted", true);
      location.hash = "#/chat";
    } catch (err) {
      toast(err.message, false);
    }
  });
  const form = document.getElementById("chat-form");
  async function send(text) {
    const btn = form.querySelector("button");
    btn.disabled = true;
    btn.textContent = "Sending...";
    try {
      const out = await api("/api/chat/sessions/" + encodeURIComponent(id) + "/messages", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({text}),
      });
      toast("Answer received (" + out.execution_status + ")", true);
    } catch (err) {
      toast(err.message, false);
    } finally {
      render();
      btn.disabled = false;
      btn.textContent = "Send";
    }
  }
  form.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const text = ev.target.text.value.trim();
    if (text) send(text);
  });
  document.getElementById("run-request-btn").addEventListener("click", async () => {
    const text = form.text.value.trim();
    if (!text) { toast("Message text is required", false); return; }
    const picker = document.getElementById("project-picker");
    const project = picker && !picker.hidden ? picker.value || null : null;
    const planPicker = document.getElementById("plan-picker");
    const plan = planPicker && !planPicker.hidden ? planPicker.value || null : null;
    try {
      const out = await api("/api/chat/sessions/" + encodeURIComponent(id) + "/run-request", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({text, project, plan}),
      });
      toast("Run queued (fan-out: " + out.fanout_effective + ")", true);
      render();
    } catch (err) {
      toast(err.message, false);
    }
  });
  loadProjectPicker();
  loadPlanPicker();
  const dictateLang = () => ((navigator.language || "en").toLowerCase().startsWith("pl") ? "pl" : "en");
  async function transcribeSegment(blob, index) {
    const data = new FormData();
    data.append("audio", blob, "clip-" + index + ".webm");
    data.append("language", dictateLang());
    const res = await fetch("/api/stt/transcribe", {method: "POST", body: data});
    const out = await res.json();
    if (!res.ok || !out.ok) throw new Error(out.error || ("Transcription failed (" + res.status + ")"));
    return out;
  }
  async function dictateViaBrowser() {
    const Engine = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Engine) {
      toast("Dictation failed and no browser speech engine exists — type instead", false);
      return;
    }
    dictateBtn.textContent = "Listening (browser fallback)...";
    toast("Server transcription failed — browser fallback listening, speak now", true);
    try {
      const text = await new Promise((resolve, reject) => {
        let settled = false;
        const rec = new Engine();
        rec.lang = dictateLang() === "pl" ? "pl-PL" : "en-US";
        rec.interimResults = false;
        rec.maxAlternatives = 1;
        rec.onresult = (ev) => {
          if (!settled) { settled = true; resolve(ev.results[0][0].transcript); }
        };
        rec.onerror = (ev) => {
          if (!settled) { settled = true; reject(new Error(ev.error || "recognition error")); }
        };
        rec.onend = () => {
          if (!settled) { settled = true; reject(new Error("no speech heard")); }
        };
        rec.start();
      });
      form.text.value = (form.text.value ? form.text.value + " " : "") + text;
      toast("Dictated via browser fallback", true);
    } catch (err) {
      toast("Browser dictation failed: " + err.message + " — type instead", false);
    } finally {
      dictateBtn.textContent = "Dictate";
    }
  }
  let dictationRecorder = null;
  let dictationSegments = [];
  const dictateBtn = document.getElementById("dictate-btn");
  dictateBtn.addEventListener("click", async () => {
    if (dictationRecorder) { dictationRecorder.stop(); return; }
    if (!navigator.mediaDevices || !window.MediaRecorder) {
      dictateViaBrowser();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({audio: true});
      dictationSegments = [];
      const recorder = new MediaRecorder(stream);
      dictationRecorder = recorder;
      dictateBtn.dataset.live = "1";
      dictateBtn.textContent = "Stop (recording...)";
      recorder.ondataavailable = (ev) => { if (ev.data.size) dictationSegments.push(ev.data); };
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        dictationRecorder = null;
        dictateBtn.dataset.live = "";
        dictateBtn.textContent = "Dictate";
        const texts = [];
        let billed = 0;
        let failed = null;
        for (let i = 0; i < dictationSegments.length && !failed; i++) {
          try {
            const out = await transcribeSegment(dictationSegments[i], i);
            texts.push(out.text);
            billed += out.billed_seconds || 0;
          } catch (err) {
            failed = err;
          }
        }
        dictationSegments = [];
        if (texts.length) form.text.value = texts.join(" ");
        if (!failed) {
          toast("Dictated (" + dictateLang() + ", " + billed + "s billed)", true);
        } else if (texts.length) {
          toast("Partial dictation kept; server failed (" + failed.message + ") — browser fallback next", false);
          dictateViaBrowser();
        } else {
          toast("Dictation failed: " + failed.message + " — trying browser fallback", false);
          dictateViaBrowser();
        }
      };
      // 55 s slices stay under the server 60 s cap; long recordings transcribe
      // sequentially instead of being whole-clip rejected (6f89d44d).
      recorder.start(55000);
    } catch (err) {
      toast("Microphone unavailable: " + err.message, false);
    }
  });
  if (initial) send(initial);
}

async function renderPlans(id) {
  if (id) {
    const payload = await api("/api/plans/" + encodeURIComponent(id));
    const plan = payload.item;
    let linkedRuns = "";
    try {
      const runs = await api("/api/runs?plan_id=" + encodeURIComponent(id));
      linkedRuns = runs.items.length
        ? `<h3>Linked runs</h3><ul class="plain">` + runs.items.map((r) =>
            `<li><a href="#/runs/${esc(r.id)}">${gtext(r.title || r.id)}</a>
             <span class="pill st-${esc((r.status || "none").replace(/\s+/g, "-"))}">${esc(r.status || "")}</span></li>`).join("") + `</ul>`
        : "";
    } catch (err) { linkedRuns = ""; }
    view.innerHTML = `<h1>Plan</h1><p><a href="#/plans">All plans</a></p>
      <div class="card"><h2>${gtext(plan.title || plan.id)}</h2>
      <p class="muted">${esc(plan.status || "")}${plan.updated_at_utc ? " · updated " + esc(plan.updated_at_utc) : ""}</p>
      <p><strong>Phase:</strong> <span class="pill">${esc(plan.phase || plan.status || "unknown")}</span></p>
      ${plan.source ? `<p class="muted">Source: ${esc(plan.source)}</p>` : ""}
      <h3>Phase checklist</h3>
      ${phaseChecklistHtml(plan)}
      <pre>${gtext(plan.body || "(empty plan)")}</pre>${linkedRuns}</div>`;
    return;
  }
  const payload = await api("/api/plans");
  const items = payload.items.length
    ? payload.items.map((p) =>
        `<li><a href="#/plans/${esc(p.id)}">${gtext(p.title || p.id)}</a>
         <span class="pill st-${esc((p.status || "none").replace(/\s+/g, "-"))}">${esc(p.status || "")}</span></li>`).join("")
    : '<li class="muted">No plans on file. Plans are created by Workbench flows.</li>';
  view.innerHTML = `<h1>Plans</h1>
    <p><input type="text" id="filter-plans" placeholder="Filter plans..." title="Filter plans by text"></p>
    <ul class="plain" id="plans-list">${items}</ul><p class="muted">${payload.total} total.</p>`;
  document.getElementById("filter-plans").addEventListener("input", (ev) => filterList("plans-list", ev.target.value));
}

async function renderRuns(id) {
  if (id) {
    stopRunsPoll();
    stopRunDetailPoll();
    const payload = await api("/api/runs/" + encodeURIComponent(id));
    const run = payload.item;
    const meta = [run.status, run.branch, run.commit].filter(Boolean).map(esc).join(" · ");
    const fanout = run.fanout_effective || run.fanout_policy || "unknown";
    const report = run.report
      ? `<h3>Report</h3><pre>${gtext(run.report)}</pre>`
      : run.report_request_id
        ? `<p class="muted">Report requested — see the inbox task.</p>`
        : `<p><button id="report-btn" title="Ask for a completion report for this run">Generate report</button></p>`;
    const diff = run.diff
      ? `<h3>Diff</h3><pre id="run-diff">${gtext(run.diff)}</pre>`
      : "";
    const inboxLink = run.inbox_id
      ? `<p><a href="#/inbox/${esc(run.inbox_id)}" title="Approve or reject via the linked inbox task">Review approval in inbox</a></p>`
      : "";
    const planLink = run.plan_id
      ? `<p><a href="#/plans/${esc(run.plan_id)}" title="Open the plan this run implements">View plan</a></p>`
      : "";
    const failure = run.failure
      ? `<div class="card" title="Why this run failed"><h2><span class="pill st-failed">failed</span> Run failed</h2>` +
        (run.failure.reason ? `<p>${esc(run.failure.reason)}</p>` : `<p class="muted">No reason recorded.</p>`) +
        (run.failure.at_utc ? `<p class="muted">${esc(run.failure.at_utc)}</p>` : "") + `</div>`
      : "";
    view.innerHTML = `<h1>Run</h1><p><a href="#/runs">All runs</a></p>
      ${failure}
      <div class="card"><h2>${gtext(run.title || run.id)}</h2>
      <p class="muted" id="run-status">${meta}</p>
      <p title="Whether this run may spawn subagent children"><strong>Fan-out:</strong> <span class="pill">${esc(fanout)}</span></p>
      ${synthesisHtml(run)}
      ${run.validation ? `<p><strong>Validation:</strong> ${esc(run.validation)}</p>` : ""}
      ${run.body ? `<pre>${gtext(run.body)}</pre>` : ""}
      ${diff}
      <h3>Staged project changes</h3>
      <div id="staged-list" data-applied="${run.staged_applied ? "1" : ""}"><p class="muted">Loading staged changes...</p></div>
      <h3>Events and receipts</h3>
      <div id="receipts-list"><p class="muted">Loading receipts...</p></div>
      ${inboxLink}${planLink}
      ${report}</div>`;
    renderReceiptsInto(id);
    renderStagedInto(id);
    startRunDetailPoll(id);
    const reportBtn = document.getElementById("report-btn");
    if (reportBtn) reportBtn.addEventListener("click", async () => {
      try {
        await api("/api/runs/" + encodeURIComponent(id) + "/report-request", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: "{}",
        });
        toast("Report requested — see inbox", true);
        render();
      } catch (err) {
        toast(err.message, false);
      }
    });
    return;
  }
  const prevFilter = (document.getElementById("filter-runs") || {}).value || "";
  const runsUrl = runsProjectFilter ? "/api/runs?project_id=" + encodeURIComponent(runsProjectFilter) : "/api/runs";
  const payload = await api(runsUrl);
  const items = payload.items.length
    ? payload.items.map((r) =>
        `<li><a href="#/runs/${esc(r.id)}">${gtext(r.title || r.id)}</a>
         <span class="pill st-${esc((r.status || "none").replace(/\s+/g, "-"))}">${esc(r.status || "")}</span>
         <span class="pill" title="Fan-out policy: whether this run may spawn subagent children">fan-out: ${esc(r.fanout_effective || r.fanout_policy || "unknown")}</span></li>`).join("")
    : '<li class="muted">No runs recorded.</li>';
  let evidence = "";
  try {
    const ev = await api("/api/evidence");
    evidence = ev.available
      ? `<h2>Route evidence</h2><ul class="plain">${ev.routes.map((row) =>
          `<li>${esc(row.route)} — ${row.reachable ? "reachable" : "unreachable"}${
            row.passed_eval === true ? ", eval PASS" : row.passed_eval === false ? ", eval FAIL" : ""}</li>`).join("")}</ul>
        <p class="muted">${esc(ev.probe_snapshot || "no probe")} · ${esc(ev.eval_snapshot || "no eval")}</p>`
      : '<p class="muted">No route snapshots yet.</p>';
  } catch (err) {
    evidence = '<p class="muted">Evidence unavailable: ' + esc(err.message) + "</p>";
  }
  view.innerHTML = `<h1>Runs</h1>
    <p><input type="text" id="filter-runs" placeholder="Filter runs..." title="Filter runs by text">
    <select id="filter-runs-project" title="Show runs for one project">${await projectOptions(runsProjectFilter)}</select>
    <button id="drain-runs" title="Execute approved queued runs (one per click)">Drain now</button></p>
    <ul class="plain" id="runs-list">${items}</ul>${evidence}`;
  const filterInput = document.getElementById("filter-runs");
  filterInput.addEventListener("input", (ev) => filterList("runs-list", ev.target.value));
  if (prevFilter) { filterInput.value = prevFilter; filterList("runs-list", prevFilter); }
  document.getElementById("filter-runs-project").addEventListener("change", (ev) => {
    runsProjectFilter = ev.target.value; renderRuns();
  });
  document.getElementById("drain-runs").addEventListener("click", async (ev) => {
    const btn = ev.target;
    btn.disabled = true;
    try {
      const out = await api("/api/runs/drain", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: "{}",
      });
      const ran = out.outcomes.filter((o) => !o.action).length;
      toast("Drain: " + ran + " executed, " + (out.outcomes.length - ran) + " parked/skipped", true);
      renderRuns();
    } catch (err) {
      toast(err.message, false);
      btn.disabled = false;
    }
  });
  startRunsPoll();
}

async function renderInbox(id) {
  if (id) {
    const payload = await api("/api/inbox/" + encodeURIComponent(id));
    const item = payload.item;
    const options = (item.options || []).map((opt, i) =>
      `<label><input type="radio" name="opt" value="${i}"> ${esc(opt)}</label><br>`).join("");
    const refs = (item.context_refs || []).map((r) => `<li>${esc(r)}</li>`).join("");
    const stamp = (v) => v ? esc(v.slice(0, 16).replace("T", " ")) : "";
    const record = (item.options || []).length && item.status === "closed"
      ? `<h3>Choices offered</h3><ol>${item.options.map((o) => `<li>${esc(o)}</li>`).join("")}</ol>` : "";
    const outcome = item.resolution
      ? `<h3>Outcome</h3><p class="inbox-body">${gtext(item.resolution)}</p>`
        + (item.resolved_at ? `<p class="muted">Resolved ${stamp(item.resolved_at)}</p>` : "")
      : "";
    const decision = item.answer || item.note
      ? `${item.answer ? `<p><strong>Answer:</strong> ${esc(item.answer)}</p>` : ""}
         ${item.note ? `<p><strong>Note:</strong> ${esc(item.note)}</p>` : ""}
         ${item.answered_at ? `<p class="muted">Answered ${stamp(item.answered_at)}</p>` : ""}`
      : '<p class="muted">No answer recorded yet.</p>';
    view.innerHTML = `<h1>Inbox task</h1><p><a href="#/inbox">All tasks</a></p>
      <div class="card"><h2>${gtext(item.title)}</h2>
      <p class="muted">${esc(item.type)} · ${esc(item.status)} · from ${esc(item.created_by || "")} · opened ${stamp(item.created_at)}</p>
      <h3>Request</h3>
      <p class="inbox-body">${gtext(item.body || "")}</p>
      ${item.type === "task" ? '<p class="muted">Do the steps above, then answer Done with a note. Never paste secrets here — put keys in .env / User env.</p>' : ""}
      ${refs ? `<ul class="plain">${refs}</ul>` : ""}
      ${record}
      <h3>Decision record</h3>
      ${decision}
      ${outcome}
      ${item.status === "closed"
        ? `<p class="muted">Closed; answers are immutable.</p>`
          + `<p><button id="reopen-btn" title="Return this task to the active list">Reopen task</button></p>`
        : `
      <h3>Your choices</h3>
      <form id="answer-form">
        ${options}
        ${options ? '<p class="muted">Pick one, add a note, or both — the note expands your choice.</p>' : ""}
        <div><input type="text" name="answer" placeholder="${options ? "Add a note (optional)..." : "Your answer..."}" title="${options ? "Optional note expanding your choice" : "Type your answer"}"></div>
        <p><button type="submit" title="Record your choice and note">Submit answer</button></p>
      </form>
      <h3>Actions</h3>
      <form id="close-form">
        <div><textarea name="resolution" rows="3" placeholder="Outcome note (required) — what was implemented, with technical details..." title="Implementation outcome, stored with the archived task"></textarea></div>
        <p><button type="submit" title="Record the outcome and archive this task">Close with outcome</button></p>
      </form>`}</div>`;
    const form = document.getElementById("answer-form");
    if (form) form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const checked = form.querySelector("input[name=opt]:checked");
      try {
        await api("/api/inbox/" + encodeURIComponent(id) + "/answer", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            answer: ev.target.answer.value,
            option_index: checked ? Number(checked.value) : null,
          }),
        });
        toast("Answer recorded", true);
        render();
      } catch (err) {
        toast(err.message, false);
      }
    });
    const closeForm = document.getElementById("close-form");
    if (closeForm) closeForm.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      try {
        await api("/api/inbox/" + encodeURIComponent(id) + "/close", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({resolution: ev.target.resolution.value}),
        });
        toast("Outcome recorded, task archived", true);
        render();
      } catch (err) {
        toast(err.message, false);
      }
    });
    const reopenBtn = document.getElementById("reopen-btn");
    if (reopenBtn) reopenBtn.addEventListener("click", async () => {
      try {
        await api("/api/inbox/" + encodeURIComponent(id) + "/reopen", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: "{}",
        });
        toast("Task reopened", true);
        render();
      } catch (err) {
        toast(err.message, false);
      }
    });
    return;
  }
  const tab = new URLSearchParams((location.hash.split("?")[1] || "")).get("status") || "active";
  const inboxUrl = inboxProjectFilter ? "/api/inbox?project_id=" + encodeURIComponent(inboxProjectFilter) : "/api/inbox";
  const payload = await api(inboxUrl);
  const shown = payload.items.filter((t) => tab === "archive" ? t.status === "closed" : tab === "queue" ? (t.assignee === "agent" && t.status === "open") : t.status !== "closed");
  const items = shown.length
    ? shown.map((t) =>
        `<li><a href="#/inbox/${esc(t.id)}">${gtext(t.title)}</a>
         <span class="pill st-${esc((t.status || "none").replace(/\s+/g, "-"))}">${esc(t.type)} · ${esc(t.status)}${t.assignee === "agent" ? " · for AI" : ""}</span></li>`).join("")
    : '<li class="muted">Nothing here. The supervisor assigns decisions and tasks to the inbox.</li>';
  view.innerHTML = `<h1>Inbox</h1>
    <p><a href="#/inbox">Active</a> · <a href="#/inbox?status=queue">AI queue</a> · <a href="#/inbox?status=archive">Archive</a></p>
    <p><input type="text" id="filter-inbox" placeholder="Filter tasks..." title="Filter inbox by text">
    <select id="filter-inbox-project" title="Show inbox tasks for one project">${await projectOptions(inboxProjectFilter)}</select></p>
    <ul class="plain" id="inbox-list">${items}</ul>`;
  document.getElementById("filter-inbox").addEventListener("input", (ev) => filterList("inbox-list", ev.target.value));
  document.getElementById("filter-inbox-project").addEventListener("change", (ev) => {
    inboxProjectFilter = ev.target.value; renderInbox();
  });
}

async function markIdeaSeen(id, item) {
  if (!item || item.status !== "new") return;
  try {
    await api("/api/ideas/" + encodeURIComponent(id) + "/review", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({status: "reviewing", decision: item.decision || ""}),
    });
    item.status = "reviewing";
  } catch (err) {
    /* Render the fetched copy; the badge refreshes anyway. */
  }
}

async function renderIdeas(id) {
  if (id) {
    const payload = await api("/api/ideas/" + encodeURIComponent(id));
    const item = payload.item;
    const opts = ["new", "reviewing", "adopted", "parked", "declined"].map((s) =>
      `<option value="${s}"${item.status === s ? " selected" : ""}>${s}</option>`).join("");
    view.innerHTML = `<h1>Idea</h1><p><a href="#/ideas">All ideas</a></p>
      <div class="card"><h2>${gtext(item.title)}</h2>
      <p class="muted">${esc(item.source)}${item.contact ? " · " + esc(item.contact) : ""} · ${esc(item.status)}</p>
      <p class="inbox-body">${gtext(item.body || "")}</p>
      ${item.decision ? `<p><strong>Decision:</strong> ${esc(item.decision)}</p>` : ""}
      ${item.status === "new" ? `<p><button id="mark-seen-btn" title="Mark this idea seen (moves it out of new)">Mark seen</button></p>` : ""}
      <form id="review-form" class="inline">
        <select name="status" title="Triage status">${opts}</select>
        <input type="text" name="decision" placeholder="Decision note..." title="Decision note (optional)" value="${esc(item.decision || "")}">
        <button type="submit" title="Save triage status and note">Save triage</button>
      </form></div>`;
    document.getElementById("review-form").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      try {
        await api("/api/ideas/" + encodeURIComponent(id) + "/review", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({status: ev.target.status.value, decision: ev.target.decision.value}),
        });
        toast("Triage saved", true);
        render();
      } catch (err) {
        toast(err.message, false);
      }
    });
    const seenBtn = document.getElementById("mark-seen-btn");
    if (seenBtn) seenBtn.addEventListener("click", async () => {
      await markIdeaSeen(id, item);
      render();
    });
    return;
  }
  const payload = await api("/api/ideas");
  const items = payload.items.length
    ? payload.items.map((t) =>
        `<li><a href="#/ideas/${esc(t.id)}">${gtext(t.title)}</a>
         <span class="muted">${esc(t.source)} · ${esc((t.created_at || "").slice(0, 10))}</span>
         <span class="pill st-${esc((t.status || "none").replace(/\s+/g, "-"))}">${esc(t.status)}</span></li>`).join("")
    : '<li class="muted">No ideas captured yet — use + New.</li>';
  view.innerHTML = `<h1>Ideas</h1>
    <p class="muted">Capture inbox for brain-dumps and third-party wishes. Triage in planning sessions.</p>
    <p><input type="text" id="filter-ideas" placeholder="Filter ideas..." title="Filter ideas by text"></p>
    <ul class="plain" id="ideas-list">${items}</ul>`;
  document.getElementById("filter-ideas").addEventListener("input", (ev) => filterList("ideas-list", ev.target.value));
}

async function renderDocuments(id) {
  if (id) {
    const payload = await api("/api/documents/" + id.split("/").map(encodeURIComponent).join("/"));
    const item = payload.entry;
    let body = `<p><a href="/api/documents/${id.split("/").map(encodeURIComponent).join("/")}/file" target="_blank" rel="noopener" title="Open the file (browser opens PDFs, other types download)">Open file</a></p>`;
    if (item.renderable) {
      try {
        const full = await api("/api/documents/" + id.split("/").map(encodeURIComponent).join("/") + "?content=1");
        body += `<div class="doc-body">${mdToHtml(full.content)}</div>`
          + (full.truncated ? '<p class="muted">Preview truncated at 100 KB — open the file for the rest.</p>' : "");
      } catch (err) {
        body += `<p class="muted">Preview unavailable: ${esc(err.message)} — open the file instead.</p>`;
      }
    } else {
      body += '<p class="muted">No in-tab preview for this file type — open it with one click above.</p>';
    }
    view.innerHTML = `<h1>Document</h1><p><a href="#/documents">All documents</a></p>
      <div class="card"><h2>${esc(item.title)}</h2>
      <p class="muted">${esc(item.root)} · ${esc(item.sensitivity)} · ${esc((item.modified_utc || "").slice(0, 10))} · ${item.size} bytes</p>
      ${(item.tags || []).length ? `<p>${item.tags.map((t) => `<span class="pill">${esc(t)}</span>`).join(" ")}</p>` : ""}
      ${item.project ? `<p><strong>Project:</strong> ${esc(item.project)}</p>` : ""}
      ${body}</div>`;
    return;
  }
  const payload = await api("/api/documents");
  const items = payload.documents.length
    ? payload.documents.map((d) =>
        `<li><a href="#/documents/${encodeURIComponent(d.id)}">${esc(d.title)}</a>
         <span class="muted">${esc(d.root)} · ${esc((d.modified_utc || "").slice(0, 10))}</span>
         <span class="pill st-${esc(d.sensitivity)}">${esc(d.sensitivity)}</span>
         ${d.project ? `<span class="pill" title="Linked project">${esc(d.project)}</span>` : ""}</li>`).join("")
    : '<li class="muted">No documents yet.</li>';
  view.innerHTML = `<h1>Documents</h1>
    <p class="muted">Company knowledge: public library, private research, and existing plans. Private files never leave this PC.</p>
    <p><input type="text" id="filter-documents" placeholder="Filter documents..." title="Filter documents by text"></p>
    <ul class="plain" id="documents-list">${items}</ul>`;
  document.getElementById("filter-documents").addEventListener("input", (ev) => filterList("documents-list", ev.target.value));
}

async function renderIntake() {
  const payload = await api("/api/intake");
  const items = payload.files.length
    ? payload.files.map((f) =>
        `<li><strong>${esc(f.name)}</strong>
         <span class="pill st-${f.valid ? "ready" : "draft"}">${f.valid ? "ready" : "draft"}</span>
         <br><span class="muted">${gtext(f.summary || "no summary")}</span>
         ${f.errors.length ? `<br><span class="muted">Errors: ${esc(f.errors.join("; "))}</span>` : ""}
         ${f.warnings.length ? `<br><span class="muted">Warnings: ${esc(f.warnings.join("; "))}</span>` : ""}
         ${f.valid ? `<br><button data-approve="${esc(f.name)}" title="Approve this brief into a proposed plan">Approve into plan</button>` : ""}</li>`).join("")
    : '<li class="muted">No intake files. Drop chatbot briefs into p7-projects/ (gitignored, stays on this PC).</li>';
  view.innerHTML = `<h1>Client intake</h1>
    <p class="muted">Review website briefs, then approve valid ones into draft plans. Nothing executes or spends.</p>
    <ul class="plain" id="intake-list">${items}</ul>`;
  view.querySelectorAll("[data-approve]").forEach((btn) => btn.addEventListener("click", async () => {
    try {
      const out = await api("/api/intake/" + encodeURIComponent(btn.dataset.approve) + "/approve", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: "{}",
      });
      toast("Draft plan opened: " + out.plan.id, true);
      renderIntake();
    } catch (err) {
      toast(err.message, false);
    }
  }));
}

function fieldRow(label, inner, hint) {
  return `<p><label><strong>${label}</strong><br>${inner}</label><br><span class="muted">${hint}</span></p>`;
}
function renderCreate(kind) {
  const defs = {
    chat: {heading: "New chat", fields: `
      ${fieldRow("Title *", '<input type="text" id="f-title" value="Dashboard chat" title="Chat title (required)">', "required")}`},
    inbox: {heading: "New inbox item", fields: `
      ${fieldRow("Title *", '<input type="text" id="f-title" title="Inbox item title (required)">', "required")}
      ${fieldRow("Details", '<textarea id="f-body" rows="3" title="Details (optional)"></textarea>', "optional")}
      ${fieldRow("Type *", `<select id="f-type" title="Item type (required)"><option value="clarification">clarification</option><option value="decision">decision</option><option value="task">task</option></select>`, "required")}
      ${fieldRow("For *", `<select id="f-for" title="Who should do this (required)"><option value="owner">me</option><option value="agent">AI agent</option></select>`, "required")}`},
    idea: {heading: "New idea", fields: `
      ${fieldRow("Title *", '<input type="text" id="f-title" title="Idea title (required)">', "required")}
      ${fieldRow("Description", '<textarea id="f-body" rows="3" title="Description (optional)"></textarea>', "optional")}
      ${fieldRow("Origin *", `<select id="f-source" title="Whose idea (required)"><option value="owner">mine</option><option value="third-party">someone else's</option></select>`, "required")}
      ${fieldRow("Contact", '<input type="text" id="f-contact" title="Name or contact (only for third-party ideas)">', "only for third-party ideas")}`},
  };
  const def = defs[kind];
  if (!def) { view.innerHTML = "<h1>Not found</h1>"; return; }
  view.innerHTML = `<h1>${def.heading}</h1><form id="create-form">${def.fields}
    <p><button type="submit" title="Create this item">Create</button>
    <button type="button" id="create-cancel" title="Cancel without creating anything">Cancel</button></p></form>`;
  document.getElementById("create-cancel").addEventListener("click", () => history.back());
  document.getElementById("create-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const createBtn = ev.target.querySelector("button[type=submit]");
    const title = document.getElementById("f-title").value.trim();
    if (!title) { toast("Title is required", false); return; }
    createBtn.disabled = true;
    try {
      if (kind === "chat") {
        const session = await api("/api/chat/sessions", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({title}),
        });
        toast("Chat created", true);
        location.hash = "#/chat/" + session.id;
      } else if (kind === "inbox") {
        const out = await api("/api/inbox", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            title,
            body: document.getElementById("f-body").value,
            type: document.getElementById("f-type").value,
            created_by: "owner",
            assignee: document.getElementById("f-for").value,
          }),
        });
        toast("Inbox item created", true);
        location.hash = "#/inbox/" + out.id;
      } else if (kind === "idea") {
        const out = await api("/api/ideas", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            title,
            body: document.getElementById("f-body").value,
            source: document.getElementById("f-source").value,
            contact: document.getElementById("f-contact").value,
          }),
        });
        toast("Idea captured", true);
        location.hash = "#/ideas/" + out.id;
      }
    } catch (err) {
      createBtn.disabled = false;
      toast(err.message, false);
    }
  });
}

async function renderSchedule() {
  let body = "";
  try {
    const payload = await api("/api/fleet");
    const f = payload.fleet;
    const upcoming = f.tasks
      .filter((t) => t.present && t.next_run)
      .sort((a, b) => (a.next_run < b.next_run ? -1 : 1));
    const recurring = f.tasks.filter((t) => t.present && !t.next_run);
    const upRows = upcoming.map((t) =>
      `<li><strong>${esc(fmtTime(t.next_run))}</strong> — ${esc(t.name)} <span class="muted">${esc(t.state || "")}</span>${t.explain ? ` <span class="muted">— ${esc(t.explain)}</span>` : ""}</li>`).join("");
    const sleepRow = f.sleep.active
      ? `<li><strong>${esc(fmtTime(f.sleep.due_utc))}</strong> — sleep guard due <span class="muted">deadline ${esc(fmtTime(f.sleep.deadline_utc))}</span>${f.sleep.explain ? ` <span class="muted">— ${esc(f.sleep.explain)}</span>` : ""}</li>`
      : "";
    const recRows = recurring.length
      ? recurring.map((t) => `<li><strong>${esc(t.name)}</strong> <span class="muted">recurring, no fixed next run · ${esc(t.state || "")}</span></li>`).join("")
      : '<li class="muted">None.</li>';
    body = `<div class="card"><h2>Upcoming</h2><ul class="plain">${sleepRow}${upRows || '<li class="muted">Nothing scheduled.</li>'}</ul></div>
      <div class="card"><h2>Recurring</h2><ul class="plain">${recRows}</ul></div>`;
  } catch (err) {
    body = `<div class="card"><h2>Schedule</h2><p class="muted">Schedule unavailable: ${esc(err.message)}</p></div>`;
  }
  view.innerHTML = `<h1>Schedule</h1><p class="muted">Read-only. Live from the fleet probe: scheduled tasks and the sleep guard.</p>${body}`;
}

async function renderFleet() {
  let body = "";
  try {
    const payload = await api("/api/fleet");
    const f = payload.fleet;
    const taskRows = f.tasks.map((t) =>
      `<li><span class="pill st-${t.present ? esc((t.state || "unknown").replace(/\s+/g, "-")) : "missing"}">${t.present ? esc(t.state || "unknown") : "missing"}</span> <strong>${esc(t.name)}</strong>` +
      (t.present
        ? ` <span class="muted">last ${esc(fmtTime(t.last_run))} · next ${esc(fmtTime(t.next_run))} · result ${esc(t.last_result ?? "?")}</span>` +
      (t.explain ? ` <span class="muted">— ${esc(t.explain)}</span>` : "")
        : ` <span class="muted">${esc(t.detail || "")}</span>`) + `</li>`).join("");
    const runRows = f.runs.length
      ? f.runs.map((r) => `<li><a href="#/runs/${esc(r.id)}">${esc(r.title || r.id)}</a> <span class="pill">${esc(r.status || "")}</span> <span class="muted">${esc(fmtTime(r.updated))}</span></li>`).join("")
      : '<li class="muted">No active runs.</li>';
    const sleep = f.sleep.active
      ? `Armed — due ${esc(fmtTime(f.sleep.due_utc))}, deadline ${esc(fmtTime(f.sleep.deadline_utc))} (PID ${esc(f.sleep.pid ?? "?")})${f.sleep.explain ? ` — ${esc(f.sleep.explain)}` : ""}`
      : `Idle (${esc(f.sleep.status || "no receipt")})`;
    body = `<div class="card"><h2>Servers</h2><ul class="plain">
      <li><span class="pill st-ready">up</span> <strong>dashboard</strong> <span class="muted">${esc(f.dashboard.explain || "this server")}</span></li>
      <li><span class="pill st-${f.ollama.up ? "ready" : "missing"}">${f.ollama.up ? "up" : "down"}</span> <strong>ollama</strong> <span class="muted">${f.ollama.up ? esc(f.ollama.models) + " model(s)" : esc(f.ollama.detail || "")}${f.ollama.explain ? ` — ${esc(f.ollama.explain)}` : ""}</span></li></ul></div>
      <div class="card"><h2>Watchdog tasks</h2><ul class="plain">${taskRows}</ul></div>
      <div class="card"><h2>Sleep guard</h2><p>${sleep}</p></div>
      <div class="card"><h2>Active runs</h2><ul class="plain">${runRows}</ul></div>`;
  } catch (err) {
    body = `<div class="card"><h2>Fleet</h2><p class="muted">Fleet unavailable: ${esc(err.message)}</p></div>`;
  }
  view.innerHTML = `<h1>Fleet</h1><p class="muted">Probed live on open. Watchdogs, servers, sleep guard, active runs.</p>${body}`;
}

function renderRestrictions() {
  // v1: static definitions only. No enforcement source of truth exists yet,
  // so every dimension is honestly "not yet evaluated" with its feeder named.
  view.innerHTML = `<h1>Agent restrictions</h1>
    <p class="muted">Read-only overview of what agents may and may not do. No live
    enforcement data feeds this page yet — each dimension shows its definition, an
    honest <strong>not yet evaluated</strong> status, and what would feed it.</p>
    <div class="card"><h2>Dimensions</h2><ul class="plain">
      <li><strong>Outbound network</strong> — which hosts an agent may call.
        Status: not yet evaluated. Would be fed by: an egress allowlist in
        agent-executor policy (not yet defined).</li>
      <li><strong>Filesystem writes</strong> — which roots an agent may create,
        edit, or delete under. Status: not yet evaluated. Would be fed by: a
        writable-roots policy in agent-executor (not yet defined).</li>
      <li><strong>Secret handling</strong> — credentials stay in .env / user env,
        never in prompts, logs, or the owner inbox. Status: not yet evaluated.
        Would be fed by: a secret-scan of run transcripts (not yet built).</li>
      <li><strong>Subprocess execution</strong> — shell commands run only through
        approval-gated run requests. Status: not yet evaluated. Would be fed by:
        run-request receipts (exist) plus an executor-side gate audit (not yet built).</li>
      <li><strong>Delegation scope</strong> — subagents inherit the
        supervisor's authority, never more (ADR-074). Status: not yet
        evaluated. Would be fed by: delegation-scope records (exist in chat
        channel tools) plus a scope audit (not yet built).</li>
      <li><strong>Human approval gates</strong> — writes, execution, and
        external sends wait for inbox approval. Status: not yet evaluated.
        Would be fed by: inbox approval records (exist) wired per dimension
        (not yet wired).</li>
    </ul></div>
    <div class="card"><h2>Related reading</h2><ul class="plain">
      <li>docs/decisions/ADR-074 — delegation inherits supervisor authority</li>
      <li>docs/capabilities.md — what each route can do today</li>
    </ul></div>`;
}
function providerStatusPill(p) {
  if (p.reachable === null || p.reachable === undefined || p.checked_at === null) {
    return '<span class="pill">not checked yet</span>';
  }
  if (p.account_required && !p.key_configured) {
    return '<span class="pill st-missing">key missing</span>';
  }
  if (!p.reachable) return '<span class="pill st-down">unreachable</span>';
  if (p.auth_ok === false) return '<span class="pill st-down">key rejected</span>';
  const n = p.model_count === null || p.model_count === undefined ? "?" : p.model_count;
  return `<span class="pill st-ok">ok &#183; ${esc(n)} models</span>`;
}

function providerCheckedAt(p) {
  if (!p.checked_at) return "never checked";
  const d = new Date(p.checked_at);
  if (Number.isNaN(d.getTime())) return p.checked_at;
  return d.toLocaleString();
}

function providerCardHtml(p) {
  const samples = (p.sample_ids || []).map((s) => `<li>${esc(s)}</li>`).join("");
  const sampleBlock = samples
    ? `<p class="muted">Sample models:</p><ul class="plain">${samples}</ul>` : "";
  const err = p.error ? `<p class="muted">Last error: ${esc(p.error)}</p>` : "";
  const latency = p.latency_ms === null || p.latency_ms === undefined
    ? "" : `<p class="muted">Latency: ${esc(p.latency_ms)} ms</p>`;
  const site = p.site_url
    ? `<p><a href="${esc(p.site_url)}" target="_blank" rel="noopener">` +
      `Log in / register at ${esc(p.display)}</a></p>` : "";
  const keyLine = !p.account_required
    ? '<p class="muted">No account or key needed (local).</p>'
    : (p.key_configured
      ? '<p class="muted">API key is configured.</p>'
      : '<p class="muted">No API key configured - add one to use this provider.</p>');
  return `<div class="card"><h2>${esc(p.display)}</h2>
    <p>${providerStatusPill(p)}</p>
    <p class="muted">${esc(p.blurb || "")}</p>
    ${keyLine}${site}${latency}${err}${sampleBlock}
    <p class="muted">Checked: ${esc(providerCheckedAt(p))}</p></div>`;
}

async function renderProviders() {
  const data = await api("/api/providers");
  const cards = (data.providers || []).map(providerCardHtml).join("");
  const note = data.cached
    ? "Showing the last saved check."
    : "Fresh check.";
  view.innerHTML = `
    <h1>Providers</h1>
    <p class="muted">Connection status only - checks are free model-list probes, never inference. ${esc(note)}</p>
    <p><button id="providers-refresh" title="Probe all providers now (free list checks)">Refresh now</button></p>
    <div class="columns" id="providers-list">${cards}</div>`;
  document.getElementById("providers-refresh").addEventListener("click", async () => {
    try {
      await api("/api/providers/refresh", {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"});
      toast("Provider status refreshed", true);
      await renderProviders();
    } catch (err) {
      toast(err.message, false);
    }
  });
}

async function render() {
  stopRunsPoll();
  stopRunDetailPoll();
  document.querySelectorAll("nav a").forEach((a) => a.classList.remove("active"));
  const raw = (location.hash || "#/home").slice(2);
  const [path, query] = raw.split("?");
  // Document ids are multi-segment (root/relpath); single-segment ids behave as before.
  const [name, ...rest] = path.split("/");
  const id = rest.length ? decodeURIComponent(rest.join("/")) : undefined;
  const active = document.querySelector(`nav a[data-view="${name}"]`);
  if (active) active.classList.add("active");
  try {
    if (name === "home") await renderHome();
    else if (name === "chat" && id) {
      const q = new URLSearchParams(query || "").get("q");
      if (q) history.replaceState(null, "", "#/chat/" + id);
      await renderChatThread(id, q);
    }
    else if (name === "chat") await renderChatList();
    else if (name === "plans") await renderPlans(id);
    else if (name === "runs") await renderRuns(id);
    else if (name === "inbox") await renderInbox(id);
    else if (name === "ideas") await renderIdeas(id);
    else if (name === "documents") await renderDocuments(id);
    else if (name === "intake") await renderIntake();
    else if (name === "schedule") await renderSchedule();
    else if (name === "fleet") await renderFleet();
    else if (name === "providers") await renderProviders();
    else if (name === "restrictions") renderRestrictions();
    else if (name === "create" && id) renderCreate(id);
    else view.innerHTML = "<h1>Not found</h1>";
  } catch (err) {
    view.innerHTML = `<h1>Something failed</h1><p>${esc(err.message)}</p>`;
    toast(err.message, false);
  }
  refreshBadge();
}

document.getElementById("create-btn").addEventListener("click", () => {
  document.getElementById("create-menu").hidden =
    !document.getElementById("create-menu").hidden;
});
document.querySelectorAll("[data-create]").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.getElementById("create-menu").hidden = true;
    location.hash = "#/create/" + btn.dataset.create;
  });
});

window.addEventListener("hashchange", render);
render();
startInboxPoll();