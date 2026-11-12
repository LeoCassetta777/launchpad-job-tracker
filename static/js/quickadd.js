/*
 * quickadd.js: the brain-dump box at the top of every page (Ctrl+K), plus the review pop-up.
 *
 * 1. You type a brain dump, or switch to "Paste a posting" and paste one.
 * 2. The server asks the AI to sort it (/api/ai/parse). Nothing is saved yet.
 * 3. Each thing it found becomes an editable preview card. Fields the AI assumed
 *    are flagged "🤔 guessed". Accept or discard each card, or Accept all.
 * 4. Accepting saves through the normal API, the same as the + Add buttons.
 *    If a card links to another new card (e.g. a task for a new opportunity),
 *    that one is saved first automatically.
 */

const qaForm = document.getElementById("qa-form");
const qaText = document.getElementById("qa-text");
const qaUrl = document.getElementById("qa-url");
const qaButton = document.getElementById("qa-submit");
const qaDialog = document.getElementById("qa-dialog");
let qaMode = "dump";
let qaPageTitle = null;   // set when a posting arrives from the clipper

const KIND_INFO = {
  opportunity: { icon: "💼", label: "New opportunity" },
  task: { icon: "✅", label: "New task" },
  contact: { icon: "👤", label: "New contact" },
  interaction: { icon: "📝", label: "Log interaction" },
  update: { icon: "✏️", label: "Update" },
};

// Fields shown up front on each preview card. Others sit under "More fields".
const KEY_FIELDS = {
  opportunity: ["company", "title", "type", "stage", "urgency", "importance", "deadline", "deadline_time",
                "next_action", "next_action_date", "link", "location", "pay", "summary", "requirements"],
  task: ["title", "planned_date", "due_date", "start_time", "duration_min", "est_min", "urgency", "importance"],
  contact: ["name", "company", "role", "email", "follow_up_date", "how_met"],
};
// Fields never shown on preview cards (links are shown separately; status starts as To do).
const HIDDEN_FIELDS = ["opportunity_id", "contact_id", "status", "actual_min", "completeness"];

/* ------------------------------------------------------------ the input box */

function setMode(mode) {
  qaMode = mode;
  document.querySelectorAll("[data-qa-mode]").forEach((b) => {
    b.classList.toggle("selected", b.dataset.qaMode === mode);
    b.setAttribute("aria-pressed", String(b.dataset.qaMode === mode));
  });
  qaUrl.hidden = mode !== "posting";
  qaText.placeholder = mode === "posting"
    ? "Paste the whole job posting here. Menus and footers are fine; the AI picks out the posting."
    : "Brain dump anything: “apply to the Lanternfly fellowship by Nov 15, email Sam next Tuesday, finance homework Thursday ~2 hrs”";
  qaButton.textContent = mode === "posting" ? "✨ Extract posting" : "✨ Sort it out";
}

function growTextarea() {
  qaText.style.height = "auto";
  const borders = qaText.offsetHeight - qaText.clientHeight;
  qaText.style.height = Math.min(qaText.scrollHeight + borders, window.innerHeight * 0.4) + "px";
}

document.querySelectorAll("[data-qa-mode]").forEach((b) => b.addEventListener("click", () => { setMode(b.dataset.qaMode); qaText.focus(); }));
qaText.addEventListener("input", growTextarea);

// Ctrl+K (Cmd+K on a Mac) jumps to the box from anywhere.
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
    e.preventDefault();
    window.scrollTo({ top: 0, behavior: "smooth" });
    qaText.focus();
  }
});
// Ctrl+Enter inside the box submits it.
qaText.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") qaForm.requestSubmit();
});

/** Used by the /clip page: put a clipped posting in the box. */
function prefillPosting({ url, title, text }) {
  setMode("posting");
  qaText.value = text || "";
  qaUrl.value = url || "";
  qaPageTitle = title || null;
  growTextarea();
  qaButton.focus();
}

qaForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = qaText.value.trim();
  if (!text) { toast("Type or paste something first", "error"); qaText.focus(); return; }
  qaButton.disabled = true;
  const label = qaButton.textContent;
  qaButton.textContent = "🌀 Sorting…";
  const body = {
    text, mode: qaMode, url: qaMode === "posting" ? qaUrl.value : undefined,
    title: qaMode === "posting" ? qaPageTitle : undefined,
  };
  try {
    // apiAI asks "run anyway?" if the monthly spending cap is reached (see lp.js).
    openReview(await apiAI("/api/ai/parse", body, "(A brain dump costs about a tenth of a cent.)"));
  } catch (err) {
    /* already shown to you */
  } finally {
    qaButton.disabled = false;
    qaButton.textContent = label;
  }
});

/* ------------------------------------------------------------ the review pop-up */

let review = null;   // { items, notes }

function openReview(result) {
  review = { items: result.items.map((it) => ({ ...it, status: "pending", savedId: null })), notes: result.notes,
             usage: result.usage };
  drawReview();
  qaDialog.showModal();
}

function pending() {
  return review.items.filter((i) => i.status === "pending");
}

/** Copy edits from the cards on screen back into the items, so redrawing doesn't lose them. */
function syncEdits() {
  for (const item of pending()) {
    if (!item.form) continue;
    if (item.kind === "update") {
      for (const c of item.changes) {
        const el = item.form.elements[c.field];
        if (el && c.field !== "notes") c.after = el.value;
      }
    } else {
      item.data = readPreview(item);
    }
  }
}

function drawReview() {
  syncEdits();
  const items = review.items;
  fill(qaDialog, 
    h("div", { class: "qa-head" },
      h("div", {},
        h("h2", {}, "🔍 Review before saving"),
        h("p", { class: "muted" }, items.length
          ? "Nothing is saved until you accept it. Edit anything first. 🤔 marks a guess; check those."
          : "The AI didn't find anything to add.")),
      h("button", { class: "btn btn-small btn-ghost", type: "button", "aria-label": "Close", onclick: closeReview }, "✕")),
    review.notes.length > 0 && h("div", { class: "qa-notes" },
      h("strong", {}, "Couldn't place:"),
      h("ul", {}, review.notes.map((n) => h("li", {}, n)))),
    h("div", { class: "qa-list" }, items.map(previewCard)),
    h("div", { class: "qa-foot" },
      h("span", { class: "muted" }, `${items.filter((i) => i.status === "accepted").length} saved · ${pending().length} waiting`,
        review.usage && h("span", { class: "qa-cost", title: "Estimated from Anthropic's published prices" },
          ` · this cost $${review.usage.cost.toFixed(4)} · $${review.usage.month_spent.toFixed(2)} of $${review.usage.month_cap.toFixed(2)} this month`)),
      h("div", { class: "inline-row" },
        h("button", { class: "btn", type: "button", onclick: closeReview }, pending().length ? "Close (discard rest)" : "Done"),
        pending().length > 0 && h("button", { class: "btn btn-primary", type: "button", onclick: acceptAll },
          `✓ Accept all (${pending().length})`))));
}

function closeReview() {
  if (pending().length && !confirm(`Discard ${pending().length} unsaved card(s)?`)) return;
  qaDialog.close();
  if (review.items.some((i) => i.status === "accepted")) {
    qaText.value = "";
    qaUrl.value = "";
    qaPageTitle = null;
    growTextarea();
  }
}

/** Short title for a card header. */
function itemTitle(item) {
  const d = item.data;
  if (item.kind === "opportunity") return d.title ? `${d.company} · ${d.title}` : d.company;
  if (item.kind === "task") return d.title;
  if (item.kind === "contact") return d.name;
  if (item.kind === "interaction") return `${choice("interaction_kinds", d.kind).label} — ${linkLabel(item.links.contact)}`;
  return item.target.label;
}

