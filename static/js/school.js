/*
 * school.js: the School page. Shows what the Canvas sync found and lets you paste
 * the Canvas feed links. The server never sends the full links back, only their ends.
 */

const $ = (id) => document.getElementById(id);

/** '2026-11-14 23:59' -> 'Sat, Nov 14 · 11:59 PM' */
function when(stamp, allDay) {
  if (!stamp) return "";
  const day = fmtDate(stamp.slice(0, 10));
  return allDay || stamp.length <= 10 ? day : `${day} · ${fmtTime(stamp.slice(11, 16))}`;
}

function assignmentRow(a) {
  const link = safeHref(a.url);
  const status = a.task_status === "done" ? "✅ done"
    : a.task_id ? "📋 on your task list"
    : "not a task yet (outside the days-ahead window, or you deleted it)";
  return h("li", { class: "school-row" },
    h("div", {}, link ? h("a", { href: link, target: "_blank", rel: "noopener noreferrer" }, a.title) : a.title,
      a.course ? h("span", { class: "muted small" }, ` · ${a.course}`) : null),
    h("div", { class: "small" }, dateChip(a.due_at.slice(0, 10), "⏰", when(a.due_at, a.all_day)),
      h("span", { class: "muted" }, ` ${status}`)));
}

function announcementRow(a) {
  const link = safeHref(a.url);
  return h("li", { class: "school-row" },
    h("details", {},
      h("summary", {}, h("strong", {}, a.title), h("span", { class: "muted small" }, ` · ${a.course} · ${when(a.posted_at)}`)),
      h("p", { class: "school-body" }, a.body || "(no text)"),
      link ? h("a", { class: "small", href: link, target: "_blank", rel: "noopener noreferrer" }, "Open in Canvas ↗") : null));
}

function eventRow(e) {
  const link = safeHref(e.url);
  return h("li", { class: "school-row" },
    h("div", {}, link ? h("a", { href: link, target: "_blank", rel: "noopener noreferrer" }, e.title) : e.title,
      e.course ? h("span", { class: "muted small" }, ` · ${e.course}`) : null),
    h("div", { class: "muted small" }, when(e.due_at, e.all_day)));
}

const list = (items, row, empty) => items.length ? h("ul", { class: "school-list" }, items.map(row)) : h("p", { class: "muted" }, empty);

async function load() {
  const d = await api("GET", "/api/school");
  const connected = d.links.calendar || d.links.feeds.length;
  fill($("school-status"), d.last_run
    ? `Last synced ${fmtTimestamp(d.last_run.at)}.`
    : connected ? "Not synced yet. Press Sync now." : "Not connected yet. Open 🔗 Canvas links below.");
  fill($("school-assignments"), list(d.assignments, assignmentRow,
    d.links.calendar ? "No upcoming assignments in your calendar feed." : "Add your calendar feed link to see assignments."));
  fill($("school-announcements"), list(d.announcements, announcementRow,
    d.links.feeds.length ? "No announcements yet." : "Add a course's announcement feed link to see announcements."));
  fill($("school-events"), list(d.events, eventRow, "Nothing on the course calendar in the next two weeks."));

  fill($("cal-state"), d.links.calendar
    ? h("span", { class: "sticker small urg-chill" }, `✓ Saved: ${d.links.calendar}`)
    : h("span", { class: "sticker small urg-pressing" }, "✕ Not set"));
  $("cal-clear").hidden = !d.links.calendar;
  $("cal-input").placeholder = d.links.calendar ? "Paste a new link to replace it" : "https://…/feeds/calendars/user_….ics";
  fill($("feed-list"), d.links.feeds.length ? d.links.feeds.map((f, i) =>
    h("li", {}, `✓ ${f} `, h("button", { class: "btn btn-small btn-ghost", type: "button", onclick: () => removeFeed(i) }, "Remove")))
    : h("li", { class: "muted" }, "None yet."));
  $("days-ahead").value = d.days_ahead;
  if (!connected) $("school-links").open = true;
}

async function saveLinks(payload, message) {
  await api("POST", "/api/school/links", payload);
  toast(message);
  await load();
}

async function removeFeed(index) {
  if (confirm("Stop reading this course's announcements?")) await saveLinks({ remove_feed: index }, "Removed");
}

$("cal-save").addEventListener("click", async () => {
  const value = $("cal-input").value.trim();
  if (!value) return toast("Paste the Calendar Feed link first", "error");
  await saveLinks({ calendar: value }, "Calendar link saved ✓ Press Sync now to pull assignments.");
  $("cal-input").value = "";
});
$("cal-clear").addEventListener("click", async () => {
  if (confirm("Remove the calendar link? Tasks already made stay on your list.")) await saveLinks({ clear_calendar: true }, "Removed");
});
$("feed-add").addEventListener("click", async () => {
  const value = $("feed-input").value.trim();
  if (!value) return toast("Paste a course's announcement feed link first", "error");
  await saveLinks({ add_feed: value }, "Course feed added ✓");
  $("feed-input").value = "";
});
$("days-save").addEventListener("click", () => saveLinks({ days_ahead: $("days-ahead").value }, "Saved ✓"));

$("school-run").addEventListener("click", async (e) => {
  const btn = e.currentTarget;
  btn.disabled = true;
  btn.textContent = "⏳ Syncing…";
  try {
    const res = await api("POST", "/api/school/run", {});
    $("school-log").textContent = res.log.join("\n");
    $("school-log").hidden = false;
    await load();
    announceChange();
  } finally {
    btn.disabled = false;
    btn.textContent = "🔄 Sync now";
  }
});

load();
