/*
 * drawer.js: the side panel that opens when you click any card (or "+ Add").
 *
 *   openDrawer("opportunity", 12)          edit opportunity #12
 *   openDrawer("task", null, {planned_date: "2026-11-10"})   new task with a preset
 *
 * The form fields for each kind are listed in FORMS below. Saving sends only the
 * fields you changed. Checklist ticks, contact links, and the like save instantly.
 */

const KINDS = {
  opportunity: { url: "/api/opportunities", icon: "💼", noun: "opportunity" },
  task:        { url: "/api/tasks",         icon: "✅", noun: "task" },
  contact:     { url: "/api/contacts",      icon: "👤", noun: "contact" },
};

// Field lists. "options" names a list in CONST (from constants.py),
// or "opportunities"/"contacts" for a dropdown of your records.
const FORMS = {
  opportunity: [
    { section: "Basics" },
    { name: "company", label: "Company / organization", type: "text", required: true },
    { name: "title", label: "Role or title", type: "text" },
    { name: "type", label: "Type", type: "select", options: "opportunity_types", default: "job" },
    { name: "source", label: "Source", type: "select", options: "sources", default: "other" },
    { name: "link", label: "Link", type: "url", placeholder: "https://…" },
    { name: "location", label: "Location", type: "text", placeholder: "Rochester, NY / Remote" },
    { name: "pay", label: "Pay", type: "text", placeholder: "optional" },
    { section: "Status" },
    { name: "stage", label: "Stage", type: "select", options: "stages", default: "interested" },
    { name: "close_reason", label: "Closed because", type: "select", options: "close_reasons", blank: true,
      showIf: (form) => form.stage.value === "closed" },
    { name: "urgency", label: "Urgency", type: "select", options: "urgency", default: "chill" },
    { name: "importance", label: "Importance", type: "select", options: "importance", default: "medium" },
    { name: "deadline", label: "Deadline", type: "date" },
    { name: "deadline_time", label: "Deadline time (optional)", type: "time" },
    { name: "reminders", label: "Deadline reminders", type: "text", placeholder: "default (7,2,0) · or e.g. 14,7,1 · or off" },
    { section: "Next step" },
    { name: "next_action", label: "Next action", type: "text", placeholder: "e.g. Email Sam to ask about the team", wide: true },
    { name: "next_action_date", label: "Next action date", type: "date" },
    { section: "Notes" },
    { name: "tags", label: "Tags (comma-separated)", type: "text", placeholder: "ai, security", wide: true },
    { name: "notes", label: "Notes", type: "textarea", wide: true },
    { section: "Posting" },
    { name: "summary", label: "Summary", type: "textarea", rows: 3, wide: true },
    { name: "requirements", label: "Key requirements (one per line)", type: "textarea", rows: 4, wide: true },
  ],
  task: [
    { section: "Task" },
    { name: "title", label: "What needs doing", type: "text", required: true, wide: true },
    { name: "status", label: "Status", type: "select", options: "task_status", default: "todo" },
    { name: "planned_date", label: "Planned day", type: "date" },
    { name: "due_date", label: "Due date", type: "date" },
    { name: "urgency", label: "Urgency", type: "select", options: "urgency", default: "chill" },
    { name: "importance", label: "Importance", type: "select", options: "importance", default: "medium" },
    { name: "energy", label: "Energy needed", type: "select", options: "energy", default: "med" },
    { name: "repeat", label: "Repeat", type: "select", options: "repeat", default: "none" },
    { section: "Time" },
    { name: "est_min", label: "Estimated minutes", type: "number", min: 0, step: 5 },
    { name: "actual_min", label: "Actual minutes", type: "number", min: 0, step: 5 },
    { name: "start_time", label: "Start time (for calls/interviews)", type: "time" },
    { name: "duration_min", label: "Length in minutes", type: "number", min: 5, step: 5 },
    { name: "completeness", label: "How complete (%)", type: "range", min: 0, max: 100, step: 5, wide: true },
    { section: "Connected to" },
    { name: "opportunity_id", label: "Opportunity", type: "select", options: "opportunities", blank: true },
    { name: "contact_id", label: "Contact", type: "select", options: "contacts", blank: true },
    { name: "notes", label: "Notes", type: "textarea", wide: true },
  ],
  contact: [
    { section: "Who" },
    { name: "name", label: "Name", type: "text", required: true },
    { name: "company", label: "Company", type: "text" },
    { name: "role", label: "Role", type: "text" },
    { name: "email", label: "Email", type: "email" },
    { name: "linkedin", label: "LinkedIn URL", type: "url", placeholder: "https://linkedin.com/in/…" },
    { name: "how_met", label: "How we met", type: "text" },
    { name: "follow_up_date", label: "Next follow-up", type: "date" },
    { name: "notes", label: "Notes", type: "textarea", wide: true },
  ],
};