/** "Copperline Security · Intern" for an existing record, or "new: Lanternfly" for a new card. */
function linkLabel(link) {
  if (!link) return "";
  if (link.id) return link.label;
  const other = review.items.find((i) => i.ref === link.ref);
  return other ? `new: ${itemTitle(other)}` : link.ref;
}

function previewCard(item) {
  const info = KIND_INFO[item.kind];
  const done = item.status !== "pending";
  const card = h("article", { class: `card preview-card kind-${item.kind} is-${item.status}`, dataset: { pid: item.pid } });

  const header = h("header", { class: "preview-head" },
    h("span", { class: "badge" }, `${info.icon} ${info.label}`),
    h("strong", { class: "preview-title" }, itemTitle(item)),
    item.status === "accepted" && h("span", { class: "sticker urg-chill small" }, "✓ Saved"),
    item.status === "discarded" && h("span", { class: "sticker small" }, "Discarded"));
  card.append(header);
  if (done) {
    if (item.status === "accepted" && item.kind !== "interaction") {
      const kind = item.kind === "update" ? item.target.type : item.kind;
      card.append(h("button", { class: "btn btn-small", type: "button",
        onclick: () => { qaDialog.close(); openDrawer(kind, item.savedId); } }, "Open it →"));
    }
    return card;
  }

  if (item.warnings.length) {
    card.append(h("ul", { class: "preview-warnings" }, item.warnings.map((w) => h("li", {}, `⚠️ ${w}`))));
  }
  if (item.reason) card.append(h("p", { class: "muted small" }, `Why: ${item.reason}`));

  const form = h("form", { class: "preview-form", onsubmit: (e) => e.preventDefault() });
  item.form = form;

  if (item.kind === "update") {
    form.append(h("div", { class: "change-list" }, item.changes.map((c) => changeRow(item, c))));
  } else if (item.kind === "interaction") {
    const fields = [
      { name: "kind", label: "What happened", type: "select", options: "interaction_kinds" },
      { name: "happened_on", label: "When", type: "date" },
      { name: "note", label: "Note", type: "text", wide: true },
    ];
    item.fields = fields;
    form.append(h("div", { class: "form-grid" }, fields.map((f) => buildField(f, item.data[f.name] ?? "", { guessed: item.guessed.includes(f.name) }))));
  } else {
    const fields = FORMS[item.kind].filter((f) => !f.section && !HIDDEN_FIELDS.includes(f.name));
    item.fields = fields;
    const isKey = (f) => KEY_FIELDS[item.kind].includes(f.name) && (item.data[f.name] != null || f.required || item.guessed.includes(f.name) || ["company", "title", "name", "stage", "planned_date"].includes(f.name));
    const make = (f) => buildField(f, item.data[f.name] ?? f.default ?? "", { guessed: item.guessed.includes(f.name) });
    const main = fields.filter((f) => isKey(f) || item.data[f.name] != null);
    const rest = fields.filter((f) => !main.includes(f));
    form.append(h("div", { class: "form-grid" }, main.map(make)));
    if (rest.length) form.append(h("details", { class: "more-fields" }, h("summary", {}, "More fields"), h("div", { class: "form-grid" }, rest.map(make))));
  }
  card.append(form);

  // Links to other records, shown as text.
  const links = [];
  if (item.links.opportunity) links.push(`💼 ${linkLabel(item.links.opportunity)}`);
  if (item.links.contact) links.push(`👤 ${linkLabel(item.links.contact)}`);
  (item.links.contacts || []).forEach((c) => links.push(`👤 ${linkLabel(c)}`));
  if (links.length) card.append(h("p", { class: "preview-links" }, "Linked to: ", links.join("  ·  ")));
  if (item.checklist.length) {
    card.append(h("div", { class: "preview-checklist" }, h("strong", {}, "Checklist"),
      h("ul", {}, item.checklist.map((c) => h("li", {}, `☐ ${c}`)))));
  }
  if (item.data.posting_text) {
    card.append(h("p", { class: "muted small" }, `📄 The original posting (${item.data.posting_text.length.toLocaleString()} characters) will be saved with it.`));
  }

  card.append(h("div", { class: "preview-actions" },
    h("button", { class: "btn btn-ghost btn-small", type: "button", onclick: () => { item.status = "discarded"; drawReview(); } }, "Discard"),
    h("button", { class: "btn btn-primary btn-small", type: "button", onclick: async (e) => {
      e.currentTarget.disabled = true;
      try { await acceptItem(item); } catch (err) { /* toast already shown */ }
      drawReview();
    } }, "✓ Accept")));
  return card;
}

