/*
 * rejections.js: the rejection log, its counts, and plain-English patterns.
 * Bars are plain HTML/CSS (no chart library needed for a few counts).
 */

const rejEl = document.getElementById("rej-page");

/** Horizontal bars: rows of {label, count}. */
function bars(title, caption, rows) {
  const max = Math.max(1, ...rows.map((r) => r.count));
  return h("section", { class: "card bar-card" },
    h("h3", {}, title),
    h("p", { class: "muted small" }, caption),
    rows.length ? h("div", { class: "bars" }, rows.map((r) =>
      h("div", { class: "bar-row" },
        h("span", { class: "bar-label" }, r.label),
        h("span", { class: "bar-track" }, h("span", { class: "bar-fill", style: `width:${(100 * r.count) / max}%` })),
        h("span", { class: "bar-value" }, r.count))))
      : h("p", { class: "muted" }, "No data yet."));
}

async function load() {
  const data = await api("GET", "/api/rejections");
  const s = data.stats;
  if (!s.total) {
    rejEl.replaceChildren(h("p", { class: "muted" }, "Nothing here yet. When a card closes as Rejected or Ghosted, it lands here."));
    return;
  }
  const monthLabel = (m) => new Date(`${m}-15T12:00:00`).toLocaleDateString("en-US", { month: "short", year: "numeric" });

  rejEl.replaceChildren(
    h("div", { class: "stat-row" },
      h("div", { class: "card stat" }, h("strong", {}, s.total), h("span", {}, "closed without an offer")),
      h("div", { class: "card stat" }, h("strong", {}, s.by_reason.rejected || 0), h("span", {}, "🚫 rejected")),
      h("div", { class: "card stat" }, h("strong", {}, s.by_reason.ghosted || 0), h("span", {}, "👻 ghosted")),
      h("div", { class: "card stat" }, h("strong", {}, s.avg_days_open ?? "–"), h("span", {}, "avg. days open")),
      h("div", { class: "card stat" }, h("strong", {}, `${s.with_lessons}/${s.total}`), h("span", {}, "with a lesson"))),

    h("section", { class: "card patterns" },
      h("h2", {}, "🔍 Patterns"),
      h("ul", {}, data.patterns.map((p) => h("li", {}, p)))),

    h("div", { class: "bar-grid" },
      bars("How far it got", "The stage each one reached before it closed. Lots of early exits point at your resume or first email; late exits point at interviews.",
           s.by_stage.map((r) => ({ label: `${choice("stages", r.stage).icon} ${choice("stages", r.stage).label}`, count: r.count }))),
      bars("Where it came from", "Which source each one came through. If one source dominates, try mixing in others.",
           Object.entries(s.by_source).map(([k, n]) => ({ label: choice("sources", k).label || "Unknown", count: n }))),
      bars("Over time", "How many closed each month. More is fine: it means you're applying.",
           s.by_month.map((r) => ({ label: monthLabel(r.month), count: r.count })))),

    h("h2", {}, "📒 Entries"),
    h("div", { class: "rej-list" }, data.items.map(entry)));
}

function entry(r) {
  const lesson = h("textarea", { rows: 2, placeholder: "What did you learn? (saves when you click away)", "aria-label": "Lesson" }, r.lesson);
  lesson.addEventListener("change", async () => {
    await api("PATCH", `/api/rejections/${r.id}`, { lesson: lesson.value });
    toast("Lesson saved ✓");
  });
  return h("article", { class: "card rej-card" },
    h("div", { class: "question-top" },
      h("span", { class: "badge" }, r.reason === "ghosted" ? "👻 Ghosted" : "🚫 Rejected"),
      h("strong", {}, r.company), r.title && h("span", { class: "muted" }, ` · ${r.title}`),
      h("span", { class: "spacer" }),
      h("span", { class: "muted small" }, `reached ${choice("stages", r.stage_reached).label} · ${r.days_open ?? "?"} days · ${fmtTimestamp(r.created_at)}`)),
    lesson);
}

load();
