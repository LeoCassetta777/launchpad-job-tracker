/*
 * contacts.js: the contact list.
 * Sorting, searching, and highlighting people whose follow-up date has arrived.
 */

const contactGrid = document.getElementById("contact-grid");
const searchBox = document.getElementById("c-search");
const sortSelect = document.getElementById("c-sort");
let contacts = [];

async function load() {
  contacts = await api("GET", "/api/contacts");
  render();
}

function followUpDue(c) {
  return c.follow_up_date && c.follow_up_date <= todayET();
}

function sorted(list) {
  const by = sortSelect.value;
  const copy = [...list];
  if (by === "name") copy.sort((a, b) => a.name.localeCompare(b.name));
  // "Coldest first": never-contacted at the top, then the oldest last contact.
  if (by === "last") copy.sort((a, b) => (a.last_contacted || "").localeCompare(b.last_contacted || ""));
  // Soonest follow-up first; people with no follow-up date go last.
  if (by === "followup") copy.sort((a, b) => (a.follow_up_date || "9999").localeCompare(b.follow_up_date || "9999"));
  return copy;
}

function render() {
  const q = searchBox.value.trim().toLowerCase();
  const visible = contacts.filter((c) =>
    !q || [c.name, c.company, c.role, c.notes, c.how_met, c.email].join(" ").toLowerCase().includes(q));

  const due = contacts.filter(followUpDue).length;
  document.getElementById("contacts-summary").textContent = due
    ? `⏰ ${due} follow-up${due === 1 ? " is" : "s are"} due. They have a red outline.`
    : "People you're talking to. No follow-ups due right now. 🌿";

  if (!visible.length) {
    contactGrid.replaceChildren(h("p", { class: "muted" }, contacts.length ? "No matches." : "No contacts yet. Use ＋ Add → Contact."));
    return;
  }
  contactGrid.replaceChildren(...sorted(visible).map((c) =>
    h("a", { class: `card contact-card${followUpDue(c) ? " needs-follow-up" : ""}`, href: `/contacts/${c.id}` },
      h("div", { class: "contact-name" }, c.name),
      (c.role || c.company) && h("div", { class: "muted" }, [c.role, c.company].filter(Boolean).join(" @ ")),
      h("div", { class: "card-meta" },
        h("span", { class: "meta-pill", title: "Last contacted" },
          c.last_contacted ? `💬 ${countdown(c.last_contacted)}` : "💬 never contacted"),
        c.follow_up_date && dateChip(c.follow_up_date, "⏰", "follow up "),
        c.opportunity_count > 0 && h("span", { class: "meta-pill" }, `💼 ${c.opportunity_count}`)))));
}

searchBox.addEventListener("input", render);
sortSelect.addEventListener("change", render);
document.addEventListener("lp:changed", load);
load();
