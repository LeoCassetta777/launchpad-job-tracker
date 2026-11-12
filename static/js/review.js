/*
 * review.js: this week's review from the coach (coach.py), your notes, and past reviews.
 * "What the coach saw" shows the exact numbers it was given.
 */

const rvEl = document.getElementById("review-page");
let selected = null;   // week_start being shown

function list(title, items, cls = "") {
  if (!items || !items.length) return null;
  return h("section", { class: `card review-block ${cls}` }, h("h2", {}, title),
    h("ul", { class: "fit-list" }, items.map((x) => h("li", {}, x))));
}

async function load() {
  const data = await api("GET", "/api/reviews");
  const current = data.reviews.find((r) => r.week_start === (selected || data.this_week));
  const generate = h("button", { class: "btn btn-primary", type: "button", onclick: async () => {
    generate.disabled = true;
    generate.textContent = "🏋️ Coach is reading your week… (about 20 seconds)";
    try {
      await apiAI("/api/reviews/generate", {}, "(About $0.02–0.05.)");
      selected = data.this_week;
      toast("Review ready");
      load();
    } catch (err) {
      generate.disabled = false;
      generate.textContent = "🏋️ Generate this week's review";
    }
  } }, current ? "🔁 Regenerate (keeps your notes)" : "🏋️ Generate this week's review");

  const picker = h("select", { "aria-label": "Pick a week", onchange: (e) => { selected = e.target.value; load(); } },
    [data.this_week, ...data.reviews.map((r) => r.week_start)].filter((w, i, a) => a.indexOf(w) === i).map((w) =>
      h("option", { value: w, selected: w === (selected || data.this_week) },
        `Week of ${fmtDate(w, { month: "short", day: "numeric" })}${w === data.this_week ? " (this week)" : ""}`)));

  if (!current) {
    fill(rvEl, h("div", { class: "inline-row wrap" }, picker, (selected || data.this_week) === data.this_week && generate),
      h("p", { class: "muted" }, "No review for this week yet. Uses the stronger AI model, about $0.02–0.05."));
    return;
  }
  const c = current.data.coach;
  const notes = h("textarea", { rows: 5, placeholder: "Your take: what the coach got right or wrong, what you'll change…" }, current.my_notes);

  fill(rvEl,
    h("div", { class: "inline-row wrap" }, picker, current.week_start === data.this_week && generate,
      h("span", { class: `sticker small ${current.status === "saved" ? "urg-chill" : "urg-soon"}` }, current.status === "saved" ? "✓ Saved" : "Draft"),
      h("span", { class: "muted small" }, `${fmtTimestamp(current.updated_at)} · $${current.cost_usd.toFixed(3)}`)),
    h("section", { class: "card review-headline" }, h("p", {}, c.headline)),
    h("div", { class: "review-grid" },
      list("📊 Scoreboard", c.scoreboard),
      list("✅ Went well", c.went_well),
      c.stalled.length > 0 && h("section", { class: "card review-block" }, h("h2", {}, "🧊 Stalled"),
        h("ul", { class: "fit-list" }, c.stalled.map((s) => h("li", {}, h("strong", {}, s.item), h("span", {}, ` — ${s.what_to_do}`))))),
      list("🪞 Hard truths", c.hard_truths, "truths")),
    h("section", { class: "card review-block priorities" }, h("h2", {}, "🎯 Next week's 3 priorities"),
      h("ol", { class: "fit-list" }, c.priorities.map((p) => h("li", {}, h("strong", {}, p.priority), h("div", { class: "muted small" }, p.why))))),
    h("section", { class: "card review-block" }, h("h2", {}, "📝 My notes"), notes,
      h("button", { class: "btn btn-primary", type: "button", onclick: async () => {
        await api("POST", `/api/reviews/${current.id}`, { my_notes: notes.value });
        toast("Review saved ✓");
        load();
      } }, "💾 Save review")),
    h("details", { class: "card" }, h("summary", {}, "What the coach saw (the exact numbers it was given)"),
      h("pre", { class: "code" }, JSON.stringify(current.data.facts, null, 2))));
}

load();
