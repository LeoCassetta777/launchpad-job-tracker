/*
 * agentchat.js: the "Ask Launchpad" chat on the Pipeline page. The 💬 button at the
 * bottom left opens it as a pop-up (full screen on a phone); ✕ or Esc closes it.
 * Sends your message to /api/agent/chat; the server runs the agent (agent.py)
 * and sends back its reply plus a list of what it changed, each with a link.
 * Replies are drawn as plain text (with **bold** and "- " lists), never as HTML.
 */

const agentLog = document.getElementById("agent-log");
const agentInput = document.getElementById("agent-input");
const agentSend = document.getElementById("agent-send");
const agentMic = document.getElementById("agent-mic");
const agentFab = document.getElementById("agent-fab");
const agentPanel = document.getElementById("agent-panel");
let agentChatId = null;
let agentBusy = false;
let agentLoaded = false;

function openAgent() {
  agentPanel.hidden = false;
  agentFab.setAttribute("aria-expanded", "true");
  if (!agentLoaded) loadAgent();
  agentLog.scrollTop = agentLog.scrollHeight;
  agentInput.focus();
}

function closeAgent() {
  agentPanel.hidden = true;
  agentFab.setAttribute("aria-expanded", "false");
  agentFab.focus();
}

agentFab.addEventListener("click", () => (agentPanel.hidden ? openAgent() : closeAgent()));
document.getElementById("agent-close").addEventListener("click", closeAgent);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !agentPanel.hidden && !document.querySelector("dialog[open]")) closeAgent();
});

/** "Some **bold** text" -> [text, <strong>, text] (safe: only text nodes). */
function inlineBold(line) {
  return line.split(/\*\*(.+?)\*\*/g).map((part, i) => (i % 2 ? h("strong", {}, part) : part));
}

/** A reply as paragraphs and bullet lists. */
function replyBody(text) {
  const out = [];
  let list = null;
  for (const raw of (text || "").split("\n")) {
    const line = raw.trimEnd();
    const bullet = line.match(/^\s*(?:[-*•]|\d+\.)\s+(.*)$/);
    if (bullet) {
      if (!list) { list = h("ul"); out.push(list); }
      list.append(h("li", {}, inlineBold(bullet[1])));
    } else if (line.trim()) {
      list = null;
      out.push(h("p", {}, inlineBold(line)));
    } else {
      list = null;
    }
  }
  return out;
}

function bubble(entry) {
  if (entry.role === "user") return h("div", { class: "agent-msg agent-user" }, h("p", {}, entry.text));
  return h("div", { class: "agent-msg agent-bot" },
    entry.text ? replyBody(entry.text) : null,
    entry.actions && entry.actions.length ? h("ul", { class: "agent-actions" },
      entry.actions.map((a) => h("li", {}, a.link ? h("a", { href: a.link }, a.text) : a.text))) : null,
    entry.note ? h("p", { class: "agent-note" }, `⚠️ ${entry.note}`) : null,
    entry.cost ? h("span", { class: "agent-cost muted small" }, `$${entry.cost.toFixed(3)}`) : null);
}

function showChat(data) {
  agentChatId = data.chat_id;
  fill(agentLog, data.display.length ? data.display.map(bubble) : h("div", { class: "agent-empty muted" },
    h("p", {}, "Tell me what to do in plain English. For example:"),
    h("ul", {},
      h("li", {}, "“I met Sam Lee from Paychex at the career fair, she's a recruiter, follow up Friday”"),
      h("li", {}, "“Move the Acme card to Sent and remind me to follow up in a week”"),
      h("li", {}, "“Which Discover postings fit me best? Add the top two”"),
      h("li", {}, "“Plan my Thursday around my Canvas assignments”"))));
  agentLog.scrollTop = agentLog.scrollHeight;
}

async function sendToAgent() {
  const text = agentInput.value.trim();
  if (!text || agentBusy) return;
  agentBusy = true;
  agentSend.disabled = true;
  agentLog.querySelector(".agent-empty")?.remove();
  agentLog.append(bubble({ role: "user", text }));
  const typing = h("div", { class: "agent-msg agent-bot agent-typing" }, h("p", {}, "Working on it… (multi-step requests can take up to a minute)"));
  agentLog.append(typing);
  agentLog.scrollTop = agentLog.scrollHeight;
  agentInput.value = "";
  try {
    const res = await apiAI("/api/agent/chat", { chat_id: agentChatId, message: text },
                            "A message usually costs 1 to 5 cents.");
    agentChatId = res.chat_id;
    typing.replaceWith(bubble(res.entry));
    if (res.changed) announceChange();       // redraw the board and Today strip
  } catch (err) {
    typing.remove();
    agentInput.value = text;                 // give the message back so it isn't lost
  } finally {
    agentBusy = false;
    agentSend.disabled = false;
    agentLog.scrollTop = agentLog.scrollHeight;
  }
}

agentSend.addEventListener("click", sendToAgent);
agentInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {   // Enter sends; Shift+Enter makes a new line
    e.preventDefault();
    sendToAgent();
  }
});

document.getElementById("agent-new").addEventListener("click", async () => {
  if (agentBusy) return;
  showChat(await api("POST", "/api/agent/new", {}));
  agentInput.focus();
});

// Talk instead of typing (same dictation as the quick-add box).
if (speechSupported()) {
  agentMic.hidden = false;
  let session = null;
  agentMic.addEventListener("click", () => {
    if (session) { session.stop(); return; }
    agentMic.classList.add("selected");
    agentMic.setAttribute("aria-pressed", "true");
    session = startDictation({
      startText: agentInput.value,
      onText: (t) => { agentInput.value = t; },
      onStop: () => {
        session = null;
        agentMic.classList.remove("selected");
        agentMic.setAttribute("aria-pressed", "false");
      },
    });
  });
}

/** Load the latest chat the first time the panel opens. */
async function loadAgent() {
  agentLoaded = true;
  const data = await api("GET", "/api/agent");
  if (!data.ai_enabled) {
    fill(agentLog, h("p", { class: "muted" }, "🔌 AI is off: add your Anthropic API key to .env."));
    agentSend.disabled = true;
    return;
  }
  showChat(data);
}
