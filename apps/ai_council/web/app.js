const grid = document.querySelector("#councilGrid");
const promptForm = document.querySelector("#promptForm");
const promptInput = document.querySelector("#promptInput");
const conversationInput = document.querySelector("#conversationInput");
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
  });
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
