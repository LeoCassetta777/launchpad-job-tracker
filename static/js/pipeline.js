/*
 * pipeline.js: the kanban board (home page).
 * Loads all opportunities, applies the filters, draws one column per stage,
 * and saves the new stage/order when you drag a card.
 */

const board = document.getElementById("board");
const filters = {
  search: document.getElementById("f-search"),
  type: document.getElementById("f-type"),
  urgency: document.getElementById("f-urgency"),
  importance: document.getElementById("f-importance"),
  tag: document.getElementById("f-tag"),
};
let opportunities = [];

// Fill the filter dropdowns from the constant lists.
for (const [select, list] of [[filters.type, "opportunity_types"], [filters.urgency, "urgency"], [filters.importance, "importance"]]) {
  CONST[list].forEach((c) => select.append(h("option", { value: c.key }, `${c.icon} ${c.label}`)));
}

async function load() {
  opportunities = await api("GET", "/api/opportunities");
  refreshTagFilter();
  render();
}

/** Rebuild the tag dropdown from the tags actually in use, keeping the current pick. */
function refreshTagFilter() {
  const current = filters.tag.value;
  const allTags = [...new Set(opportunities.flatMap((o) => (o.tags ? o.tags.split(",") : [])))].sort();
  filters.tag.replaceChildren(h("option", { value: "" }, "Any tag"),
    allTags.map((t) => h("option", { value: t, selected: t === current }, `#${t}`)));
}

/** Does this card pass the current filters? */
function matches(o) {
  const q = filters.search.value.trim().toLowerCase();
  if (filters.type.value && o.type !== filters.type.value) return false;
  if (filters.urgency.value && o.urgency !== filters.urgency.value) return false;
  if (filters.importance.value && o.importance !== filters.importance.value) return false;
  if (filters.tag.value && !(o.tags || "").split(",").includes(filters.tag.value)) return false;
  if (q) {
    const haystack = [o.company, o.title, o.notes, o.tags, o.location, o.next_action,
                      ...(o.contacts || []).map((c) => c.name)].join(" ").toLowerCase();
    if (!haystack.includes(q)) return false;
  }
  return true;
}

function render() {
  const visible = opportunities.filter(matches);
  const filtering = visible.length !== opportunities.length;
  document.getElementById("f-count").textContent = filtering ? `Showing ${visible.length} of ${opportunities.length}` : "";

  board.replaceChildren(...CONST.stages.map((stage) => {
    const cards = visible.filter((o) => o.stage === stage.key);
    const list = h("div", { class: "column-list", dataset: { stage: stage.key } }, cards.map(opportunityCard));
    return h("section", { class: `column stage-${stage.key}` },
      h("header", { class: "column-head" },
        h("span", { class: "column-icon", "aria-hidden": "true" }, stage.icon),
        h("h2", {}, stage.label),
        h("span", { class: "count" }, cards.length)),
      list,
      stage.key === "interested" && h("button", { class: "column-add", type: "button",
        onclick: () => openDrawer("opportunity", null, { stage: "interested" }) }, "＋ Add opportunity"));
  }));

  // Make every column a drop zone. All columns share the group "pipeline" so cards can move between them.
  board.querySelectorAll(".column-list").forEach((list) => {
    new Sortable(list, {
      group: "pipeline",
      animation: 160,
      delay: 180, delayOnTouchOnly: true,   // on a phone, hold briefly to drag so scrolling still works
      ghostClass: "drag-ghost",
      chosenClass: "drag-chosen",
      onEnd: onDrop,
    });
  });
}

/** A card was dropped. Save its stage (if the column changed) and the column's new order. */
async function onDrop(evt) {
  const card = evt.item;
  const id = Number(card.dataset.id);
  const fromStage = evt.from.dataset.stage;
  const toStage = evt.to.dataset.stage;
  if (fromStage === toStage && evt.oldIndex === evt.newIndex) return;

  try {
    if (fromStage !== toStage) {
      const opp = opportunities.find((o) => o.id === id);
      const change = { stage: toStage };
      if (toStage === "closed") {
        const reason = await pickCloseReason(opp.company);
        if (!reason) { render(); return; }   // cancelled: put the card back
        change.close_reason = reason;
      }
      await api("PATCH", `/api/opportunities/${id}`, change);
      toast(`${choice("stages", toStage).icon} Moved to ${choice("stages", toStage).label}`);
      if (toStage === "offer") celebrate();   // 🎉
      if (["rejected", "ghosted"].includes(change.close_reason)) {
        await askLesson(id, opp.company, change.close_reason);   // optional note for the Rejection Log
      }
    }
    const ids = [...evt.to.querySelectorAll(".opp-card")].map((el) => Number(el.dataset.id));
    await api("POST", "/api/opportunities/reorder", { stage: toStage, ids });
  } catch (e) {
    await load(); // something failed: redraw from the server's truth
    return;
  }
  await load();
  const landed = board.querySelector(`.opp-card[data-id="${id}"]`);
  if (landed) wiggle(landed);
}

Object.values(filters).forEach((el) => el.addEventListener("input", render));
document.getElementById("f-clear").addEventListener("click", () => {
  Object.values(filters).forEach((el) => { el.value = ""; });
  render();
});
document.addEventListener("lp:changed", load);
load();
