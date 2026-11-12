/*
 * discover.js: the Discover inbox. Lists found postings, best fit first, with
 * ➕ (make an Interested card) and ✕ (dismiss). Also edits the Sources box.
 */

const listEl = document.getElementById("disc-list");
const statusEl = document.getElementById("disc-status");
const sourcesForm = document.getElementById("sources-form");
let showing = "new";

/** Sticker color for a 0-100 fit score. */
function scoreSticker(score) {
  if (score === null || score === undefined) return h("span", { class: "sticker small", title: "Not scored yet" }, "– /100");
  const level = score >= 75 ? "urg-chill" : score >= 50 ? "urg-pressing" : "urg-on_fire";
  return h("span", { class: `sticker small ${level}`, title: "Fit with your skills profile" }, `${score}/100`);
}

/** Where a posting came from, in words: '80000hours:jobs' -> '🎯 80,000 Hours', 'greenhouse:anthropic' -> '🏢 Anthropic careers'. */
function sourceLabel(source) {
  const [kind, name] = source.split(":");
  if (kind === "80000hours") return "🎯 80,000 Hours";
  if (kind === "aisafety") return "🛡️ aisafety.com";
  if (kind === "web") return "🌐 Web sweep";
  if (kind === "email") return `📬 ${name} alert email`;
  return `🏢 ${name.charAt(0).toUpperCase()}${name.slice(1)} careers`;
}

/* ---------- source filter: show one source at a time ---------- */
const sourceSelect = document.getElementById("disc-source");
let allItems = [];

function drawList(emptyText) {
  // Rebuild the source menu from what's in this tab, keeping the current choice if it still exists.
  const counts = {};
  for (const d of allItems) {
    const label = sourceLabel(d.source);
    counts[label] = (counts[label] || 0) + 1;
  }
  const chosen = sourceSelect.value;
  fill(sourceSelect, h("option", { value: "" }, `All sources (${allItems.length})`),
    Object.keys(counts).sort().map((label) => h("option", { value: label, selected: label === chosen }, `${label} (${counts[label]})`)));
  if (chosen && !counts[chosen]) sourceSelect.value = "";
  const shown = sourceSelect.value ? allItems.filter((d) => sourceLabel(d.source) === sourceSelect.value) : allItems;
  fill(listEl, shown.length ? shown.map(itemCard) : h("p", { class: "muted" }, emptyText));
}

sourceSelect.addEventListener("change", () => drawList("Nothing from this source."));

function itemCard(d) {
  const link = safeHref(d.link);
  const card = h("article", { class: "card disc-card" },
    h("div", { class: "disc-head" },
      scoreSticker(d.score),
      h("div", { class: "disc-titles" },
        h("strong", { class: "disc-title" }, d.title || "(no title)"),
        h("span", { class: "disc-org" }, d.org, d.location ? ` · ${d.location}` : ""))),
    d.score_reason ? h("p", { class: "disc-reason" }, `🎯 ${d.score_reason}`) : null,
    d.summary ? h("p", { class: "muted small" }, d.summary) : null,
    h("div", { class: "disc-meta muted small" },
      typeBadge(d.type), " ",
      sourceLabel(d.source), " · found ", fmtDate(d.found_at.slice(0, 10)),
      d.deadline ? ` · ⏰ deadline ${fmtDate(d.deadline)}` : ""),
    h("div", { class: "inline-row wrap disc-actions" },
      link ? h("a", { class: "btn btn-small", href: link, target: "_blank", rel: "noopener noreferrer" }, "Open posting ↗") : null,
      d.has_text ? h("button", { class: "btn btn-small btn-ghost", type: "button", "data-act": "text" }, "📄 Read here") : null,
      d.status === "new" ? h("button", { class: "btn btn-small btn-primary", type: "button", "data-act": "add" }, "➕ Add to Pipeline") : null,
      d.status === "new" ? h("button", { class: "btn btn-small btn-ghost", type: "button", "data-act": "dismiss" }, "✕ Dismiss") : null,
      d.status === "dismissed" ? h("button", { class: "btn btn-small", type: "button", "data-act": "restore" }, "↩️ Bring back") : null,
      d.status === "added" && d.opportunity_id
        ? h("a", { class: "btn btn-small", href: `/?open=opportunity:${d.opportunity_id}` }, "Open card →") : null));
  card.addEventListener("click", (e) => onAction(e, d, card));
  return card;
}

async function onAction(e, d, card) {
  const btn = e.target.closest("[data-act]");
  if (!btn) return;
  btn.disabled = true;
  try {
    if (btn.dataset.act === "add") {
      await api("POST", `/api/discover/${d.id}/add`, {});
      toast(`Added ${d.org} to Interested ➕`);
      card.remove();
      allItems = allItems.filter((x) => x.id !== d.id);
    } else if (btn.dataset.act === "dismiss" || btn.dataset.act === "restore") {
      await api("POST", `/api/discover/${d.id}/${btn.dataset.act}`, {});
      card.remove();
      allItems = allItems.filter((x) => x.id !== d.id);
    } else if (btn.dataset.act === "text") {
      const full = await api("GET", `/api/discover/${d.id}`);
      const box = card.querySelector(".disc-text") || card.appendChild(h("pre", { class: "disc-text" }));
      box.textContent = full.description;
      btn.remove();
      return;
    }
    load({ keepList: true });
  } finally { btn.disabled = false; }
}