const drawerEl = document.getElementById("drawer");
const drawerBody = document.getElementById("drawer-body");
const backdropEl = document.getElementById("drawer-backdrop");
let drawerDirty = false; // true when the form has unsaved edits

/* ------------------------------------------------------------ open / close */

async function openDrawer(kind, id, defaults = {}) {
  if (!closeDrawer()) return; // user chose to keep editing the current one
  const meta = KINDS[kind];
  const record = id ? await api("GET", `${meta.url}/${id}`) : { ...defaults };

  // Task forms need the opportunity and contact lists for their dropdowns.
  let lists = {};
  if (kind === "task") {
    const [opportunities, contacts] = await Promise.all([api("GET", "/api/opportunities"), api("GET", "/api/contacts")]);
    lists = {
      opportunities: opportunities.filter((o) => o.stage !== "closed" || o.id === record.opportunity_id)
        .map((o) => ({ key: o.id, label: o.title ? `${o.company} · ${o.title}` : o.company })),
      contacts: contacts.map((c) => ({ key: c.id, label: c.company ? `${c.name} (${c.company})` : c.name })),
    };
  }

  drawerBody.replaceChildren(renderDrawer(kind, id, record, lists));
  drawerDirty = false;
  drawerEl.hidden = false;
  backdropEl.hidden = false;
  requestAnimationFrame(() => drawerEl.classList.add("open"));
  if (!id) drawerBody.querySelector("input, select, textarea")?.focus();
}

/** Close the drawer. Returns false if there are unsaved edits and the user wants to keep them. */
function closeDrawer({ force = false } = {}) {
  if (drawerEl.hidden) return true;
  if (drawerDirty && !force && !confirm("Discard your unsaved changes?")) return false;
  drawerDirty = false;
  drawerEl.classList.remove("open");
  drawerEl.hidden = true;
  backdropEl.hidden = true;
  return true;
}

backdropEl.addEventListener("click", () => closeDrawer());
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !drawerEl.hidden && !document.getElementById("modal").open) closeDrawer();
});

/** Does this record have a date worth putting on a calendar? */
function hasCalendarDate(kind, r) {
  if (kind === "opportunity") return !!(r.deadline || (r.next_action_date && r.next_action));
  if (kind === "task") return !!(r.planned_date || r.due_date);
  return !!r.follow_up_date;
}

/* ------------------------------------------------------------ drawer contents */

