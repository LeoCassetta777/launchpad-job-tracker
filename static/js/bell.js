/*
 * bell.js: the 🔔 in the header. Shows the same reminders that went out by
 * email/push, newest first. Opening the panel marks them read.
 */

const bellBtn = document.getElementById("bell-btn");
const bellPanel = document.getElementById("bell-panel");
const bellCount = document.getElementById("bell-count");
const BELL_ICONS = { deadline: "📅", followup: "⏳", contact: "👤", next_action: "➡️", digest: "☀️", weekly_plan: "🗺️",
                     weekly_review: "🏋️", streak: "🔥", shutdown: "🌙", test: "🧪" };

async function loadBell() {
  let data;
  try {
    data = await fetch("/api/notifications").then((r) => r.json());
  } catch (e) {
    return; // offline or server restarting; try again next time
  }
  bellCount.textContent = data.unread > 9 ? "9+" : data.unread;
  bellCount.hidden = data.unread === 0;
  bellBtn.setAttribute("aria-label", `Notifications (${data.unread} unread)`);
  fill(bellPanel, 
    h("div", { class: "bell-head" }, h("strong", {}, "Reminders"),
      h("a", { href: "/settings#reminders", class: "small" }, "Settings")),
    data.items.length === 0 && h("p", { class: "muted small bell-empty" }, "Nothing yet. Reminders show up here as well as in email/push."),
    h("ul", { class: "bell-list" }, data.items.map((n) =>
      h("li", { class: n.read_at ? "" : "unread" },
        h("a", { href: n.link || "/" },
          h("span", { class: "bell-icon", "aria-hidden": "true" }, BELL_ICONS[n.trigger] || "🔔"),
          h("span", {},
            h("span", { class: "bell-title" }, n.title),
            h("span", { class: "muted small" }, fmtTimestamp(n.created_at),
              n.error && h("span", { class: "bell-error", title: n.error }, " · ⚠️ not delivered")))))))
  );
}

bellBtn.addEventListener("click", async (e) => {
  e.stopPropagation();
  const opening = bellPanel.hidden;
  bellPanel.hidden = !opening;
  bellBtn.setAttribute("aria-expanded", String(opening));
  if (opening && !bellCount.hidden) {
    await api("POST", "/api/notifications/read", {});
    bellCount.hidden = true;
  }
});
document.addEventListener("click", (e) => {
  if (!bellPanel.hidden && !bellPanel.contains(e.target)) { bellPanel.hidden = true; bellBtn.setAttribute("aria-expanded", "false"); }
});

loadBell();
setInterval(loadBell, 2 * 60 * 1000); // check every 2 minutes
