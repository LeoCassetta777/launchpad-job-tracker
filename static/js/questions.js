/*
 * questions.js: the question bank (all questions from all opportunities).
 * Search and filters run on the server (/api/questions?q=&tag=&kind=).
 */

const bSearch = document.getElementById("b-search");
const bTag = document.getElementById("b-tag");
const bKind = document.getElementById("b-kind");
CONST.question_tags.forEach((t) => bTag.append(h("option", { value: t.key }, `${t.icon} ${t.label}`)));
CONST.question_kinds.forEach((k) => bKind.append(h("option", { value: k.key }, `${k.icon} ${k.label}`)));

let searchTimer = null;

async function load() {
  const params = new URLSearchParams();
  if (bSearch.value.trim()) params.set("q", bSearch.value.trim());
  if (bTag.value) params.set("tag", bTag.value);
  if (bKind.value) params.set("kind", bKind.value);
  const questions = await api("GET", `/api/questions?${params}`);
  document.getElementById("b-count").textContent =
    `${questions.length} question${questions.length === 1 ? "" : "s"} · ${questions.filter((q) => q.answer.trim()).length} answered · ${questions.filter((q) => q.best).length} ⭐`;
  document.getElementById("b-list").replaceChildren(...(questions.length
    ? questions.map((q) => questionCard(q, { showOpp: true, onChange: load }))
    : [h("p", { class: "muted" }, "Nothing here yet. Log questions on a card's prep page, or add a practice question.")]));
}

bSearch.addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(load, 250); });
bTag.addEventListener("change", load);
bKind.addEventListener("change", load);

document.getElementById("b-add").addEventListener("click", async () => {
  const text = prompt("Practice question:");
  if (!text || !text.trim()) return;
  const q = await api("POST", "/api/questions", { kind: "bank", text });
  if (q.note) toast(q.note);
  load();
});

load();
