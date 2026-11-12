/*
 * prep.js: interview prep for one opportunity.
 *   Research notes (save when you click away)
 *   🎤 Questions they asked me, with my answers
 *   🔮 Likely questions (AI, from the posting + fit check)
 *   🙋 Questions I want to ask them
 * Every question here also shows up in the question bank.
 */

const prepEl = document.getElementById("prep-page");
const OPP_ID = Number(prepEl.dataset.oppId);

async function load() {
  const data = await api("GET", `/api/opportunities/${OPP_ID}/prep`);
  const o = data.opportunity;
  document.title = `Prep: ${o.company} · Launchpad`;
  const byKind = (k) => data.questions.filter((q) => q.kind === k);

  // Everything goes inside h("div") so parts that are skipped (null/false) don't show up as text.
  prepEl.replaceChildren(h("div", {},
    h("div", { class: "page-head prep-head" },
      h("div", {},
        h("h1", {}, `🎤 ${o.company}`),
        h("p", { class: "page-sub" }, [o.title, choice("stages", o.stage).label].filter(Boolean).join(" · "))),
      h("div", { class: "inline-row wrap" },
        data.fit && h("span", { class: `fit-score fit-${data.fit.score}`, title: data.fit.score_reason }, `Fit ${data.fit.score}/5`),
        h("button", { class: "btn btn-small", type: "button", onclick: () => openDrawer("opportunity", OPP_ID) }, "Open card"))),

    data.fit && h("details", { class: "card prep-fit" }, h("summary", {}, h("strong", {}, "🎯 Fit check: matches, gaps, talking points")), fitView(data.fit)),

    notesSection(o),

    section("🎤 They asked me", "Log questions right after the interview, while you remember them.", "asked", byKind("asked"), data.bank),
    likelySection(byKind("likely"), !!data.fit),
    section("🙋 I'll ask them", "Good questions show you've done your homework.", "to_ask", byKind("to_ask"), []),
  ));
}

function notesSection(o) {
  const box = h("textarea", { rows: 6, placeholder: "What the company does, recent news, who you'll talk to, why you want this…" }, o.research_notes);
  box.addEventListener("change", async () => {
    await api("PATCH", `/api/opportunities/${OPP_ID}`, { research_notes: box.value });
    toast("Notes saved ✓");
  });
  return h("section", { class: "card prep-section" }, h("h2", {}, "🔎 Research notes"), box);
}

/** A list of questions of one kind, with an "add" row. `bank` feeds autocomplete suggestions. */
function section(title, hint, kind, questions, bank) {
  const listId = `bank-${kind}`;
  const input = h("input", { type: "text", placeholder: "Type a question…", list: bank.length ? listId : null, "aria-label": "New question" });
  const tag = h("select", { "aria-label": "Tag" }, h("option", { value: "" }, "Tag…"),
    CONST.question_tags.map((t) => h("option", { value: t.key }, `${t.icon} ${t.label}`)));
  const add = async () => {
    if (!input.value.trim()) return;
    const q = await api("POST", "/api/questions", { opportunity_id: OPP_ID, kind, text: input.value, tags: tag.value });
    if (q.note) toast(q.note);
    load();
  };
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); add(); } });
  return h("section", { class: "card prep-section" },
    h("h2", {}, title, " ", h("span", { class: "count" }, questions.length)),
    h("p", { class: "muted small" }, hint),
    bank.length > 0 && h("datalist", { id: listId }, bank.map((t) => h("option", { value: t }))),
    h("div", { class: "prep-add" }, input, tag, h("button", { class: "btn btn-small", type: "button", onclick: add }, "Add")),
    h("div", { class: "question-list" }, questions.map((q) => questionCard(q, { onChange: load }))));
}

function likelySection(questions, hasFit) {
  const button = h("button", { class: "btn btn-primary btn-small", type: "button", onclick: async () => {
    button.disabled = true;
    button.textContent = "🔮 Thinking… (about 20 seconds)";
    try {
      const res = await apiAI(`/api/opportunities/${OPP_ID}/questions/generate`, {}, "(About $0.03–0.05.)");
      toast(`Added ${res.added} likely question${res.added === 1 ? "" : "s"} · cost $${res.cost.toFixed(3)}`);
      load();
    } catch (err) {
      button.disabled = false;
      button.textContent = "✨ Generate likely questions";
    }
  } }, questions.length ? "✨ Generate more" : "✨ Generate likely questions");
  return h("section", { class: "card prep-section" },
    h("h2", {}, "🔮 Likely questions ", h("span", { class: "count" }, questions.length)),
    h("p", { class: "muted small" }, "Predicted from the posting", hasFit ? " and your fit check (it probes your gaps)." : ". Run a fit check first for sharper questions.",
      " Uses the stronger AI model, about $0.03–0.05 each time."),
    button,
    h("div", { class: "question-list" }, questions.map((q) => questionCard(q, { onChange: load }))));
}

document.addEventListener("lp:changed", load);
load();
