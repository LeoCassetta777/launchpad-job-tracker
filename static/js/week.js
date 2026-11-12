/*
 * week.js: the This Week page.
 * Asks the server for one Monday–Sunday week (/api/week), then draws the
 * Overdue and Unscheduled lanes and a column per day. Dragging a task onto a
 * day sets its planned day.
 */

const grid = document.getElementById("week-grid");
let weekStart = new URLSearchParams(location.search).get("start") || todayET();

async function load() {
  const week = await api("GET", `/api/week?start=${weekStart}`);
  weekStart = week.start; // the server snaps to Monday
  document.getElementById("export-week").href = `/calendar/week.ics?start=${week.start}`;
  render(week);
}

function itemCard(item, opts) {
  return item.kind === "task" ? taskCard(item, opts) : oppDateCard(item);
}

function render(week) {
  const isThisWeek = week.start <= week.today && week.today <= week.end;
  document.getElementById("week-title").textContent = isThisWeek ? "This Week"
    : `Week of ${fmtDate(week.start, { month: "short", day: "numeric" })}`;
  document.title = `${document.getElementById("week-title").textContent} · Launchpad`;

  // Lanes
  const overdueList = document.getElementById("overdue-list");
  const unscheduledList = document.getElementById("unscheduled-list");
  overdueList.replaceChildren(...week.overdue.map((i) => itemCard(i, { showDate: true })));
  unscheduledList.replaceChildren(...week.unscheduled.map((i) => itemCard(i)));
  document.getElementById("overdue-count").textContent = week.overdue.length;
  document.getElementById("unscheduled-count").textContent = week.unscheduled.length;
  if (!week.overdue.length) overdueList.append(h("p", { class: "lane-empty" }, "Nothing overdue. Nice. 🌿"));
  if (!week.unscheduled.length) unscheduledList.append(h("p", { class: "lane-empty" }, "Every task has a day."));

  // Day columns
  const capacityMin = CONST.daily_capacity_hours * 60;
  grid.replaceChildren(...week.days.map((day) => {
    const pct = Math.min(100, Math.round((100 * day.est_min) / capacityMin));
    const load = day.est_min > capacityMin ? "over" : day.est_min > capacityMin * 0.75 ? "full" : "ok";
    const isToday = day.date === week.today;
    const isPast = day.date < week.today;
    return h("section", { class: `day${isToday ? " is-today" : ""}${isPast ? " is-past" : ""}` },
      h("header", { class: "day-head" },
        h("div", {},
          h("div", { class: "day-name" }, fmtDate(day.date, { weekday: "long" }), isToday && h("span", { class: "today-pill" }, "today")),
          h("div", { class: "day-date" }, fmtDate(day.date, { month: "short", day: "numeric" }))),
        h("button", { class: "icon-btn add-btn", type: "button", "aria-label": `Add task on ${fmtDate(day.date)}`,
                      onclick: () => openDrawer("task", null, { planned_date: day.date }) }, "＋")),
      h("div", { class: `load load-${load}`, title: `${fmtMinutes(day.est_min) || "0m"} planned of ${CONST.daily_capacity_hours}h` },
        h("div", { class: "load-bar" }, h("div", { class: "load-fill", style: `width:${pct}%` })),
        h("span", { class: "load-text" },
          day.est_min ? `${(day.est_min / 60).toFixed(1)}h planned` : "free",
          load === "over" && " · overloaded ⚠️")),
      h("div", { class: "day-list", dataset: { date: day.date } }, day.items.map((i) => itemCard(i))));
  }));

  // Drag and drop: only task cards move; deadline/next-action cards stay put.
  const common = { animation: 160, delay: 180, delayOnTouchOnly: true, draggable: ".task-card",
                   ghostClass: "drag-ghost", chosenClass: "drag-chosen", onEnd: onDrop };
  grid.querySelectorAll(".day-list").forEach((list) => makeSortable(list, { ...common, group: "week" }));
  makeSortable(unscheduledList, { ...common, group: "week" });
  makeSortable(overdueList, { ...common, group: { name: "week", put: false } }); // can drag out, not in
}

/** The two lanes are redrawn in place, so remove the old drag handler before adding a new one. */
function makeSortable(el, options) {
  Sortable.get(el)?.destroy();
  return new Sortable(el, options);
}

async function onDrop(evt) {
  if (evt.from === evt.to) return; // order within a day isn't saved
  const id = Number(evt.item.dataset.id);
  const planned = evt.to.dataset.date || null; // unscheduled lane has no date
  try {
    await api("PATCH", `/api/tasks/${id}`, { planned_date: planned });
    toast(planned ? `Planned for ${fmtDate(planned)}` : "Unscheduled");
  } finally {
    await load();
  }
  const landed = document.querySelector(`.task-card[data-id="${id}"]`);
  if (landed) wiggle(landed);
}

function go(start) {
  weekStart = start;
  history.replaceState(null, "", start === todayET() ? "/week" : `/week?start=${start}`);
  load();
}
document.getElementById("prev-week").addEventListener("click", () => go(addDays(weekStart, -7)));
document.getElementById("next-week").addEventListener("click", () => go(addDays(weekStart, 7)));
document.getElementById("this-week").addEventListener("click", () => go(todayET()));
document.addEventListener("lp:changed", load);
load();