function showSweep(sweep) {
  document.getElementById("sweep-on").checked = sweep.on;
  document.getElementById("sweep-last").textContent = sweep.last
    ? ` Last run ${fmtTimestamp(sweep.last.at)}: ${sweep.last.new} new.` : " Not run yet.";
}

document.getElementById("sweep-on").addEventListener("change", async (e) => {
  await api("POST", "/api/discover/sweep-setting", { on: e.target.checked });
  toast(e.target.checked ? "Sweep on: Mon, Wed, Fri mornings" : "Sweep off");
});

document.getElementById("sweep-run").addEventListener("click", async (e) => {
  const btn = e.currentTarget;
  btn.disabled = true;
  btn.textContent = "⏳ Searching… (up to a minute)";
  try {
    const res = await apiAI("/api/discover/sweep", {}, "A sweep costs about 5 to 10 cents.");
    toast(res.new ? `Found ${res.new} new posting${res.new === 1 ? "" : "s"} ✨` : "Nothing new this time");
    fill(statusEl, h("pre", { class: "code" }, res.log.join("\n")));
    await load();
  } finally {
    btn.disabled = false;
    btn.textContent = "🔎 Run it now";
  }
});

function showStatus(data) {
  if (data.sweep) showSweep(data.sweep);
  const parts = [];
  if (data.last_run) parts.push(h("span", {}, `Last checked ${fmtTimestamp(data.last_run.at)}: ${data.last_run.new} new.`));
  else parts.push(h("span", {}, "Not checked yet."));
  if (!data.profile_set) parts.push(h("span", {}, " Add a ", h("a", { href: "/settings#skills-profile" }, "skills profile"), " to get fit scores."));
  if (!data.gmail_ready && data.sources.senders) parts.push(h("span", {}, " Alert emails need Gmail set up (Settings → Reminders)."));
  fill(statusEl, parts);
  for (const key of ["new", "added", "dismissed"]) {
    const n = data.counts[key] || 0;
    document.querySelector(`[data-count="${key}"]`).textContent = n ? `(${n})` : "";
  }
}

async function load({ keepList = false } = {}) {
  const data = await api("GET", `/api/discover?status=${showing}`);
  showStatus(data);
  if (!keepList || !listEl.children.length) {
    const empty = {
      new: data.sources.senders || data.sources.boards
        ? "Nothing new right now. Discover checks every morning at 7, or press Check now."
        : "No sources yet. Open ⚙️ Sources below to add a career page.",
      added: "Nothing added from Discover yet.",
      dismissed: "Nothing dismissed.",
    }[showing];
    allItems = data.items;
    drawList(empty);
  }
  if (!sourcesForm.dataset.loaded) {
    for (const [k, v] of Object.entries(data.sources)) sourcesForm.elements[k].value = v;
    if (data.gmail_address) document.getElementById("gmail-addr").textContent = data.gmail_address;
    sourcesForm.dataset.loaded = "1";
    if (!data.sources.senders && !data.sources.boards) document.getElementById("disc-sources").open = true;
  }
}

document.querySelectorAll("[data-status]").forEach((btn) => btn.addEventListener("click", () => {
  showing = btn.dataset.status;
  document.querySelectorAll("[data-status]").forEach((b) => {
    b.classList.toggle("selected", b === btn);
    b.setAttribute("aria-pressed", b === btn ? "true" : "false");
  });
  load();
}));

document.getElementById("disc-run").addEventListener("click", async (e) => {
  const btn = e.currentTarget;
  btn.disabled = true;
  btn.textContent = "⏳ Checking…";
  try {
    const res = await api("POST", "/api/discover/run", {});
    toast(res.new ? `Found ${res.new} new posting${res.new === 1 ? "" : "s"} ✨` : "Nothing new this time");
    fill(statusEl, h("pre", { class: "code" }, res.log.join("\n")));
    const data = await api("GET", `/api/discover?status=${showing}`);
    allItems = data.items;
    drawList("Nothing new right now.");
    for (const key of ["new", "added", "dismissed"]) {
      document.querySelector(`[data-count="${key}"]`).textContent = data.counts[key] ? `(${data.counts[key]})` : "";
    }
  } finally {
    btn.disabled = false;
    btn.textContent = "🔄 Check now";
  }
});

document.getElementById("sources-save").addEventListener("click", async () => {
  const payload = {};
  for (const name of ["senders", "boards", "keywords", "locations"]) payload[name] = sourcesForm.elements[name].value;
  await api("POST", "/api/discover/sources", payload);
  sourcesForm.dataset.loaded = "";
  await load();
  toast("Sources saved ✓ Press Check now to look right away.");
});

load();
