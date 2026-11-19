const grid = document.querySelector("#councilGrid");
const promptForm = document.querySelector("#promptForm");
const promptInput = document.querySelector("#promptInput");
const conversationInput = document.querySelector("#conversationInput");
const roundsInput = document.querySelector("#roundsInput");
const askButton = document.querySelector("#askButton");
const connectionStatus = document.querySelector("#connectionStatus");

const panels = new Map();

function setGlobalStatus(text, state = "") {
  connectionStatus.textContent = text;
  connectionStatus.className = `status-pill ${state}`.trim();
}

function createPanel(member) {
  const panel = document.createElement("article");
  panel.className = "member-window";
  panel.dataset.member = member.name;
  panel.innerHTML = `
    <header class="member-header">
      <div>
        <div class="member-name"></div>
        <div class="member-model"></div>
      </div>
      <div class="member-state">Waiting</div>
    </header>
    <pre class="member-answer empty">No answer yet.</pre>
  `;
  panel.querySelector(".member-name").textContent = member.name;
  panel.querySelector(".member-model").textContent = member.model;
  grid.appendChild(panel);
  panels.set(member.name, panel);
}

function setPanelState(memberName, state, label) {
  const panel = panels.get(memberName);
  if (!panel) return;
  panel.classList.remove("running", "done", "error");
  if (state) panel.classList.add(state);
  panel.querySelector(".member-state").textContent = label;
}

function setPanelText(memberName, text) {
  const panel = panels.get(memberName);
  if (!panel) return;
  const answer = panel.querySelector(".member-answer");
  answer.classList.toggle("empty", !text);
  answer.textContent = text || "No answer yet.";
  answer.scrollTop = answer.scrollHeight;
}

function appendPanelText(memberName, text) {
  const panel = panels.get(memberName);
  if (!panel) return;
  const answer = panel.querySelector(".member-answer");
  if (answer.classList.contains("empty")) {
    answer.textContent = "";
    answer.classList.remove("empty");
  }
  answer.textContent += text;
  answer.scrollTop = answer.scrollHeight;
}

async function loadConfig() {
  const response = await fetch("/api/config");
  if (!response.ok) throw new Error(await response.text());
  const config = await response.json();
  conversationInput.value = config.default_conversation;
  grid.textContent = "";
  panels.clear();
  config.members.forEach(createPanel);
}

function resetPanels() {
  panels.forEach((panel, memberName) => {
    panel.classList.remove("running", "done", "error");
    panel.querySelector(".member-state").textContent = "Waiting";
    setPanelText(memberName, "");
    panel.querySelectorAll(".member-reaction").forEach((box) => box.remove());
  });
  document.querySelectorAll("#synthesisPanel").forEach((pinned) => pinned.remove());
}

function ensureReactionBox(memberName) {
  const panel = panels.get(memberName);
  if (!panel) return null;
  let box = panel.querySelector(".member-reaction");
  if (!box) {
    box = document.createElement("details");
    box.className = "member-reaction";
    const summary = document.createElement("summary");
    summary.textContent = "Reaction (R2)";
    const body = document.createElement("pre");
    body.className = "reaction-answer empty";
    body.textContent = "No reaction yet.";
    box.appendChild(summary);
    box.appendChild(body);
    panel.appendChild(box);
  }
  return box.querySelector(".reaction-answer");
}

function appendReactionText(memberName, text) {
  const body = ensureReactionBox(memberName);
  if (!body) return;
  if (body.classList.contains("empty")) {
    body.textContent = "";
    body.classList.remove("empty");
  }
  body.textContent += text;
  body.scrollTop = body.scrollHeight;
}

function pinSynthesis(text, partial) {
  let pinned = document.querySelector("#synthesisPanel");
  if (!pinned) {
    pinned = document.createElement("article");
    pinned.id = "synthesisPanel";
    pinned.className = "member-window synthesis";
    pinned.innerHTML = `
      <header class="member-header">
        <div><div class="member-name">Synthesis</div></div>
        <div class="member-state">Chair</div>
      </header>
      <pre class="member-answer empty">No synthesis yet.</pre>
    `;
    grid.prepend(pinned);
  }
  const body = pinned.querySelector(".member-answer");
  body.classList.toggle("empty", !text);
  body.textContent = text || "No synthesis yet.";
  body.scrollTop = body.scrollHeight;
  if (partial) {
    pinned.querySelector(".member-state").textContent = "Partial";
  }
}

function handleEvent(event) {
  if (event.type === "member_started") {
    setPanelText(event.member, "");
    setPanelState(event.member, "running", "Generating");
  }

  if (event.type === "member_delta") {
    appendPanelText(event.member, event.delta);
  }

  if (event.type === "member_finished") {
    setPanelState(event.member, "done", "Finished");
    if (event.answer) setPanelText(event.member, event.answer);
  }

  if (event.type === "member_error") {
    setPanelState(event.member, "error", "Error");
    setPanelText(event.member, event.error);
  }

  if (event.type === "reaction_delta") {
    setPanelState(event.member, "running", "Reacting");
    appendReactionText(event.member, event.delta);
  }

  if (event.type === "reaction_finished") {
    setPanelState(event.member, "done", "Finished");
  }

  if (event.type === "synthesis_delta") {
    pinSynthesis("", false);
    const pinned = document.querySelector("#synthesisPanel .member-answer");
    if (pinned) {
      if (pinned.classList.contains("empty")) {
        pinned.textContent = "";
        pinned.classList.remove("empty");
      }
      pinned.textContent += event.delta;
      pinned.scrollTop = pinned.scrollHeight;
    }
  }

  if (event.type === "synthesis_finished") {
    pinSynthesis(event.answer, event.partial);
  }

  if (event.type === "council_finished") {
    setGlobalStatus("Done", "done");
    askButton.disabled = false;
  }
}

async function readEventStream(response) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() || "";

    for (const frame of frames) {
      const line = frame.split("\n").find((item) => item.startsWith("data: "));
      if (!line) continue;
      handleEvent(JSON.parse(line.slice(6)));
    }
  }
}

promptForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const prompt = promptInput.value.trim();
  if (!prompt) return;

  askButton.disabled = true;
  resetPanels();
  setGlobalStatus("Running", "running");

  try {
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt,
        conversation: conversationInput.value.trim(),
        rounds: parseInt(roundsInput.value, 10) || 1,
      }),
    });

    if (!response.ok) {
      throw new Error(await response.text());
    }

    await readEventStream(response);
  } catch (error) {
    setGlobalStatus("Error", "error");
    askButton.disabled = false;
    console.error(error);
  }
});

loadConfig().catch((error) => {
  setGlobalStatus("Error", "error");
  grid.textContent = error.message;
});
