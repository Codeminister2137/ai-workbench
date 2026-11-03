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
  STT: "Speech-to-text dictation (Web Speech v1 live, Meta server planned)",
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

async function renderHome() {
  const status = await api("/api/status");
  const plan = status.current_plan
    ? `<a href="#/plans/${esc(status.current_plan.id)}">${esc(status.current_plan.title || status.current_plan.id)}</a>`
    : '<span class="muted">No plan yet</span>';
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
    <p class="muted">Supervisor answers; turns cannot run tools yet. Full transcripts stay local.</p>
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
    <p><button id="delete-btn" title="Delete this chat and its transcript">Delete chat</button></p>
    <div id="thread">${msgs || '<p class="muted">No messages yet.</p>'}</div>
    <form class="inline" id="chat-form"><input type="text" name="text" placeholder="Message..." title="Message the supervisor" required>
    <button type="submit" title="Send message">Send</button></form>`;
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
      render();
    } catch (err) {
      toast(err.message, false);
    } finally {
      btn.disabled = false;
      btn.textContent = "Send";
    }
  }
  form.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const text = ev.target.text.value.trim();
    if (text) send(text);
  });
  if (initial) send(initial);
}

async function renderPlans(id) {
  if (id) {
    const payload = await api("/api/plans/" + encodeURIComponent(id));
    const plan = payload.item;
    view.innerHTML = `<h1>Plan</h1><p><a href="#/plans">All plans</a></p>
      <div class="card"><h2>${gtext(plan.title || plan.id)}</h2>
      <p class="muted">${esc(plan.status || "")}${plan.updated_at_utc ? " · updated " + esc(plan.updated_at_utc) : ""}</p>
      ${plan.source ? `<p class="muted">Source: ${esc(plan.source)}</p>` : ""}
      <pre>${gtext(plan.body || "(empty plan)")}</pre></div>`;
    return;
  }
  const payload = await api("/api/plans");
  const items = payload.items.length
    ? payload.items.map((p) =>
        `<li><a href="#/plans/${esc(p.id)}">${gtext(p.title || p.id)}</a>
         <span class="pill st-${esc((p.status || "none").replace(/\s+/g, "-"))}">${esc(p.status || "")}</span></li>`).join("")
    : '<li class="muted">No plans on file. Plans are created by Workbench flows.</li>';
  view.innerHTML = `<h1>Plans</h1><ul class="plain">${items}</ul><p class="muted">${payload.total} total.</p>`;
}

async function renderRuns(id) {
  if (id) {
    const payload = await api("/api/runs/" + encodeURIComponent(id));
    const run = payload.item;
    const meta = [run.status, run.branch, run.commit].filter(Boolean).map(esc).join(" · ");
    const report = run.report
      ? `<h3>Report</h3><pre>${gtext(run.report)}</pre>`
      : run.report_request_id
        ? `<p class="muted">Report requested — see the inbox task.</p>`
        : `<p><button id="report-btn" title="Ask for a completion report for this run">Generate report</button></p>`;
    view.innerHTML = `<h1>Run</h1><p><a href="#/runs">All runs</a></p>
      <div class="card"><h2>${gtext(run.title || run.id)}</h2>
      <p class="muted">${meta}</p>
      ${run.validation ? `<p><strong>Validation:</strong> ${esc(run.validation)}</p>` : ""}
      ${run.body ? `<pre>${gtext(run.body)}</pre>` : ""}
      ${report}</div>`;
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
  const payload = await api("/api/runs");
  const items = payload.items.length
    ? payload.items.map((r) =>
        `<li><a href="#/runs/${esc(r.id)}">${gtext(r.title || r.id)}</a>
         <span class="pill st-${esc((r.status || "none").replace(/\s+/g, "-"))}">${esc(r.status || "")}</span></li>`).join("")
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
  view.innerHTML = `<h1>Runs</h1><ul class="plain">${items}</ul>${evidence}`;
}

async function renderInbox(id) {
  if (id) {
    const payload = await api("/api/inbox/" + encodeURIComponent(id));
    const item = payload.item;
    const options = (item.options || []).map((opt, i) =>
      `<label><input type="radio" name="opt" value="${i}"> ${esc(opt)}</label><br>`).join("");
    const refs = (item.context_refs || []).map((r) => `<li>${esc(r)}</li>`).join("");
    view.innerHTML = `<h1>Inbox task</h1><p><a href="#/inbox">All tasks</a></p>
      <div class="card"><h2>${gtext(item.title)}</h2>
      <p class="muted">${esc(item.type)} · ${esc(item.status)} · from ${esc(item.created_by || "")}</p>
      <p>${gtext(item.body || "")}</p>
      ${refs ? `<ul class="plain">${refs}</ul>` : ""}
      ${(item.options || []).length ? `<p><strong>Options offered:</strong></p><ol>${item.options.map((o) => `<li>${esc(o)}</li>`).join("")}</ol>` : ""}
      ${item.answer ? `<p><strong>Answer:</strong> ${esc(item.answer)}</p>` : ""}
      ${item.note ? `<p><strong>Note:</strong> ${esc(item.note)}</p>` : ""}
      ${item.status === "closed" ? '<p class="muted">Closed; answers are immutable.</p>' : `
      <form id="answer-form">
        ${options}
        ${options ? '<p class="muted">Pick one, add a note, or both — the note expands your choice.</p>' : ""}
        <div><input type="text" name="answer" placeholder="${options ? "Add a note (optional)..." : "Your answer..."}" title="${options ? "Optional note expanding your choice" : "Type your answer"}"></div>
        <p><button type="submit" title="Record your choice and note">Submit answer</button></p>
      </form>
      <p><button id="close-btn" title="Close this task (answers become immutable)">Close task</button></p>`}</div>`;
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
    const closeBtn = document.getElementById("close-btn");
    if (closeBtn) closeBtn.addEventListener("click", async () => {
      try {
        await api("/api/inbox/" + encodeURIComponent(id) + "/close", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: "{}",
        });
        toast("Task closed", true);
        render();
      } catch (err) {
        toast(err.message, false);
      }
    });
    return;
  }
  const tab = new URLSearchParams((location.hash.split("?")[1] || "")).get("status") || "active";
  const payload = await api("/api/inbox");
  const shown = payload.items.filter((t) => tab === "archive" ? t.status === "closed" : t.status !== "closed");
  const items = shown.length
    ? shown.map((t) =>
        `<li><a href="#/inbox/${esc(t.id)}">${gtext(t.title)}</a>
         <span class="pill st-${esc((t.status || "none").replace(/\s+/g, "-"))}">${esc(t.type)} · ${esc(t.status)}</span></li>`).join("")
    : '<li class="muted">Nothing here. The supervisor assigns decisions to the inbox.</li>';
  view.innerHTML = `<h1>Inbox</h1>
    <p><a href="#/inbox">Active</a> · <a href="#/inbox?status=archive">Archive</a></p>
    <ul class="plain">${items}</ul>`;
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
      <p>${gtext(item.body || "")}</p>
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
    <ul class="plain">${items}</ul>`;
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
      ${fieldRow("Type *", `<select id="f-type" title="Item type (required)"><option value="clarification">clarification</option><option value="decision">decision</option></select>`, "required")}`},
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
    const title = document.getElementById("f-title").value.trim();
    if (!title) { toast("Title is required", false); return; }
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
      toast(err.message, false);
    }
  });
}

function renderSchedule() {
  view.innerHTML = `<h1>Schedule</h1>
    <p class="muted">Read-only until the P5 scheduler exists. Queued work today lives in plans and runs.</p>`;
}

async function render() {
  document.querySelectorAll("nav a").forEach((a) => a.classList.remove("active"));
  const raw = (location.hash || "#/home").slice(2);
  const [path, query] = raw.split("?");
  const [name, id] = path.split("/");
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
    else if (name === "schedule") renderSchedule();
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