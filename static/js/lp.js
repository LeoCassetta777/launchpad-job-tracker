/*
 * lp.js: helpers shared by every page.
 *
 *   h(...)            build HTML elements safely (text is never treated as HTML)
 *   api(...)          talk to the Flask server
 *   dates             today in Eastern Time, "in 3 days", "Mon, Nov 9", ...
 *   badges & cards    the little stickers and the opportunity/task cards
 *   toast, modal      small pop-up messages and questions
 */

// The choice lists from constants.py (stages, urgency, ...), embedded in base.html.
const CONST = JSON.parse(document.getElementById("lp-constants").textContent);

/* ------------------------------------------------------------ building elements */

/**
 * Create an element. Example:
 *   h("a", { class: "btn", href: "/week", onclick: fn }, "This week")
 * Strings become plain text, so anything typed or pasted (even "<script>") is shown, never run.
 */
function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "dataset") Object.assign(el.dataset, value);
    else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2), value);
    else if (key in el && typeof value !== "string") el[key] = value; // e.g. checked: true
    else el.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

/**
 * Replace an element's contents, skipping null/undefined/false, the same way h() does.
 * (Plain replaceChildren() would show a skipped `cond && h(...)` as the word "false".)
 */
function fill(el, ...children) {
  el.replaceChildren(...children.flat(Infinity).filter((c) => c !== null && c !== undefined && c !== false));
}

/** Only allow http(s) links into href attributes. */
function safeHref(url) {
  return /^https?:\/\//i.test(url || "") ? url : null;
}

/* ------------------------------------------------------------ server calls */

/** Call the API. Shows a red toast and throws if the server says no. */
async function api(method, url, data) {
  const options = { method, headers: { "Content-Type": "application/json" } };
  if (method !== "GET") options.body = JSON.stringify(data ?? {});
  const res = await fetch(url, options);
  if (res.status === 401) {               // logged out (password login): go log in, then come back
    location.href = `/login?next=${encodeURIComponent(location.pathname + location.search)}`;
    throw new Error("Please log in again.");
  }
  const json = await res.json().catch(() => ({}));
  if (!res.ok) {
    const message = json.error || `Something went wrong (${res.status})`;
    if (!json.cap_reached) toast(message, "error");   // cap errors get a "run anyway?" question instead
    const err = new Error(message);
    err.status = res.status;
    err.data = json;
    throw err;
  }
  return json;
}

/** Tell the current page "data changed, redraw". Pages listen for this. */
function announceChange() {
  document.dispatchEvent(new Event("lp:changed"));
}

/* ------------------------------------------------------------ dates (all Eastern Time) */

/** Today's date in Eastern Time as "YYYY-MM-DD", no matter where the laptop thinks it is. */
function todayET() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit",
  }).format(new Date());
}

// Dates are handled as midnight UTC internally so time zones and daylight saving can't shift a day.
function parseDate(s) {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}
function addDays(s, n) {
  const d = parseDate(s);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}
function daysBetween(from, to) {
  return Math.round((parseDate(to) - parseDate(from)) / 86400000);
}

/** "Mon, Nov 9" */
function fmtDate(s, opts = { weekday: "short", month: "short", day: "numeric" }) {
  return s ? parseDate(s).toLocaleDateString("en-US", { timeZone: "UTC", ...opts }) : "";
}

/** "14:30" -> "2:30 PM" */
function fmtTime(hhmm) {
  if (!hhmm) return "";
  let [hr, min] = hhmm.split(":").map(Number);
  const ampm = hr >= 12 ? "PM" : "AM";
  hr = hr % 12 || 12;
  return `${hr}:${String(min).padStart(2, "0")} ${ampm}`;
}