function renderDrawer(kind, id, record, lists) {
  const meta = KINDS[kind];
  const title = !id ? `New ${meta.noun}`
    : kind === "opportunity" ? record.company
    : kind === "task" ? record.title : record.name;

  const link = kind === "opportunity" ? safeHref(record.link) : kind === "contact" ? safeHref(record.linkedin) : null;

  const header = h("div", { class: "drawer-head" },
    h("div", {},
      h("div", { class: "drawer-kicker" }, `${meta.icon} ${id ? meta.noun : "new"}`),
      h("h2", { id: "drawer-title" }, title),
      kind === "opportunity" && id && record.title && h("p", { class: "drawer-sub" }, record.title)),
    h("div", { class: "drawer-head-actions" },
      link && h("a", { class: "btn btn-small", href: link, target: "_blank", rel: "noopener noreferrer" }, "Open link ↗"),
      kind === "contact" && id && h("a", { class: "btn btn-small", href: `/contacts/${id}` }, "Full page →"),
      id && kind !== "contact" && h("button", { class: "btn btn-small", type: "button", title: "Pin to Today's Top 3",
        onclick: () => pinItem(kind, id) }, "📌 Top 3"),
      id && kind === "task" && record.status !== "done" && h("button", { class: "btn btn-small", type: "button",
        title: "Start a focus timer on this task", onclick: () => { closeDrawer(); startFocus(record); } }, "▶ Focus"),
      id && hasCalendarDate(kind, record) && h("a", { class: "btn btn-small", href: `/calendar/${kind}/${id}.ics`,
        download: true, title: "Download a calendar file for Outlook / Google / Apple Calendar" }, "📅 Add to calendar"),
      h("button", { class: "btn btn-small btn-ghost", type: "button", "aria-label": "Close",
                    onclick: () => closeDrawer() }, "✕")));

  const form = renderForm(kind, id, record, lists);
  const parts = [header, form];

  if (id && (kind === "opportunity" || kind === "task")) {
    parts.push(checklistSection(kind, id, record.checklist || []));
  }
  if (id && kind === "opportunity" && record.posting_text) {
    parts.push(h("details", { class: "drawer-section posting-text" },
      h("summary", {}, `📄 Original posting (${record.posting_text.length.toLocaleString()} characters)`),
      h("pre", {}, record.posting_text)));
  }
  if (id && kind === "opportunity") {
    parts.push(fitSection(id, record));
    parts.push(sentSection(id));
    parts.push(h("section", { class: "drawer-section" },
      h("h3", { class: "form-section" }, "Interview prep"),
      h("a", { class: "btn btn-small", href: `/prep/${id}` }, "🎤 Open interview prep →")));
    parts.push(linkedContactsSection(id, record.contacts || []));
    parts.push(oppTasksSection(id, record.tasks || []));
  }
  if (id && record.activity) parts.push(activitySection(record.activity));
  if (id) {
    parts.push(h("div", { class: "drawer-danger" },
      h("button", { class: "btn btn-danger btn-small", type: "button",
                    onclick: () => deleteRecord(kind, id, title) }, `🗑 Delete ${meta.noun}`)));
  }
  return h("div", { class: "drawer-inner" }, parts);
}

/** Build the edit form from the FORMS list. */
function renderForm(kind, id, record, lists) {
  const fields = FORMS[kind];
  const form = h("form", { class: "drawer-form", novalidate: true });
  let grid = null;

  for (const f of fields) {
    if (f.section) {
      form.append(h("h3", { class: "form-section" }, f.section));
      grid = h("div", { class: "form-grid" });
      form.append(grid);
      continue;
    }
    grid.append(buildField(f, record[f.name] ?? f.default ?? "", { lists, record }));
  }

  // Show/hide fields that depend on others (e.g. "closed because" only when stage = closed).
  const refreshConditional = () => {
    for (const f of fields.filter((x) => x.showIf)) {
      form.querySelector(`[data-field="${f.name}"]`).hidden = !f.showIf(form.elements);
    }
  };
  refreshConditional();
  form.addEventListener("input", () => { drawerDirty = true; refreshConditional(); });
  form.addEventListener("change", refreshConditional);

  form.append(h("div", { class: "drawer-save" },
    h("button", { type: "submit", class: "btn btn-primary" }, id ? "💾 Save changes" : "✨ Create")));

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const data = collectForm(form, fields, id ? record : null);
    if (id && Object.keys(data).length === 0) { toast("Nothing changed"); return; }
    if (kind === "opportunity" && form.elements.stage.value === "closed" && !form.elements.close_reason.value) {
      toast("Pick why it closed", "error"); return;
    }
    const saved = id
      ? await api("PATCH", `${KINDS[kind].url}/${id}`, data)
      : await api("POST", KINDS[kind].url, data);
    drawerDirty = false;
    toast(id ? "Saved ✓" : "Created ✨");
    announceChange();
    if (kind === "opportunity" && saved.stage === "offer" && record.stage !== "offer") celebrate();   // 🎉
    // Just closed as rejected/ghosted? Offer the optional "what did you learn?" note.
    const justRejected = kind === "opportunity" && saved.stage === "closed" && ["rejected", "ghosted"].includes(saved.close_reason)
      && (record.stage !== "closed" || record.close_reason !== saved.close_reason);
    if (justRejected) {
      closeDrawer({ force: true });
      await askLesson(saved.id, saved.company, saved.close_reason);
    }
    // Re-open on the saved record so checklist, links, and history are available.
    openDrawer(kind, saved.id);
  });
  return form;
}

