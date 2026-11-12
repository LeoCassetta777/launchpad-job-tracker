/*
 * shutdown.js: today's unfinished tasks (move to tomorrow / pick a day / drop),
 * today's numbers, and "log one win" (saved to the activity log).
 */

const sdEl = document.getElementById("shutdown-page");

async function load() {
  const d = await api("GET", "/api/shutdown");
  const winBox = h("input", { type: "text", placeholder: "One win from today, big or small", maxlength: 300, "aria-label": "Today's win" });

  fill(sdEl,
    h("div", { class: "stat-row" },
      h("div", { class: "card stat" }, h("strong", {}, d.done_today.length), h("span", {}, "tasks finished")),
      h("div", { class: "card stat" }, h("strong", {}, fmtMinutes(d.focus_minutes) || "0m"), h("span", {}, "focused")),
      h("div", { class: "card stat" }, h("strong", {}, `+${d.points_today}`), h("span", {}, "points today"))),

    h("section", { class: "card prep-section" },
      h("h2", {}, `1️⃣ Unfinished (${d.tasks.length})`),
      d.tasks.length === 0 ? h("p", {}, "Nothing left over. Clean slate for tomorrow. 🌿")
        : h("div", { class: "shutdown-list" }, d.tasks.map((t) => taskRow(t, d.tomorrow)))),

    h("section", { class: "card prep-section" },
      h("h2", {}, "2️⃣ One win"),
      d.win ? h("p", {}, `✅ Logged: “${d.win}”`) : h("div", { class: "prep-add" }, winBox,
        h("button", { class: "btn btn-primary", type: "button", onclick: async () => {
          if (!winBox.value.trim()) { toast("Write one thing that went right", "error"); return; }
          await api("POST", "/api/wins", { text: winBox.value });
          toast("Win logged. Shut the laptop. 🌙");
          load();
        } }, "Log win"))),

    d.done_today.length > 0 && h("details", { class: "card" }, h("summary", {}, `Finished today (${d.done_today.length})`),
      h("ul", {}, d.done_today.map((t) => h("li", {}, t)))));
}

function taskRow(t, tomorrow) {
  const date = h("input", { type: "date", value: tomorrow, "aria-label": `New day for ${t.title}` });
  const move = async (day) => {
    await api("PATCH", `/api/tasks/${t.id}`, { planned_date: day });
    toast(`Moved to ${fmtDate(day)}`);
    load();
  };
  return h("article", { class: "card shutdown-row" },
    h("div", {},
      h("strong", {}, t.title),
      h("div", { class: "muted small" }, [t.opp_company, t.due_date && `due ${fmtDate(t.due_date)}`].filter(Boolean).join(" · "))),
    h("div", { class: "inline-row wrap" },
      h("button", { class: "btn btn-small btn-primary", type: "button", onclick: () => move(tomorrow) }, "➡️ Tomorrow"),
      date,
      h("button", { class: "btn btn-small", type: "button", onclick: () => move(date.value) }, "Pick day"),
      h("button", { class: "btn btn-small btn-danger", type: "button", onclick: async () => {
        if (!confirm(`Drop "${t.title}"? It will be deleted.`)) return;
        await api("DELETE", `/api/tasks/${t.id}`);
        toast("Dropped. Letting go counts too.");
        load();
      } }, "🗑 Drop")));
}

load();