/** Add minutes to "HH:MM" -> "HH:MM" */
function addMinutes(hhmm, minutes) {
  const [hr, min] = hhmm.split(":").map(Number);
  const total = (hr * 60 + min + minutes) % (24 * 60);
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

/** "in 3 days", "today", "2 days ago" */
function countdown(s) {
  const n = daysBetween(todayET(), s);
  if (n === 0) return "today";
  if (n === 1) return "tomorrow";
  if (n === -1) return "yesterday";
  return n > 0 ? `in ${n} days` : `${-n} days ago`;
}

/** How hot a date is, for coloring: past / hot (≤2 days) / warm (≤7) / cool */
function dateHeat(s) {
  const n = daysBetween(todayET(), s);
  if (n < 0) return "past";
  if (n <= 2) return "hot";
  if (n <= 7) return "warm";
  return "cool";
}

/** "2026-11-09 14:03:12" (Eastern) -> "today 2:03 PM" or "Nov 3, 2:03 PM" */
function fmtTimestamp(ts) {
  if (!ts) return "";
  const [d, t] = ts.split(" ");
  const time = fmtTime(t.slice(0, 5));
  const n = daysBetween(d, todayET());
  if (n === 0) return `today ${time}`;
  if (n === 1) return `yesterday ${time}`;
  return `${fmtDate(d, { month: "short", day: "numeric" })}, ${time}`;
}

/** 135 -> "2h 15m" */
function fmtMinutes(min) {
  if (!min) return "";
  const hr = Math.floor(min / 60), m = min % 60;
  return hr ? (m ? `${hr}h ${m}m` : `${hr}h`) : `${m}m`;
}

/* ------------------------------------------------------------ badges */

/** Look up {key, label, icon} in one of the constant lists, e.g. choice("stages", "sent"). */
function choice(list, key) {
  return CONST[list].find((c) => c.key === key) || { key, label: key || "", icon: "" };
}

function typeBadge(type) {
  const c = choice("opportunity_types", type);
  return h("span", { class: `badge type-${c.key}` }, `${c.icon} ${c.label}`);
}

function urgencySticker(urgency, small = false) {
  const c = choice("urgency", urgency);
  return h("span", { class: `sticker urg-${c.key}${small ? " small" : ""}`, title: `Urgency: ${c.label}` },
    h("span", { "aria-hidden": "true" }, c.icon), ` ${c.label}`);
}

function importanceStars(importance) {
  const filled = { low: 1, medium: 2, high: 3 }[importance] || 0;
  return h("span", { class: "stars", title: `Importance: ${choice("importance", importance).label}`,
                     "aria-label": `Importance: ${choice("importance", importance).label}` },
    "★".repeat(filled), h("span", { class: "stars-empty" }, "★".repeat(3 - filled)));
}

/** "📅 in 3 days" with heat color. */
function dateChip(dateStr, icon = "📅", label = "") {
  return h("span", { class: `datechip heat-${dateHeat(dateStr)}`, title: fmtDate(dateStr) },
    `${icon} ${label}${countdown(dateStr)}`);
}

function progressBar(pct) {
  return h("div", { class: "progress", role: "progressbar", "aria-valuenow": pct,
                    "aria-valuemin": 0, "aria-valuemax": 100, title: `${pct}% done` },
    h("div", { class: "progress-fill", style: `width:${pct}%` }));
}

/* ------------------------------------------------------------ cards */

/** Kanban card for an opportunity. Clicking it opens the detail drawer. */
function opportunityCard(o) {
  const closed = o.stage === "closed";
  const open = () => openDrawer("opportunity", o.id);
  return h("article", {
      class: `card opp-card urg-edge-${o.urgency}${closed ? " is-closed" : ""}`,
      dataset: { id: o.id }, tabindex: 0, role: "button",
      "aria-label": `${o.company} ${o.title}`,
      onclick: open, onkeydown: (e) => { if (e.key === "Enter") open(); },
    },
    h("div", { class: "card-top" }, typeBadge(o.type), urgencySticker(o.urgency, true)),
    h("h3", { class: "card-title" }, o.company),
    o.title && h("p", { class: "card-role" }, o.title),
    closed && o.close_reason && h("p", { class: "close-reason" },
      `${choice("close_reasons", o.close_reason).icon} ${choice("close_reasons", o.close_reason).label}`),
    h("div", { class: "card-meta" },
      o.deadline && !closed && dateChip(o.deadline, "📅", "due "),
      o.check_total > 0 && h("span", { class: "meta-pill" }, `☑ ${o.check_done}/${o.check_total}`),
      importanceStars(o.importance)),
    o.next_action && !closed && h("p", {
        class: `next-action${o.next_action_date && dateHeat(o.next_action_date) === "past" ? " is-late" : ""}` },
      h("span", { "aria-hidden": "true" }, "➡️ "), o.next_action,
      o.next_action_date && h("span", { class: "muted" }, ` · ${fmtDate(o.next_action_date)}`)),
    (o.contacts || []).length > 0 && h("div", { class: "people" },
      o.contacts.map((c) => h("span", { class: "person-chip" }, `👤 ${c.name}`))),
    o.tags && h("div", { class: "tags" }, o.tags.split(",").map((t) => h("span", { class: "tag" }, `#${t}`)))
  );
}

/** Card for a task. The round button ticks it done; clicking anywhere else opens the drawer. */
function taskCard(t, { showDate = false } = {}) {
  const done = t.status === "done";
  const timed = !!t.start_time;
  const open = () => openDrawer("task", t.id);
  const repeat = t.repeat && t.repeat !== "none";
  return h("article", {
      class: `card task-card urg-edge-${t.urgency}${done ? " is-done" : ""}${timed ? " is-timed" : ""}`,
      dataset: { id: t.id, kind: "task" }, tabindex: 0, role: "button", "aria-label": t.title,
      onclick: open, onkeydown: (e) => { if (e.key === "Enter" && e.target === e.currentTarget) open(); },
    },
    h("button", {
      class: `check${done ? " checked" : ""}`, type: "button",
      "aria-label": done ? "Mark not done" : "Mark done", title: done ? "Mark not done" : "Mark done",
      onclick: (e) => { e.stopPropagation(); toggleTaskDone(t, e.currentTarget); },
    }, done ? "✓" : ""),
    h("div", { class: "task-body" },
      timed && h("div", { class: "time-block" },
        `🕑 ${fmtTime(t.start_time)}${t.duration_min ? "–" + fmtTime(addMinutes(t.start_time, t.duration_min)) : ""}`),
      h("div", { class: "task-title" }, t.title, repeat && h("span", { title: "Repeats", "aria-label": "Repeats" }, " 🔁")),
      h("div", { class: "card-meta" },
        urgencySticker(t.urgency, true),
        t.est_min && h("span", { class: "meta-pill", title: "Estimated time" }, `⏱ ${fmtMinutes(t.est_min)}`),
        showDate && (t.planned_date || t.due_date) &&
          h("span", { class: "meta-pill" }, fmtDate(t.planned_date || t.due_date)),
        t.due_date && !done && (showDate || t.planned_date && t.planned_date !== t.due_date) &&
          dateChip(t.due_date, "🎯", "due "),
        t.check_total > 0 && h("span", { class: "meta-pill" }, `☑ ${t.check_done}/${t.check_total}`)),
      (t.opp_company || t.contact_name) && h("div", { class: "task-links muted" },
        t.opp_company && `↳ ${t.opp_company}${t.opp_title ? " · " + t.opp_title : ""}`,
        t.opp_company && t.contact_name && "  ",
        t.contact_name && `👤 ${t.contact_name}`),
      !done && t.completeness > 0 && progressBar(t.completeness))
  );
}

/** Small card for an opportunity date on the week view (deadline or next action). */
function oppDateCard(item) {
  const isDeadline = item.kind === "deadline";
  const open = () => openDrawer("opportunity", item.id);
  return h("article", {
      class: `card date-card ${isDeadline ? "is-deadline" : "is-next"}`, tabindex: 0, role: "button",
      dataset: { id: item.id, kind: item.kind },
      onclick: open, onkeydown: (e) => { if (e.key === "Enter") open(); },
    },
    h("div", { class: "date-card-label" }, isDeadline
      ? `📅 Deadline${item.deadline_time ? " " + fmtTime(item.deadline_time) : ""}`
      : "➡️ Next action"),
    h("div", { class: "task-title" }, isDeadline ? `${item.company}${item.title ? " · " + item.title : ""}` : item.next_action),
    !isDeadline && h("div", { class: "muted small" }, item.company),
    h("div", { class: "card-meta" }, urgencySticker(item.urgency, true),
      dateChip(isDeadline ? item.deadline : item.next_action_date, "", "")));
}

/** Tick a task done (or undo), with a little pop. */
async function toggleTaskDone(task, button) {
  const nowDone = task.status !== "done";
  button.classList.add("pop");
  button.textContent = nowDone ? "✓" : "";
  await api("PATCH", `/api/tasks/${task.id}`, { status: nowDone ? "done" : "todo" });
  if (nowDone) toast(task.repeat && task.repeat !== "none" ? "Done! Next one scheduled 🔁" : "Done! 🎉");
  setTimeout(announceChange, 350); // let the pop finish before redrawing
}

/** Little shake when a card lands somewhere new. */
function wiggle(el) {
  el.classList.remove("wiggle");
  void el.offsetWidth; // restart the animation
  el.classList.add("wiggle");
}

/* ------------------------------------------------------------ toasts and modal */

function toast(message, kind = "ok") {
  const el = h("div", { class: `toast toast-${kind}`, role: kind === "error" ? "alert" : "status" }, message);
  document.getElementById("toasts").append(el);
  setTimeout(() => el.classList.add("leaving"), kind === "error" ? 6000 : 2500);
  setTimeout(() => el.remove(), kind === "error" ? 6400 : 2900);
}

/** Ask why a card closed. Resolves to a reason key, or null if cancelled. */
function pickCloseReason(name) {
  const modal = document.getElementById("modal");
  return new Promise((resolve) => {
    let answer = null;
    modal.replaceChildren(
      h("h2", {}, "📦 Closing it out"),
      h("p", {}, `Why is ${name} closed?`),
      h("div", { class: "reason-grid" }, CONST.close_reasons.map((r) =>
        h("button", { type: "button", class: "btn reason-btn",
                      onclick: () => { answer = r.key; modal.close(); } }, `${r.icon} ${r.label}`))),
      h("div", { class: "modal-actions" },
        h("button", { type: "button", class: "btn btn-ghost", onclick: () => modal.close() }, "Cancel")));
    modal.addEventListener("close", () => resolve(answer), { once: true });
    modal.showModal();
  });
}

/* ------------------------------------------------------------ header: add menu + theme */

document.querySelectorAll("[data-new]").forEach((btn) => {
  btn.addEventListener("click", () => {
    btn.closest("details").open = false;
    openDrawer(btn.dataset.new, null);
  });
});

// Close the Add and More menus when clicking elsewhere.
document.addEventListener("click", (e) => {
  document.querySelectorAll(".add-menu, .more-menu").forEach((menu) => {
    if (menu.open && !menu.contains(e.target)) menu.open = false;
  });
});

(function setUpThemePicker() {
  const select = document.getElementById("theme-select");
  select.value = document.documentElement.dataset.theme || "sticker";
  select.addEventListener("change", () => {
    document.documentElement.dataset.theme = select.value;
    try { localStorage.setItem("lp-theme", select.value); } catch (e) { /* private window: fine */ }
    document.dispatchEvent(new Event("lp:theme"));   // e.g. charts redraw in the new colors
  });
})();

/* ------------------------------------------------------------ AI calls (Phase 4) */

/**
 * POST to an AI endpoint. At the monthly spending cap the server says so, and this
 * asks whether to run it anyway (re-sending with override_cap). `costHint` goes in the question.
 */
async function apiAI(url, body = {}, costHint = "") {
  try {
    return await api("POST", url, body);
  } catch (err) {
    if (err.data && err.data.cap_reached &&
        confirm(`${err.message}\n\nRun it anyway? ${costHint}\nYou can raise the cap or allow the rest of the month in Settings → AI spending.`)) {
      return await api("POST", url, { ...body, override_cap: true });
    }
    throw err;
  }
}

/* ------------------------------------------------------------ fit check display */

const FIT_LABELS = { 1: "Not a fit", 2: "Long shot", 3: "Possible", 4: "Good fit", 5: "Strong fit" };

/** The saved result of a fit check, as a card section. */
function fitView(fit) {
  const r = fit.result;
  return h("div", { class: "fit-view" },
    h("div", { class: "fit-score-row" },
      h("span", { class: `fit-score fit-${fit.score}`, title: "Fit score, 1 to 5" }, `${fit.score}/5`),
      h("div", {},
        h("strong", {}, FIT_LABELS[fit.score]),
        h("div", {}, fit.score_reason),
        h("div", { class: "muted small" }, `${fmtTimestamp(fit.created_at)} · with ${fit.document_label} · $${(fit.cost_usd || 0).toFixed(3)}`))),
    (r.notes || []).map((n) => h("p", { class: "muted small" }, `ℹ️ ${n}`)),
    h("h4", {}, "✅ Strong matches"),
    r.strong_matches.length ? h("ul", { class: "fit-list" }, r.strong_matches.map((m) =>
      h("li", {}, h("strong", {}, m.requirement), h("span", { class: "muted" }, ` — ${m.evidence}`))))
      : h("p", { class: "muted small" }, "None found with clear evidence."),
    h("h4", {}, "🧩 Gaps"),
    r.gaps.length ? h("ul", { class: "fit-list" }, r.gaps.map((g) =>
      h("li", {},
        h("span", { class: `gap-chip gap-${g.severity}` }, g.severity === "dealbreaker" ? "⛔ Dealbreaker" : "📈 Learnable"),
        " ", h("strong", {}, g.gap), g.how_to_close && h("div", { class: "muted small" }, `How to close: ${g.how_to_close}`))))
      : h("p", { class: "muted small" }, "No gaps found."),
    h("h4", {}, "🗣️ Talking points"),
    h("ol", { class: "fit-list" }, r.talking_points.map((t) => h("li", {}, t))),
    r.unknowns && r.unknowns.length > 0 && [h("h4", {}, "❔ Unknowns"), h("ul", { class: "fit-list" }, r.unknowns.map((u) => h("li", {}, u)))]);
}

/* ------------------------------------------------------------ question cards (bank + prep page) */

/**
 * One interview question with an answer box that saves when you click away.
 * opts.showOpp: link to the opportunity's prep page. opts.onChange: called after delete/move/star.
 */
function questionCard(q, { showOpp = false, onChange = () => {} } = {}) {
  const kind = choice("question_kinds", q.kind);
  const save = async (fields, message) => {
    Object.assign(q, await api("PATCH", `/api/questions/${q.id}`, fields));
    if (message) toast(message);
  };
  const answer = h("textarea", { rows: 3, "aria-label": "Answer",
    placeholder: q.kind === "to_ask" ? "Their answer / notes" : "Your answer (saves when you click away)" }, q.answer);
  answer.addEventListener("change", () => save({ answer: answer.value }, "Answer saved ✓"));
  const star = h("button", { type: "button", class: `icon-btn star${q.best ? " on" : ""}`,
    title: q.best ? "Your best answer to this question" : "Mark as your best answer",
    "aria-label": "Mark as best answer", "aria-pressed": String(!!q.best),
    onclick: async () => { await save({ best: !q.best }); onChange(); } }, "⭐");

  return h("article", { class: `card question-card kind-${q.kind}` },
    h("div", { class: "question-top" },
      h("span", { class: "badge" }, `${kind.icon} ${kind.label}`),
      (q.tags || "").split(",").filter(Boolean).map((t) => {
        const tag = choice("question_tags", t);
        return h("span", { class: "tag" }, `${tag.icon || "#"} ${tag.label}`);
      }),
      h("span", { class: "spacer" }),
      q.kind !== "to_ask" && star,
      q.kind === "likely" && h("button", { type: "button", class: "btn btn-small", title: "They actually asked this",
        onclick: async () => { await save({ kind: "asked" }, "Moved to “They asked me”"); onChange(); } }, "🎤 They asked it"),
      h("button", { type: "button", class: "icon-btn", "aria-label": "Delete question",
        onclick: async () => { if (!confirm("Delete this question?")) return; await api("DELETE", `/api/questions/${q.id}`); onChange(); } }, "✕")),
    h("p", { class: "question-text" }, q.text),
    showOpp && q.opp_company && h("a", { class: "muted small", href: `/prep/${q.opportunity_id}` },
      `↳ ${q.opp_company}${q.opp_title ? " · " + q.opp_title : ""}`),
    q.note && h("p", { class: "muted small question-note" }, q.note),
    answer);
}

/* ------------------------------------------------------------ "what did you learn?" */

/** After a card closes as rejected or ghosted: an optional lesson for the Rejection Log. */
function askLesson(oppId, name, reason) {
  const modal = document.getElementById("modal");
  const box = h("textarea", { rows: 3, placeholder: "e.g. Tailor the summary to the role; follow up sooner" });
  return new Promise((resolve) => {
    modal.replaceChildren(
      h("h2", {}, reason === "ghosted" ? "👻 Ghosted" : "🚫 Rejected"),
      h("p", {}, `What did you learn from ${name}? Optional, but it feeds your Rejection Log and the weekly coach.`),
      box,
      h("div", { class: "modal-actions" },
        h("button", { type: "button", class: "btn btn-ghost", onclick: () => modal.close() }, "Skip"),
        h("button", { type: "button", class: "btn btn-primary", onclick: async () => {
          if (box.value.trim()) {
            await api("POST", `/api/opportunities/${oppId}/lesson`, { lesson: box.value });
            toast("Lesson saved. Rejections count as reps 💪");
          }
          modal.close();
        } }, "Save")));
    modal.addEventListener("close", () => resolve(), { once: true });
    modal.showModal();
    box.focus();
  });
}
