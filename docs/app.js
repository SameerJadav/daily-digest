// Playback of pre-generated Kokoro MP3s (female voice af_heart) through the
// browser's NATIVE audio element — no custom player, nothing to maintain.
// The player appears only while something is playing and hides itself after.
// speechSynthesis is only the fallback for vocab on days whose audio has been
// pruned (audio is kept for the last 7 days) and for the select-any-word button.
// Edit freely — the AI pipeline never touches this file.

const prefix = document.body.dataset.prefix || "";
const pageDate = document.body.dataset.date || "";

const player = document.createElement("audio");
player.id = "player";
player.controls = true;
player.hidden = true;
player.preload = "none";
document.body.appendChild(player);

let activeBtn = null;

// one glyph function for BOTH the per-story button and the whole-digest button,
// driven by the player's own events so native controls stay in sync too
function setGlyph(btn, playing) {
  if (!btn) return;
  btn.classList.toggle("playing", playing);
  btn.setAttribute("aria-pressed", playing ? "true" : "false");
  const glyph = btn.querySelector(".glyph");
  if (glyph) glyph.textContent = playing ? "❘❘" : "▶";
}

function closePlayer() {
  setGlyph(activeBtn, false);
  activeBtn = null;
  player.hidden = true;
}

player.addEventListener("ended", closePlayer);
player.addEventListener("error", closePlayer);
player.addEventListener("pause", () => setGlyph(activeBtn, false));
player.addEventListener("play", () => setGlyph(activeBtn, true));

function slug(term) {
  // must match slug() in audio.py
  return term.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

let sayAudio = null; // the in-flight vocab clip, if any, so only one thing ever plays

// stop anything that isn't the main player: a vocab clip or speechSynthesis
function stopExtras() {
  if (sayAudio) { sayAudio.pause(); sayAudio = null; }
  speechSynthesis.cancel();
}

function stopAll() {
  player.pause();
  stopExtras();
}

function speakFallback(text) {
  // browser TTS, prefer a female English voice
  stopAll();
  const speak = () => {
    const u = new SpeechSynthesisUtterance(text);
    const en = speechSynthesis.getVoices().filter((v) => v.lang.startsWith("en"));
    u.voice =
      en.find((v) => /female|woman|zira|aria|jenny|neerja|heera|veena|libby|sonia/i.test(v.name)) ||
      en[0] || null;
    u.lang = "en-IN";
    u.rate = 0.85;
    speechSynthesis.speak(u);
  };
  if (speechSynthesis.getVoices().length === 0) {
    speechSynthesis.addEventListener("voiceschanged", speak, { once: true });
  } else {
    speak();
  }
}

function sayWord(word) {
  if (pageDate) {
    stopAll();
    const a = new Audio(`${prefix}audio/${pageDate}/v/${slug(word)}.mp3`);
    sayAudio = a;
    let fellBack = false;
    const fallback = () => {
      if (fellBack) return;
      fellBack = true;
      speakFallback(word);
    };
    a.addEventListener("error", fallback, { once: true });
    a.play().catch(fallback);
  } else {
    speakFallback(word);
  }
}

document.addEventListener("click", (e) => {
  const say = e.target.closest(".say");
  if (say) { sayWord(say.dataset.word); return; }

  const btn = e.target.closest(".listen");
  if (!btn || !btn.dataset.audio) return;

  if (btn === activeBtn) {           // same button: plain toggle
    if (player.paused) { stopExtras(); player.play().catch(() => {}); }
    else player.pause();
    return;
  }
  stopAll();                         // switch to another story/digest
  setGlyph(activeBtn, false);
  activeBtn = btn;
  player.src = btn.dataset.audio;
  player.hidden = false;
  player.play().catch(() => {});
});

// ---- select/long-press ANY word -> small button -> hear it --------------
const selBtn = document.createElement("button");
selBtn.id = "speak-selection";
selBtn.textContent = "\u{1F508} say it";
selBtn.hidden = true;
document.body.appendChild(selBtn);

selBtn.addEventListener("pointerdown", (e) => e.preventDefault()); // keep the selection
selBtn.addEventListener("click", () => {
  if (selBtn.dataset.word) speakFallback(selBtn.dataset.word);
  selBtn.hidden = true;
});

document.addEventListener("selectionchange", () => {
  const sel = window.getSelection();
  const text = sel.toString().trim();
  if (!text || text.length > 80 || sel.rangeCount === 0) {
    selBtn.hidden = true;
    return;
  }
  const rect = sel.getRangeAt(0).getBoundingClientRect();
  selBtn.dataset.word = text;
  selBtn.style.top = window.scrollY + rect.bottom + 10 + "px";
  selBtn.style.left = Math.max(8, window.scrollX + rect.left) + "px";
  selBtn.hidden = false;
});