/**
 * One labelled input for a field definition from FORMS.
 * Also used by the quick-add preview cards (quickadd.js). `guessed` adds the 🤔 flag.
 */
function buildField(f, value, { lists = {}, record = {}, guessed = false } = {}) {
  let input;
  if (f.type === "select") {
    const options = f.options in CONST ? CONST[f.options] : lists[f.options] || [];
    input = h("select", { name: f.name },
      f.blank && h("option", { value: "" }, "—"),
      options.map((o) => h("option", { value: String(o.key), selected: String(o.key) === String(value) },
        o.icon ? `${o.icon} ${o.label}` : o.label)));
  } else if (f.type === "textarea") {
    input = h("textarea", { name: f.name, rows: f.rows || 5 }, value);
  } else if (f.type === "range") {
    const fromChecklist = record.check_total > 0;
    const out = h("output", {}, `${value || 0}%`);
    input = h("div", { class: "range-wrap" },
      h("input", { type: "range", name: f.name, min: f.min, max: f.max, step: f.step, value: value || 0,
                   disabled: fromChecklist, oninput: (e) => { out.textContent = `${e.target.value}%`; } }),
      out,
      fromChecklist && h("span", { class: "muted small" }, "Calculated from the checklist"));
  } else {
    input = h("input", { type: f.type, name: f.name, value, placeholder: f.placeholder,
                         min: f.min, step: f.step, required: f.required });
  }
  return h("label", { class: `field${f.wide ? " wide" : ""}${guessed ? " is-guessed" : ""}`, dataset: { field: f.name } },
    h("span", { class: "field-label" }, f.label, f.required && h("span", { class: "req" }, " *"),
      guessed && h("span", { class: "guess-chip", title: "The AI assumed this. Check it." }, "🤔 guessed")),
    input);
}

/** Read the form. When editing, only return fields that changed. Empty boxes become null. */
function collectForm(form, fields, original) {
  const data = {};
  for (const f of fields) {
    if (f.section) continue;
    const el = form.elements[f.name];
    if (!el || el.disabled) continue;
    let value = el.value;
    if (["number", "range"].includes(f.type) || f.options === "opportunities" || f.options === "contacts") {
      value = value === "" ? null : Number(value);
    } else if (["date", "time"].includes(f.type) || f.name === "close_reason") {
      value = value === "" ? null : value;
    }
    if (f.showIf && !f.showIf(form.elements)) continue;
    if (original) {
      const before = original[f.name] ?? (["number", "range", "date", "time"].includes(f.type) || f.blank ? null : "");
      if (String(before ?? "") === String(value ?? "")) continue;
    } else if (value === "" || value === null) {
      continue;
    }
    data[f.name] = value;
  }
  return data;
}

async function deleteRecord(kind, id, title) {
  if (!confirm(`Delete "${title}"? This can't be undone.`)) return;
  await api("DELETE", `${KINDS[kind].url}/${id}`);
  closeDrawer({ force: true });
  toast("Deleted");
  if (kind === "contact" && location.pathname === `/contacts/${id}`) location.href = "/contacts";
  else announceChange();
}

