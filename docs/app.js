// Audio: pre-generated Kokoro voice (female, af_heart) served as MP3s from audio/.
// Browser speechSynthesis is only the fallback (select-any-word, or missing files).
// Edit freely — the AI pipeline never touches this file.

const prefix = document.body.dataset.prefix || "";

// one shared player, fixed at the bottom while something plays
const player = document.createElement("audio");
player.id = "player";
player.controls = true;
player.hidden = true;
document.body.appendChild(player);

let queue = [];
function playQueue(list) {
  queue = list.slice();
  next();
}
function next() {
  if (!queue.length) { player.hidden = true; return; }
  player.src = queue.shift();
  player.hidden = false;
  player.play();
}
player.addEventListener("ended", next);
player.addEventListener("error", next); // missing file: skip on

function slug(term) {
  // must match slug() in audio.py
  return term.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

function speak(text) {
  // fallback only: browser TTS, prefer a female English voice
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  const en = speechSynthesis.getVoices().filter((v) => v.lang.startsWith("en"));
  u.voice =
    en.find((v) => /female|woman|zira|aria|jenny|neerja|heera|veena|libby|sonia/i.test(v.name)) ||
    en[0] || null;
  u.lang = "en-IN";
  u.rate = 0.8;
  speechSynthesis.speak(u);
}

document.addEventListener("click", (e) => {
  const say = e.target.closest(".say");
  if (say) {
    const a = new Audio(`${prefix}audio/v/${slug(say.dataset.word)}.mp3`);
    a.onerror = () => speak(say.dataset.word);
    a.play().catch(() => speak(say.dataset.word));
    return;
  }
  const listen = e.target.closest(".listen");
  if (listen) {
    if (player.src.endsWith(listen.dataset.audio) && !player.paused) player.pause();
    else playQueue([listen.dataset.audio]);
    return;
  }
  if (e.target.closest("#listen-all")) {
    playQueue([...document.querySelectorAll(".listen")].map((b) => b.dataset.audio));
  }
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
