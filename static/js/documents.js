/*
 * documents.js: upload or paste resume / cover letter versions, and manage them.
 * Uploads go as a form (not JSON), so they carry the X-Launchpad header the
 * server requires instead (see api_prep.py).
 */

const docForm = document.getElementById("doc-form");
const docList = document.getElementById("doc-list");
CONST.document_kinds.forEach((k) => document.getElementById("doc-kind").append(h("option", { value: k.key }, `${k.icon} ${k.label}`)));

function fmtBytes(n) {
  return n > 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`;
}

async function load() {
  const docs = await api("GET", "/api/documents");
  if (!docs.length) {
    docList.replaceChildren(h("p", { class: "muted" }, "No documents yet. Add your current resume above."));
    return;
  }
  docList.replaceChildren(...CONST.document_kinds.map((kind) => {
    const mine = docs.filter((d) => d.kind === kind.key);
    if (!mine.length) return h("span");
    return h("section", { class: "doc-group" },
      h("h2", {}, `${kind.icon} ${kind.label}s`),
      h("div", { class: "doc-grid" }, mine.map(docCard)));
  }));
}

function docCard(d) {
  const textBox = h("pre", { class: "code" }, "Loading…");
  return h("article", { class: "card doc-card" },
    h("h3", {}, d.label),
    h("div", { class: "card-meta" },
      d.tailored_for && h("span", { class: "meta-pill tailored-pill" }, `✂️ tailored for ${d.tailored_for}`),
      h("span", { class: "meta-pill" }, d.has_file ? `📎 ${d.filename} · ${fmtBytes(d.size_bytes)}`
                                                   : d.tailored_for ? "🤖 AI-tailored text" : "📝 pasted text"),
      h("span", { class: "meta-pill" }, `${d.text_length.toLocaleString()} characters`),
      h("span", { class: "meta-pill" }, d.times_sent ? `📨 sent ${d.times_sent}×` : "not sent yet")),
    d.text_length === 0 && h("p", { class: "budget-warning small" }, "⚠️ No text: fit checks can't read this one. Edit it and paste the text."),
    h("p", { class: "muted small" }, `Added ${fmtTimestamp(d.created_at)}`),
    h("details", { ontoggle: async (e) => {
        if (!e.target.open) return;
        const full = await api("GET", `/api/documents/${d.id}`);
        textBox.textContent = full.text || "(no text)";
      } },
      h("summary", {}, "See the text the AI reads"), textBox),
    d.tailor_notes && h("details", {},
      h("summary", {}, "What changed, and what it didn't claim"),
      (d.tailor_notes.not_claimed || []).length > 0 && h("ul", { class: "fit-list" },
        d.tailor_notes.not_claimed.map((x) => h("li", {}, `🚫 ${x}`))),
      h("ul", { class: "fit-list" }, (d.tailor_notes.changes || []).map((c) => h("li", {}, `🔧 ${c.what} — ${c.why}`)))),
    h("div", { class: "inline-row wrap" },
      d.has_file && h("a", { class: "btn btn-small", href: `/documents/${d.id}/file` }, "⬇️ Download"),
      d.tailored_for && h("a", { class: "btn btn-small btn-primary", href: `/documents/${d.id}/docx`,
                             title: "Built from the current text, so your edits are included" }, "⬇️ Word (.docx)"),
      h("button", { class: "btn btn-small", type: "button", onclick: () => editDoc(d) }, "✏️ Edit"),
      h("button", { class: "btn btn-small btn-danger", type: "button", onclick: async () => {
        if (!confirm(`Delete "${d.label}"? Its file is removed too.`)) return;
        await api("DELETE", `/api/documents/${d.id}`);
        toast("Deleted");
        load();
      } }, "🗑 Delete")));
}

/** Edit label, kind, and text in the shared modal. */
async function editDoc(d) {
  const full = await api("GET", `/api/documents/${d.id}`);
  const modal = document.getElementById("modal");
  const label = h("input", { type: "text", value: full.label });
  const kind = h("select", {}, CONST.document_kinds.map((k) => h("option", { value: k.key, selected: k.key === full.kind }, `${k.icon} ${k.label}`)));
  const text = h("textarea", { rows: 12 }, full.text);
  modal.replaceChildren(
    h("h2", {}, "✏️ Edit document"),
    h("label", { class: "field" }, h("span", { class: "field-label" }, "Label"), label),
    h("label", { class: "field" }, h("span", { class: "field-label" }, "Kind"), kind),
    h("label", { class: "field" }, h("span", { class: "field-label" }, "Text the AI reads (fix any extraction mistakes)"), text),
    h("div", { class: "modal-actions" },
      h("button", { class: "btn btn-ghost", type: "button", onclick: () => modal.close() }, "Cancel"),
      h("button", { class: "btn btn-primary", type: "button", onclick: async () => {
        await api("PATCH", `/api/documents/${d.id}`, { label: label.value, kind: kind.value, text: text.value });
        modal.close();
        toast("Saved ✓");
        load();
      } }, "Save")));
  modal.showModal();
}

docForm.addEventListener("submit", async () => {
  const label = docForm.elements.label.value.trim();
  const file = docForm.elements.file.files[0];
  const text = docForm.elements.text.value.trim();
  if (!label) { toast("Give it a label first", "error"); return; }
  if (!file && !text) { toast("Choose a file or paste the text", "error"); return; }
  const button = document.getElementById("doc-submit");
  button.disabled = true;
  try {
    let saved;
    if (file) {
      const form = new FormData();
      form.append("label", label);
      form.append("kind", docForm.elements.kind.value);
      form.append("file", file);
      const res = await fetch("/api/documents", { method: "POST", body: form, headers: { "X-Launchpad": "1" } });
      saved = await res.json();
      if (!res.ok) { toast(saved.error || "Upload failed", "error"); return; }
    } else {
      saved = await api("POST", "/api/documents", { label, kind: docForm.elements.kind.value, text });
    }
    toast(saved.warning || `Saved: ${saved.text_length.toLocaleString()} characters of text`, saved.warning ? "error" : "ok");
    docForm.reset();
    load();
  } finally {
    button.disabled = false;
  }
});

load();