/* ------------------------------------------------------------ checklist */

function checklistSection(kind, parentId, items) {
  const section = h("section", { class: "drawer-section" });
  const parentKey = kind === "task" ? "task_id" : "opportunity_id";

  const draw = () => {
    const done = items.filter((i) => i.done).length;
    const input = h("input", { type: "text", placeholder: "Add a step and press Enter", "aria-label": "New checklist step" });
    const addForm = h("form", { class: "check-add",
      onsubmit: async (e) => {
        e.preventDefault();
        if (!input.value.trim()) return;
        items.push(await api("POST", "/api/checklist", { [parentKey]: parentId, text: input.value }));
        draw(); announceChange();
        section.querySelector(".check-add input").focus();
      } }, input, h("button", { class: "btn btn-small", type: "submit" }, "Add"));

    fill(section, 
      h("h3", { class: "form-section" }, `Checklist ${items.length ? `(${done}/${items.length})` : ""}`),
      items.length > 0 && progressBar(Math.round((100 * done) / items.length)),
      h("ul", { class: "checklist" }, items.map((item) =>
        h("li", { class: item.done ? "is-done" : "" },
          h("label", {},
            h("input", { type: "checkbox", checked: !!item.done,
              onchange: async (e) => {
                const updated = await api("PATCH", `/api/checklist/${item.id}`, { done: e.target.checked });
                Object.assign(item, updated);
                draw(); announceChange();
                if (updated.done) section.querySelector(`[data-item="${item.id}"]`)?.classList.add("pop");
              } }),
            h("span", { dataset: { item: item.id } }, item.text)),
          h("button", { class: "icon-btn", type: "button", "aria-label": `Remove ${item.text}`,
            onclick: async () => {
              await api("DELETE", `/api/checklist/${item.id}`);
              items.splice(items.indexOf(item), 1);
              draw(); announceChange();
            } }, "✕")))),
      addForm);
  };
  draw();
  return section;
}

/* ------------------------------------------------------------ opportunity extras */

function linkedContactsSection(oppId, contacts) {
  const section = h("section", { class: "drawer-section" });

  const draw = async () => {
    const all = await api("GET", "/api/contacts");
    const linkedIds = new Set(contacts.map((c) => c.id));
    const select = h("select", { "aria-label": "Contact to link" },
      h("option", { value: "" }, "Link a contact…"),
      all.filter((c) => !linkedIds.has(c.id)).map((c) => h("option", { value: c.id }, c.company ? `${c.name} (${c.company})` : c.name)));

    fill(section, 
      h("h3", { class: "form-section" }, "People"),
      contacts.length === 0 && h("p", { class: "muted small" }, "No one linked yet."),
      h("div", { class: "people" }, contacts.map((c) =>
        h("span", { class: "person-chip big" },
          h("a", { href: `/contacts/${c.id}` }, `👤 ${c.name}`),
          c.role && h("span", { class: "muted" }, ` ${c.role}`),
          h("button", { class: "icon-btn", type: "button", "aria-label": `Unlink ${c.name}`,
            onclick: async () => {
              await api("DELETE", `/api/opportunities/${oppId}/contacts/${c.id}`);
              contacts.splice(contacts.indexOf(c), 1);
              draw(); announceChange();
            } }, "✕")))),
      h("div", { class: "inline-row" }, select,
        h("button", { class: "btn btn-small", type: "button", onclick: async () => {
          if (!select.value) return;
          await api("POST", `/api/opportunities/${oppId}/contacts`, { contact_id: Number(select.value) });
          contacts.push(all.find((c) => c.id === Number(select.value)));
          draw(); announceChange();
        } }, "Link")));
  };
  draw();
  return section;
}