/** One editable row in an "Update" card: field, old value, new value. */
function changeRow(item, change) {
  if (change.field === "notes") {
    return h("div", { class: "change-row" }, h("span", { class: "field-label" }, "Add note"), h("span", {}, change.after));
  }
  const def = FORMS[item.target.type].find((f) => f.name === change.field) || { name: change.field, label: change.label, type: "text" };
  const before = change.before == null || change.before === "" ? "(empty)" : String(change.before);
  return h("div", { class: "change-row" },
    buildField({ ...def, wide: true }, change.after ?? "", { guessed: item.guessed.includes(change.field) }),
    h("span", { class: "muted small" }, `was: ${before}`));
}

/** Read the (possibly edited) values from a preview card's form. */
function readPreview(item) {
  if (item.kind === "update") {
    const data = {};
    for (const c of item.changes) {
      if (c.field === "notes") { data.notes = item.data.notes; continue; }
      const el = item.form.elements[c.field];
      if (el) data[c.field] = el.value === "" ? null : el.value;
    }
    return data;
  }
  // Start from the hidden values (e.g. posting_text), then overlay what's in the form.
  const data = {};
  for (const [k, v] of Object.entries(item.data)) if (!item.fields.some((f) => f.name === k)) data[k] = v;
  return { ...data, ...collectForm(item.form, item.fields, null) };
}

/* ------------------------------------------------------------ saving */

/** The saved id for a link: existing records have one; new cards get saved first. */
async function resolveLink(link) {
  if (!link) return null;
  if (link.id) return link.id;
  const other = review.items.find((i) => i.ref === link.ref);
  if (!other || other.status === "discarded") return null;
  if (other.status === "pending") {
    await acceptItem(other);
    toast(`Also saved ${itemTitle(other)}`);
  }
  return other.savedId;
}

async function acceptItem(item) {
  if (item.status === "accepted") return item.savedId;
  const data = readPreview(item);
  let saved;

  if (item.kind === "contact") {
    saved = await api("POST", "/api/contacts", data);
  } else if (item.kind === "opportunity") {
    saved = await api("POST", "/api/opportunities", data);
    for (const link of item.links.contacts || []) {
      const contactId = await resolveLink(link);
      if (contactId) await api("POST", `/api/opportunities/${saved.id}/contacts`, { contact_id: contactId });
    }
    for (const text of item.checklist) await api("POST", "/api/checklist", { opportunity_id: saved.id, text });
  } else if (item.kind === "task") {
    data.opportunity_id = await resolveLink(item.links.opportunity);
    data.contact_id = await resolveLink(item.links.contact);
    saved = await api("POST", "/api/tasks", data);
    for (const text of item.checklist) await api("POST", "/api/checklist", { task_id: saved.id, text });
  } else if (item.kind === "interaction") {
    const contactId = await resolveLink(item.links.contact);
    if (!contactId) { toast("This interaction's contact was discarded, so it can't be saved.", "error"); throw new Error("no contact"); }
    const oppId = await resolveLink(item.links.opportunity);
    if (oppId) data.opportunity_id = oppId;
    saved = await api("POST", `/api/contacts/${contactId}/interactions`, data);
  } else if (item.kind === "update") {
    const url = item.target.type === "opportunity" ? "/api/opportunities" : "/api/contacts";
    saved = await api("PATCH", `${url}/${item.target.id}`, data);
  }

  item.status = "accepted";
  item.savedId = saved.id;
  announceChange();
  return saved.id;
}

