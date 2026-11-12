/*
 * home.js: the strip at the top of the Pipeline page.
 *   📌 Today's Top 3   pinned tasks/opportunities for today
 *   🎯 This week       weekly goals as progress rings (confetti when one is hit)
 *   🔥 Streak & level  streak days, points, level, and quick buttons
 * All numbers come from /api/progress (progress.py), computed from the activity log.
 */

const strip = document.getElementById("today-strip");

/** A progress ring as SVG: `pct` 0-100. */
function ring(pct, done) {
  const r = 26, c = 2 * Math.PI * r;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 64 64");
  svg.setAttribute("class", `ring${done ? " ring-done" : ""}`);
  svg.setAttribute("aria-hidden", "true");
  svg.innerHTML = `<circle cx="32" cy="32" r="${r}" class="ring-track"/>` +
    `<circle cx="32" cy="32" r="${r}" class="ring-fill" stroke-dasharray="${(c * pct) / 100} ${c}" transform="rotate(-90 32 32)"/>`;
  return svg;   // only numbers go into this markup, never user text
}

function celebrateGoals(data) {
  for (const g of data.goals) {
    const key = `lp-goal-${data.week_start}-${g.kind}`;
    let seen = null;
    try { seen = localStorage.getItem(key); } catch (e) { /* ignore */ }
    if (g.done >= g.target && !seen) {
      celebrate();
      toast(`🎯 Goal hit: ${g.label} (${g.done}/${g.target})!`);
      try { localStorage.setItem(key, "1"); } catch (e) { /* ignore */ }
    }
  }
}

async function loadStrip() {
  const data = await api("GET", "/api/progress");
  const lvl = data.level;
  const toNext = lvl.next_at ? Math.round((100 * (data.points - lvl.floor)) / (lvl.next_at - lvl.floor)) : 100;

  fill(strip,
    h("section", { class: "card strip-card top3" },
      h("h2", {}, "📌 Today's Top 3"),
      data.top3.length === 0 && h("p", { class: "muted small" }, "Pin up to three things for today: open a card and click 📌 Top 3."),
      h("ol", { class: "top3-list" }, data.top3.map((p) =>
        h("li", { class: p.item_type === "task" && p.status === "done" ? "is-done" : "" },
          h("button", { class: "linklike", type: "button", onclick: () => openDrawer(p.item_type, p.id) },
            `${p.item_type === "task" ? "✅" : "💼"} ${p.name}`),
          h("button", { class: "icon-btn", type: "button", "aria-label": `Unpin ${p.name}`, onclick: async () => {
            await api("DELETE", `/api/pins/${p.pin_id}`, {});
            loadStrip();
          } }, "✕")))),
      h("div", { class: "inline-row wrap" },
        h("button", { class: "btn btn-small btn-primary", type: "button", onclick: openMinutesPicker }, "⏱ I have __ minutes"),
        h("a", { class: "btn btn-small", href: "/shutdown" }, "🌙 Shutdown"))),

    h("section", { class: "card strip-card goals" },
      h("div", { class: "strip-head" }, h("h2", {}, "🎯 This week"),
        h("button", { class: "btn btn-small btn-ghost", type: "button", onclick: () => editGoals(data) }, "✏️ Goals")),
      h("div", { class: "rings" }, data.goals.map((g) =>
        h("div", { class: "ring-item", title: `${g.label}: ${g.done} of ${g.target}` },
          h("div", { class: "ring-wrap" }, ring(g.percent, g.done >= g.target),
            h("span", { class: "ring-label" }, g.done >= g.target ? "✓" : `${g.done}/${g.target}`)),
          h("span", { class: "small" }, `${g.icon} ${g.label}`))))),

    h("section", { class: "card strip-card level" },
      h("div", { class: `streak${data.streak_at_risk ? " at-risk" : ""}` },
        h("span", { class: "streak-flame", "aria-hidden": "true" }, data.streak ? "🔥" : "🌑"),
        h("div", {},
          h("strong", {}, `${data.streak}-day streak`),
          h("div", { class: "muted small" }, data.streak_at_risk ? "⚠️ At risk: do one thing today to keep it"
            : data.streak ? "Keep it going" : "Finish a task, log an interaction, or move a card forward"))),
      h("div", { class: "level-row" },
        h("span", { class: "level-icon", "aria-hidden": "true" }, lvl.icon),
        h("div", {},
          h("strong", {}, `Level ${lvl.number}: ${lvl.name}`),
          h("div", { class: "muted small" }, lvl.next_at ? `${data.points} pts · ${lvl.next_at - data.points} to ${lvl.next_name}` : `${data.points} pts · max level!`))),
      progressBar(toNext),
      h("div", { class: "muted small" }, `+${data.week_points} points this week`)));

  celebrateGoals(data);
}

/** Pick up to 5 weekly goals and targets. */
function editGoals(data) {
  const modal = document.getElementById("modal");
  const rows = h("div", { class: "goal-rows" });
  const addRow = (g = { kind: "applications", target: 3 }) => {
    const row = h("div", { class: "goal-row" },
      h("select", { "aria-label": "Goal type" }, data.goal_kinds.map((k) => h("option", { value: k.key, selected: k.key === g.kind }, `${k.icon} ${k.label}`))),
      h("input", { type: "number", min: 1, max: 200, value: g.target, "aria-label": "Target per week" }),
      h("button", { class: "icon-btn", type: "button", "aria-label": "Remove goal", onclick: () => row.remove() }, "✕"));
    rows.append(row);
  };
  data.goals.forEach(addRow);
  modal.replaceChildren(
    h("h2", {}, "🎯 Weekly goals"),
    h("p", { class: "muted small" }, "Counted Monday to Sunday. Applications = cards moved to Sent; outreach also counts emails, calls, and chats you log on contacts."),
    rows,
    h("button", { class: "btn btn-small", type: "button", onclick: () => rows.children.length < 5 && addRow() }, "＋ Add goal"),
    h("div", { class: "modal-actions" },
      h("button", { class: "btn btn-ghost", type: "button", onclick: () => modal.close() }, "Cancel"),
      h("button", { class: "btn btn-primary", type: "button", onclick: async () => {
        const goals = [...rows.children].map((r) => ({ kind: r.querySelector("select").value, target: Number(r.querySelector("input").value) }));
        await api("POST", "/api/goals", { goals });
        modal.close();
        toast("Goals saved 🎯");
        loadStrip();
      } }, "Save")));
  modal.showModal();
}

document.addEventListener("lp:changed", loadStrip);
loadStrip();