/** 🎯 Fit check: the newest result, plus a button to run one (Sonnet, about $0.05). */
function fitSection(oppId, record) {
  const section = h("section", { class: "drawer-section" }, h("h3", { class: "form-section" }, "Fit check"), h("p", { class: "muted small" }, "Loading…"));

  const draw = async () => {
    const [fit, docs, tailored] = await Promise.all([api("GET", `/api/opportunities/${oppId}/fit`), api("GET", "/api/documents"),
                                                     api("GET", `/api/opportunities/${oppId}/tailored`)]);
    const resumes = docs.filter((d) => d.kind === "resume" && !d.opportunity_id);   // tailor from originals, not copies
    const select = h("select", { "aria-label": "Resume to check against" },
      h("option", { value: "" }, "Skills profile only (no resume)"),
      resumes.map((d, i) => h("option", { value: d.id, selected: fit.latest ? d.id === fit.latest.document_id : i === 0 }, `📄 ${d.label}`)));
    const hasPosting = record.posting_text || record.requirements || record.summary;
    const button = h("button", { class: "btn btn-primary btn-small", type: "button", disabled: !hasPosting, onclick: async () => {
      button.disabled = true;
      button.textContent = "🎯 Checking… (about 20–40 seconds)";
      try {
        await apiAI(`/api/opportunities/${oppId}/fit`, { document_id: select.value ? Number(select.value) : null }, "(About $0.03–0.07.)");
        toast("Fit check saved 🎯");
        draw();
      } catch (err) {
        button.disabled = false;
        button.textContent = "🎯 Run fit check";
      }
    } }, fit.latest ? "🔁 Re-run fit check" : "🎯 Run fit check");

    // ✂️ Tailor: a new, truthful copy of the chosen resume aimed at this role.
    const tailorBtn = h("button", { class: "btn btn-small", type: "button", disabled: !hasPosting, onclick: async () => {
      if (!select.value) { toast("Pick a resume to tailor", "error"); return; }
      tailorBtn.disabled = true;
      tailorBtn.textContent = "✂️ Tailoring… (about 30 seconds)";
      try {
        await apiAI(`/api/opportunities/${oppId}/tailor`, { document_id: Number(select.value) }, "(About $0.03–0.05.)");
        toast("Tailored copy saved ✂️ Your original is unchanged.");
        draw();
      } catch (err) {
        tailorBtn.disabled = false;
        tailorBtn.textContent = "✂️ Tailor this resume";
      }
    } }, "✂️ Tailor this resume");

    fill(section,
      h("h3", { class: "form-section" }, "Fit check & tailored resume"),
      !hasPosting && h("p", { class: "budget-warning small" }, "Add the posting first (paste or clip it, or fill in Summary / Key requirements)."),
      resumes.length === 0 && h("p", { class: "muted small" }, "Tip: add your resume on the Documents page for a sharper check."),
      h("div", { class: "inline-row wrap" }, select, button, tailorBtn),
      h("p", { class: "muted small" }, "Both use the stronger AI model: about $0.02–0.05 each. Results are saved here."),
      tailored.map(tailoredView),
      fit.latest ? fitView(fit.latest) : h("p", { class: "muted small" }, "No fit check yet."),
      fit.history.length > 1 && h("p", { class: "muted small" }, `Earlier checks: ${fit.history.slice(1).map((f) => `${f.score}/5 (${fmtTimestamp(f.created_at)})`).join(", ")}`));
  };
  draw();
  return section;
}

