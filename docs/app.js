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

// every button plays exactly one file (full.mp3 is the whole digest pre-concatenated),
// so playback never needs a programmatic play() that mobile autoplay policies block
function playFile(src) {
  if (player.src.endsWith(src) && !player.paused) { player.pause(); return; }
  player.src = src;
  player.hidden = false;
  player.play();
}
player.addEventListener("ended", () => { player.hidden = true; });
player.addEventListener("error", () => { player.hidden = true; });

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
  if (listen) playFile(listen.dataset.audio);
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
