/*
 * focus.js: the focus timer (Pomodoro), the "I have __ minutes" picker, pins, and confetti.
 * Loaded on every page.
 *
 * The timer lives in localStorage, so it keeps running if you switch pages or
 * reload. When a work session ends, its minutes are added to the task's
 * "actual minutes" (POST /api/focus), which feeds estimate-accuracy stats,
 * focus-hour goals, and points. A "logged" marker stops two open tabs from
 * logging the same session twice.
 */

const FOCUS_KEY = "lp-focus";
let focusTick = null;
let focusLengths = { work: 25, brk: 5 };
api("GET", "/api/focus/settings").then((s) => { focusLengths = s; }).catch(() => {});

function readFocus() {
  try { return JSON.parse(localStorage.getItem(FOCUS_KEY) || "null"); } catch (e) { return null; }
}
function writeFocus(state) {
  try { state ? localStorage.setItem(FOCUS_KEY, JSON.stringify(state)) : localStorage.removeItem(FOCUS_KEY); } catch (e) { /* ignore */ }
}

/** Start a focus session on a task (or on nothing in particular). */
function startFocus(task, minutes) {
  const work = minutes || focusLengths.work;
  writeFocus({ taskId: task ? task.id : null, title: task ? task.title : "Focus", phase: "work",
               workMin: work, startedAt: Date.now(), endsAt: Date.now() + work * 60000 });
  document.getElementById("modal").open && document.getElementById("modal").close();
  toast(`⏱ ${work}-minute focus started. You've got this one.`);
  renderFocus();
}

async function logFocus(state, minutes) {
  if (!minutes || minutes < 1 || state.loggedAt === state.startedAt) return;
  state.loggedAt = state.startedAt;
  writeFocus(state);
  const res = await api("POST", "/api/focus", { task_id: state.taskId, minutes });
  toast(`🎉 Logged ${minutes} focus minutes${res.points ? ` · +${res.points} points` : ""}`);
  announceChange();
}

function beep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    osc.frequency.value = 880;
    osc.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.25);
  } catch (e) { /* no sound available */ }
}

async function stopFocus() {
  const state = readFocus();
  if (state && state.phase === "work") {
    const minutes = Math.floor((Date.now() - state.startedAt) / 60000);
    await logFocus(state, Math.min(minutes, state.workMin));
  }
  writeFocus(null);
  renderFocus();
}

/** Draw the floating timer and handle the end of each phase. */
async function renderFocus() {
  const box = document.getElementById("focus-widget");
  const state = readFocus();
  clearInterval(focusTick);
  if (!state) { box.hidden = true; document.title = document.title.replace(/^⏱ \S+ · /, ""); return; }

  const left = state.endsAt - Date.now();
  if (left <= 0) {
    if (state.phase === "work") {
      beep();
      await logFocus(state, state.workMin);
      writeFocus({ ...state, phase: "break", endsAt: Date.now() + focusLengths.brk * 60000 });
      toast(`☕ Break time: ${focusLengths.brk} minutes`);
    } else {
      beep();
      writeFocus(null);
      toast("Break's over. Ready for another round?");
    }
    renderFocus();
    return;
  }
  const mm = String(Math.floor(left / 60000)).padStart(2, "0");
  const ss = String(Math.floor((left % 60000) / 1000)).padStart(2, "0");
  const isWork = state.phase === "work";
  box.hidden = false;
  fill(box,
    h("div", { class: `focus-ring ${isWork ? "work" : "rest"}` }, `${mm}:${ss}`),
    h("div", { class: "focus-info" },
      h("strong", {}, isWork ? "Focusing" : "Break"),
      h("span", { class: "muted small" }, state.title)),
    h("button", { class: "btn btn-small", type: "button", title: isWork ? "Stop and log the minutes so far" : "End the break",
                  onclick: stopFocus }, isWork ? "■ Stop" : "Skip"));
  document.title = `⏱ ${mm}:${ss} · ${document.title.replace(/^⏱ \S+ · /, "")}`;
  focusTick = setInterval(renderFocus, 1000);
}

/* ------------------------------------------------------------ "I have __ minutes" */

function openMinutesPicker() {
  const modal = document.getElementById("modal");
  let minutes = 30;
  let energy = "med";
  const results = h("div", { class: "suggestions" });

  const pills = (options, current, set) => h("div", { class: "pill-row" }, options.map(([value, label]) =>
    h("button", { type: "button", class: `pill${value === current ? " selected" : ""}`, onclick: (e) => {
      set(value);
      e.currentTarget.parentElement.querySelectorAll(".pill").forEach((b) => b.classList.toggle("selected", b === e.currentTarget));
      load();
    } }, label)));

  async function load() {
    const picks = await api("GET", `/api/suggest?minutes=${minutes}&energy=${energy}`);
    fill(results, picks.length ? picks.map((t, i) => h("article", { class: "card suggestion" },
      h("div", { class: "suggestion-rank" }, ["🥇", "🥈", "🥉"][i]),
      h("div", { class: "suggestion-body" },
        h("strong", {}, t.title),
        h("div", { class: "muted small" }, [`~${fmtMinutes(t.remaining_min)} left`, ...t.reasons, t.opp_company].filter(Boolean).join(" · "))),
      h("button", { class: "btn btn-primary btn-small", type: "button",
                    onclick: () => startFocus(t, Math.min(minutes, focusLengths.work, t.remaining_min)) }, "▶ Start")))
      : h("p", { class: "muted" }, "Nothing fits that time and energy. Try more minutes, or add estimates to your tasks."));
  }

  modal.replaceChildren(
    h("h2", {}, "⏱ I have…"),
    pills([[15, "15 min"], [30, "30 min"], [60, "1 hour"], [90, "90 min"]], minutes, (v) => { minutes = v; }),
    h("p", { class: "muted small" }, "…and my energy is"),
    pills([["low", "🔋 Low"], ["med", "🔋🔋 Medium"], ["high", "🔋🔋🔋 High"]], energy, (v) => { energy = v; }),
    h("p", { class: "muted small" }, "Best fits, ranked by urgency, importance, and due date (no AI):"),
    results,
    h("div", { class: "modal-actions" },
      h("button", { class: "btn btn-ghost", type: "button", onclick: () => startFocus(null) }, "Just start a timer"),
      h("button", { class: "btn", type: "button", onclick: () => modal.close() }, "Close")));
  modal.showModal();
  load();
}

/* ------------------------------------------------------------ pins + confetti */

async function pinItem(itemType, itemId) {
  await api("POST", "/api/pins", { item_type: itemType, item_id: itemId });
  toast("📌 Pinned to Today's Top 3");
  announceChange();
}

/** Confetti for big moments (an Offer, a weekly goal hit). */
function celebrate() {
  if (typeof confetti !== "function" || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const colors = ["#FF5A36", "#FFC83D", "#3DDC97", "#4CC9F0", "#B79CFF"];
  confetti({ particleCount: 140, spread: 80, origin: { y: 0.65 }, colors });
  setTimeout(() => confetti({ particleCount: 80, angle: 60, spread: 60, origin: { x: 0 }, colors }), 250);
  setTimeout(() => confetti({ particleCount: 80, angle: 120, spread: 60, origin: { x: 1 }, colors }), 400);
}

window.addEventListener("storage", (e) => { if (e.key === FOCUS_KEY) renderFocus(); });   // other tabs
renderFocus();