/** One tailored resume: download, what changed, and what it deliberately didn't claim. */
function tailoredView(t) {
  const n = t.tailor_notes || {};
  return h("details", { class: "card tailored-card" },
    h("summary", {}, h("strong", {}, `✂️ ${t.label}`), h("span", { class: "muted small" }, ` · ${fmtTimestamp(t.created_at)}`)),
    h("div", { class: "inline-row wrap" },
      h("a", { class: "btn btn-small btn-primary", href: `/documents/${t.id}/docx` }, "⬇️ Download Word"),
      h("a", { class: "btn btn-small", href: "/documents" }, "✏️ Review / edit text")),
    (n.not_claimed || []).length > 0 && h("div", {},
      h("h4", {}, "🚫 Not claimed (you haven't shown these yet)"),
      h("ul", { class: "fit-list" }, n.not_claimed.map((x) => h("li", {}, x)))),
    h("h4", {}, "🔧 What changed"),
    h("ul", { class: "fit-list" }, (n.changes || []).map((c) => h("li", {}, h("strong", {}, c.what), h("span", { class: "muted" }, ` — ${c.why}`)))));
}

/** 📄 Which document versions were sent, and when. */
function sentSection(oppId) {
  const section = h("section", { class: "drawer-section" });

  const draw = async () => {
    const [prep, docs] = await Promise.all([api("GET", `/api/opportunities/${oppId}/prep`), api("GET", "/api/documents")]);
    const select = h("select", { "aria-label": "Document sent" }, h("option", { value: "" }, "Pick a version…"),
      docs.map((d) => h("option", { value: d.id }, `${choice("document_kinds", d.kind).icon} ${d.label}`)));
    const date = h("input", { type: "date", value: todayET(), "aria-label": "Date sent" });
    fill(section, 
      h("h3", { class: "form-section" }, "Sent materials"),
      prep.sent.length === 0 && h("p", { class: "muted small" }, "Nothing recorded yet."),
      h("ul", { class: "checklist" }, prep.sent.map((s) => h("li", {},
        h("span", { class: "sent-label" }, `${choice("document_kinds", s.kind).icon} ${s.label}`),
        h("span", { class: "muted small" }, fmtDate(s.sent_on)),
        h("button", { class: "icon-btn", type: "button", "aria-label": `Remove ${s.label}`, onclick: async () => {
          await api("DELETE", `/api/sent-documents/${s.id}`); draw();
        } }, "✕")))),
      docs.length === 0 ? h("p", { class: "muted small" }, h("a", { href: "/documents" }, "Add a document"), " to record what you sent.")
        : h("div", { class: "inline-row wrap" }, select, date, h("button", { class: "btn btn-small", type: "button", onclick: async () => {
          if (!select.value) { toast("Pick a document", "error"); return; }
          await api("POST", `/api/opportunities/${oppId}/documents`, { document_id: Number(select.value), sent_on: date.value });
          toast("Recorded 📨");
          draw();
        } }, "Record")));
  };
  draw();
  return section;
}

function oppTasksSection(oppId, tasks) {
  return h("section", { class: "drawer-section" },
    h("h3", { class: "form-section" }, "Tasks"),
    tasks.length === 0 && h("p", { class: "muted small" }, "No tasks yet."),
    h("div", { class: "stack" }, tasks.map((t) => taskCard(t, { showDate: true }))),
    h("button", { class: "btn btn-small", type: "button",
                  onclick: () => openDrawer("task", null, { opportunity_id: oppId }) }, "＋ Task for this"));
}

function activitySection(activity) {
  return h("section", { class: "drawer-section" },
    h("h3", { class: "form-section" }, "History"),
    activity.length === 0 && h("p", { class: "muted small" }, "Nothing yet."),
    h("ul", { class: "activity" }, activity.map((a) =>
      h("li", {}, h("span", { class: "activity-when" }, fmtTimestamp(a.created_at)), " ", a.summary))));
}

/* ------------------------------------------------------------ links like /?open=opportunity:12 */

// Email reminders link to "/?open=kind:id". Open that card's drawer once the page has loaded.
(function openFromLink() {
  const target = new URLSearchParams(location.search).get("open");
  const match = target && target.match(/^(opportunity|task|contact):(\d+)$/);
  if (!match) return;
  history.replaceState(null, "", location.pathname);   // so a refresh doesn't reopen it
  window.addEventListener("load", () => openDrawer(match[1], Number(match[2])));
})();
