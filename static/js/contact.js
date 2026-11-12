/*
 * contact.js: one contact's page.
 * Details at the top, a quick "log interaction" form, the timeline of
 * everything you've logged, and the opportunities and tasks they're linked to.
 */

const pageEl = document.getElementById("contact-page");
const CONTACT_ID = Number(pageEl.dataset.contactId);

async function load() {
  const [c, allOpps] = await Promise.all([
    api("GET", `/api/contacts/${CONTACT_ID}`),
    api("GET", "/api/opportunities"),
  ]);
  document.title = `${c.name} · Launchpad`;
  pageEl.replaceChildren(header(c), logForm(c), h("div", { class: "contact-columns" },
    timeline(c), h("div", {}, linkedOpportunities(c, allOpps), linkedTasks(c))));
}

function header(c) {
  const linkedin = safeHref(c.linkedin);
  const due = c.follow_up_date && c.follow_up_date <= todayET();
  return h("section", { class: `card contact-hero${due ? " needs-follow-up" : ""}` },
    h("div", { class: "contact-hero-main" },
      h("h1", {}, c.name),
      (c.role || c.company) && h("p", { class: "contact-sub" }, [c.role, c.company].filter(Boolean).join(" @ ")),
      h("div", { class: "card-meta" },
        h("span", { class: "meta-pill" }, c.last_contacted ? `💬 Last contact ${countdown(c.last_contacted)}` : "💬 Never contacted"),
        c.follow_up_date ? dateChip(c.follow_up_date, "⏰", "follow up ") : h("span", { class: "meta-pill" }, "⏰ No follow-up set"),
        c.how_met && h("span", { class: "meta-pill" }, `🤝 ${c.how_met}`)),
      c.notes && h("p", { class: "contact-notes" }, c.notes)),
    h("div", { class: "contact-hero-actions" },
      c.email && h("a", { class: "btn btn-small", href: `mailto:${c.email}` }, `✉️ ${c.email}`),
      linkedin && h("a", { class: "btn btn-small", href: linkedin, target: "_blank", rel: "noopener noreferrer" }, "in LinkedIn ↗"),
      c.follow_up_date && h("a", { class: "btn btn-small", href: `/calendar/contact/${c.id}.ics`, download: true }, "📅 Add follow-up to calendar"),
      h("button", { class: "btn btn-small", type: "button", onclick: () => openDrawer("contact", c.id) }, "✏️ Edit")));
}

/** Quick form: what happened, when, optional note, and when to follow up next. */
function logForm(c) {
  let kind = "emailed";
  const kindButtons = CONST.interaction_kinds.map((k) =>
    h("button", { type: "button", class: `pill${k.key === kind ? " selected" : ""}`, "aria-pressed": String(k.key === kind),
      onclick: (e) => {
        kind = k.key;
        e.currentTarget.parentElement.querySelectorAll(".pill").forEach((b) => {
          b.classList.toggle("selected", b === e.currentTarget);
          b.setAttribute("aria-pressed", String(b === e.currentTarget));
        });
      } }, `${k.icon} ${k.label}`));

  const dateInput = h("input", { type: "date", value: todayET(), "aria-label": "When" });
  const noteInput = h("input", { type: "text", placeholder: "Short note (optional)", "aria-label": "Note" });
  const oppSelect = h("select", { "aria-label": "About which opportunity" },
    h("option", { value: "" }, "About… (optional)"),
    (c.opportunities || []).map((o) => h("option", { value: o.id }, o.title ? `${o.company} · ${o.title}` : o.company)));
  const followSelect = h("select", { "aria-label": "Next follow-up" },
    h("option", { value: "keep" }, "Keep follow-up date"),
    h("option", { value: "7" }, "Follow up in 1 week"),
    h("option", { value: "14" }, "Follow up in 2 weeks"),
    h("option", { value: "30" }, "Follow up in a month"),
    h("option", { value: "clear" }, "No follow-up needed"));

  return h("form", { class: "card log-form", onsubmit: async (e) => {
      e.preventDefault();
      const data = { kind, happened_on: dateInput.value, note: noteInput.value };
      if (oppSelect.value) data.opportunity_id = Number(oppSelect.value);
      if (followSelect.value === "clear") data.next_follow_up = null;
      else if (followSelect.value !== "keep") data.next_follow_up = addDays(todayET(), Number(followSelect.value));
      await api("POST", `/api/contacts/${CONTACT_ID}/interactions`, data);
      toast("Logged 📝");
      announceChange();
    } },
    h("h2", {}, "📝 Log an interaction"),
    h("div", { class: "pill-row" }, kindButtons),
    h("div", { class: "log-row" }, dateInput, noteInput, oppSelect, followSelect,
      h("button", { type: "submit", class: "btn btn-primary" }, "Log it")));
}

function timeline(c) {
  return h("section", { class: "card timeline-card" },
    h("h2", {}, "🕰️ Timeline"),
    c.interactions.length === 0 && h("p", { class: "muted" }, "Nothing logged yet."),
    h("ol", { class: "timeline" }, c.interactions.map((i) => {
      const k = choice("interaction_kinds", i.kind);
      return h("li", {},
        h("span", { class: "timeline-icon", "aria-hidden": "true" }, k.icon),
        h("div", { class: "timeline-body" },
          h("div", {}, h("strong", {}, k.label), h("span", { class: "muted" }, ` · ${fmtDate(i.happened_on)} (${countdown(i.happened_on)})`)),
          i.note && h("div", {}, i.note),
          i.opp_company && h("div", { class: "muted small" }, `↳ ${i.opp_company}${i.opp_title ? " · " + i.opp_title : ""}`)),
        h("button", { class: "icon-btn", type: "button", "aria-label": "Delete this entry", onclick: async () => {
          if (!confirm("Delete this entry?")) return;
          await api("DELETE", `/api/interactions/${i.id}`);
          announceChange();
        } }, "✕"));
    })));
}

function linkedOpportunities(c, allOpps) {
  const linkedIds = new Set(c.opportunities.map((o) => o.id));
  const select = h("select", { "aria-label": "Opportunity to link" },
    h("option", { value: "" }, "Link an opportunity…"),
    allOpps.filter((o) => !linkedIds.has(o.id)).map((o) =>
      h("option", { value: o.id }, o.title ? `${o.company} · ${o.title}` : o.company)));
  return h("section", { class: "card side-card" },
    h("h2", {}, "💼 Opportunities"),
    c.opportunities.length === 0 && h("p", { class: "muted" }, "Not linked to anything yet."),
    h("div", { class: "stack" }, c.opportunities.map(opportunityCard)),
    h("div", { class: "inline-row" }, select,
      h("button", { class: "btn btn-small", type: "button", onclick: async () => {
        if (!select.value) return;
        await api("POST", `/api/opportunities/${select.value}/contacts`, { contact_id: CONTACT_ID });
        announceChange();
      } }, "Link")));
}

function linkedTasks(c) {
  return h("section", { class: "card side-card" },
    h("h2", {}, "✅ Tasks"),
    c.tasks.length === 0 && h("p", { class: "muted" }, "No tasks for this person."),
    h("div", { class: "stack" }, c.tasks.map((t) => taskCard(t, { showDate: true }))),
    h("button", { class: "btn btn-small", type: "button",
                  onclick: () => openDrawer("task", null, { contact_id: CONTACT_ID }) }, "＋ Task for this person"));
}

document.addEventListener("lp:changed", load);
load();
