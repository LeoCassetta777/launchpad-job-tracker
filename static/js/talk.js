/*
 * talk.js: the Talk screen. Tap the big mic, talk, tap again, then ✨ Sort it out.
 * Sorting works like the quick-add box: the AI turns your words into preview cards,
 * and nothing is saved until you accept them (same review pop-up, from quickadd.js).
 *
 * If this browser can't do speech recognition (or the page isn't https), the big
 * button turns into "Tap to type": the keyboard's own mic key works there instead.
 * The text is kept in this device's storage until it's sorted, so closing the app
 * doesn't lose it.
 */

const talkMic = document.getElementById("talk-mic");
const talkLabel = document.getElementById("talk-label");
const talkText = document.getElementById("talk-text");
const DRAFT_KEY = "lp-talk-draft";
let talking = null;

function saveDraft() {
  try { localStorage.setItem(DRAFT_KEY, talkText.value); } catch (e) { /* private mode: fine */ }
}
try { talkText.value = localStorage.getItem(DRAFT_KEY) || ""; } catch (e) { /* ignore */ }
talkText.addEventListener("input", saveDraft);

function setListening(on) {
  talkMic.classList.toggle("listening", on);
  talkMic.setAttribute("aria-pressed", String(on));
  talkLabel.textContent = on ? "Listening… tap to stop" : "Tap to talk";
}

if (!speechSupported()) {
  talkMic.querySelector(".talk-mic-icon").textContent = "⌨️";
  talkLabel.textContent = "Tap to type";
  document.getElementById("talk-hint").textContent =
    "This browser can't listen here, so tap the box below and use your keyboard's 🎤 key to dictate.";
}

talkMic.addEventListener("click", () => {
  if (!speechSupported()) { talkText.focus(); return; }
  if (talking) { talking.stop(); return; }
  if (navigator.vibrate) navigator.vibrate(30);
  talking = startDictation({
    startText: talkText.value,
    onText: (text) => { talkText.value = text; saveDraft(); },
    onStop: () => { talking = null; setListening(false); saveDraft(); },
  });
  setListening(true);
});

document.getElementById("talk-sort").addEventListener("click", async (e) => {
  if (talking) talking.stop();
  const text = talkText.value.trim();
  if (!text) { toast("Say or type something first", "error"); return; }
  const button = e.currentTarget;
  button.disabled = true;
  button.textContent = "🌀 Sorting…";
  try {
    openReview(await apiAI("/api/ai/parse", { text, mode: "dump" }, "(About a tenth of a cent.)"));
  } catch (err) {
    /* already shown */
  } finally {
    button.disabled = false;
    button.textContent = "✨ Sort it out";
  }
});

// After the review pop-up closes: if anything was saved, start fresh.
document.getElementById("qa-dialog").addEventListener("close", () => {
  if (typeof review !== "undefined" && review && review.items.some((i) => i.status === "accepted")) {
    talkText.value = "";
    saveDraft();
  }
});

document.getElementById("talk-clear").addEventListener("click", () => {
  if (talkText.value && !confirm("Clear what you've said?")) return;
  talkText.value = "";
  saveDraft();
});