async function acceptAll() {
  // Contacts and opportunities first, so tasks and interactions can link to them.
  const order = ["contact", "opportunity", "task", "interaction", "update"];
  const queue = pending().sort((a, b) => order.indexOf(a.kind) - order.indexOf(b.kind));
  let failed = 0;
  for (const item of queue) {
    if (item.status !== "pending") continue;   // may have been saved as another card's link
    try { await acceptItem(item); } catch (err) { failed++; }
  }
  drawReview();
  toast(failed ? `Saved some; ${failed} need fixing` : "All saved 🎉", failed ? "error" : "ok");
}

qaDialog.addEventListener("cancel", (e) => {   // Esc key
  if (review && pending().length && !confirm(`Discard ${pending().length} unsaved card(s)?`)) e.preventDefault();
});

/* ------------------------------------------------------------ 🎤 talk instead of typing */

/*
 * Uses the browser's built-in speech recognition, where it exists (Edge, Chrome,
 * Safari). The browser sends your audio to its own speech service (Microsoft,
 * Google, or Apple) to turn it into text; Launchpad only receives the text.
 * Browsers allow the microphone only on secure pages (https:// or this computer),
 * so on your phone this works through the Mac mini's https:// address.
 * Your phone keyboard's own microphone key works in the box too, button or not.
 */
function speechSupported() {
  return !!(window.SpeechRecognition || window.webkitSpeechRecognition) && window.isSecureContext;
}

/**
 * Listen and turn speech into text. Used by the 🎤 Talk pill and the big button on /talk.
 *   startText  text already in the box (new words are added after it)
 *   onText     called with the full text as words arrive
 *   onStop     called with the final text when listening ends
 * Returns { stop() }. Phones end a listening session after a few seconds of
 * silence, so this quietly starts a new one until you tap Stop (at most 40 times).
 */
function startDictation({ startText = "", onText, onStop }) {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let finalText = startText.trim() ? startText.replace(/\s*$/, " ") : "";
  let stopped = false;
  let restarts = 0;
  let rec = null;

  const begin = () => {
    rec = new Recognition();
    rec.lang = "en-US";
    rec.continuous = true;          // keep listening through pauses
    rec.interimResults = true;      // show words as they come
    rec.onresult = (e) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) finalText += e.results[i][0].transcript.trim() + " ";
        else interim += e.results[i][0].transcript;
      }
      onText(finalText + interim);
    };
    rec.onerror = (e) => {
      if (e.error === "no-speech" || e.error === "aborted") return;   // harmless; keep going
      stopped = true;
      toast(e.error === "not-allowed" || e.error === "service-not-allowed"
        ? "Microphone blocked. Allow it for this site in the browser's settings."
        : `Speech recognition stopped (${e.error}). You can type or use the keyboard's mic instead.`, "error");
    };
    rec.onend = () => {
      if (!stopped && restarts < 40) {
        restarts += 1;
        try { begin(); return; } catch (err) { /* fall through and finish */ }
      }
      onStop(finalText.trim());
    };
    rec.start();
  };
  begin();
  return { stop() { stopped = true; if (rec) rec.stop(); } };
}

(function setUpMicPill() {
  const micBtn = document.getElementById("qa-mic");
  if (!speechSupported()) return;   // button stays hidden; the keyboard's mic key still works
  micBtn.hidden = false;
  let session = null;

  micBtn.addEventListener("click", () => {
    if (session) { session.stop(); return; }
    session = startDictation({
      startText: qaText.value,
      onText: (text) => { qaText.value = text; growTextarea(); },
      onStop: () => {
        session = null;
        micBtn.classList.remove("selected");
        micBtn.setAttribute("aria-pressed", "false");
        micBtn.textContent = "🎤 Talk";
        qaText.focus();
      },
    });
    micBtn.classList.add("selected");
    micBtn.setAttribute("aria-pressed", "true");
    micBtn.textContent = "⏹ Stop";
    toast("Listening… tap Stop when you're done");
  });
})();

setMode("dump");
