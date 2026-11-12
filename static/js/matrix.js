/*
 * matrix.js: the Eisenhower 2x2 for open tasks and active opportunities.
 * The server decides which box each item is in (api_focus.matrix); dragging an
 * item to another box sends the new urgent/important pair, and the server
 * changes urgency/importance to match.
 */

const quads = [...document.querySelectorAll(".quad")];
const mediumBox = document.getElementById("include-medium");

function matrixCard(it) {
  const open = () => openDrawer(it.item_type, it.id);
  const due = it.due_date || it.deadline;
  return h("article", { class: `card mini-card urg-edge-${it.urgency}`, tabindex: 0, role: "button",
                        dataset: { type: it.item_type, id: it.id }, onclick: open,
                        onkeydown: (e) => { if (e.key === "Enter") open(); } },
    h("div", { class: "mini-title" }, `${it.item_type === "task" ? "✅" : "💼"} ${it.name}`),
    h("div", { class: "card-meta" },
      urgencySticker(it.urgency, true), importanceStars(it.importance),
      due && dateChip(due, "📅", ""),
      it.urgent_by_date && h("span", { class: "meta-pill", title: "Urgent because it's due within 3 days" }, "⏳ due soon")));
}

async function load() {
  const data = await api("GET", "/api/matrix");
  mediumBox.checked = data.include_medium;
  document.getElementById("medium-note").textContent = data.include_medium ? " or Medium" : "";
  for (const q of quads) {
    const urgent = q.dataset.urgent === "1", important = q.dataset.important === "1";
    const items = data.items.filter((i) => i.urgent === urgent && i.important === important);
    const list = q.querySelector(".quad-list");
    list.replaceChildren(...items.map(matrixCard));
    q.querySelector("header h2").dataset.count = items.length;
    Sortable.get(list)?.destroy();
    new Sortable(list, { group: "matrix", animation: 160, delay: 180, delayOnTouchOnly: true,
                         ghostClass: "drag-ghost", chosenClass: "drag-chosen", onEnd: onDrop });
  }
}

async function onDrop(evt) {
  if (evt.from === evt.to) return;
  const q = evt.to.closest(".quad");
  const card = evt.item;
  try {
    const res = await api("POST", "/api/matrix/move", {
      item_type: card.dataset.type, item_id: Number(card.dataset.id),
      urgent: q.dataset.urgent === "1", important: q.dataset.important === "1" });
    const what = Object.entries(res.changes).map(([k, v]) => `${k} → ${v}`).join(", ");
    toast(res.still_urgent_by_date ? "It's due within 3 days, so it stays urgent. Change the due date to move it."
                                    : what ? `Updated: ${what}` : "No change needed");
  } finally {
    await load();
  }
  const landed = document.querySelector(`.mini-card[data-type="${card.dataset.type}"][data-id="${card.dataset.id}"]`);
  if (landed) wiggle(landed);
}

mediumBox.addEventListener("change", async () => {
  await api("POST", "/api/matrix/settings", { include_medium: mediumBox.checked });
  load();
});
document.addEventListener("lp:changed", load);
load();
