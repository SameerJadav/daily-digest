// Pronunciation via the browser's built-in speech engine. No network, no service.
// Edit freely — the AI pipeline never touches this file.

function speak(text) {
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "en-IN";
  u.rate = 0.8;
  speechSynthesis.speak(u);
}

// Speaker buttons in the "Words to know" boxes
document.addEventListener("click", (e) => {
  const b = e.target.closest(".say");
  if (b) speak(b.dataset.word);
});

// Select/long-press ANY word on the page -> a small button appears -> tap to hear it
const btn = document.createElement("button");
btn.id = "speak-selection";
btn.textContent = "\u{1F508} say it";
btn.hidden = true;
document.body.appendChild(btn);

btn.addEventListener("pointerdown", (e) => e.preventDefault()); // keep the selection
btn.addEventListener("click", () => {
  if (btn.dataset.word) speak(btn.dataset.word);
  btn.hidden = true;
});

document.addEventListener("selectionchange", () => {
  const sel = window.getSelection();
  const text = sel.toString().trim();
  if (!text || text.length > 80 || sel.rangeCount === 0) {
    btn.hidden = true;
    return;
  }
  const rect = sel.getRangeAt(0).getBoundingClientRect();
  btn.dataset.word = text;
  btn.style.top = window.scrollY + rect.bottom + 10 + "px";
  btn.style.left = Math.max(8, window.scrollX + rect.left) + "px";
  btn.hidden = false;
});
