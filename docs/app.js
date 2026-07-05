// On-demand TTS: Kokoro-82M running in the browser (voice af_heart, female).
// The model (~90 MB) downloads on first listen and is cached by the browser after that.
// Sentences are synthesized one by one and scheduled gaplessly through WebAudio, so
// playback never needs the programmatic <audio>.play() that mobile autoplay policies block.
// Browser speechSynthesis is only the fallback if the model fails to load.
// Edit freely — the AI pipeline never touches this file.

const KOKORO_URL = "https://cdn.jsdelivr.net/npm/kokoro-js@1.2.1/+esm";
const MODEL_ID = "onnx-community/Kokoro-82M-v1.0-ONNX";
const VOICE = "af_heart";

// ---- status bar -------------------------------------------------------
const bar = document.createElement("div");
bar.id = "tts-bar";
bar.hidden = true;
bar.innerHTML =
  '<button id="tts-toggle" aria-label="pause or resume">&#10074;&#10074;</button>' +
  '<span id="tts-status"></span>' +
  '<button id="tts-stop" aria-label="stop">&#10005;</button>';
document.body.appendChild(bar);
const statusEl = bar.querySelector("#tts-status");
const toggleEl = bar.querySelector("#tts-toggle");

function setStatus(text) { statusEl.textContent = text; bar.hidden = !text; }

// ---- kokoro loading ---------------------------------------------------
let ttsPromise = null;
function loadTTS() {
  ttsPromise ??= import(KOKORO_URL).then(({ KokoroTTS }) =>
    KokoroTTS.from_pretrained(MODEL_ID, { dtype: "q8", device: "wasm" })
  ).catch((e) => { ttsPromise = null; throw e; });
  return ttsPromise;
}

// ---- playback ---------------------------------------------------------
let ctx = null;
let session = 0;       // bumped to cancel any in-flight read
let playhead = 0;
let liveSources = [];
let generating = false;

function stopAll() {
  session += 1;
  liveSources.forEach((s) => { try { s.stop(); } catch {} });
  liveSources = [];
  setStatus("");
  if (ctx && ctx.state === "suspended") ctx.resume();
  toggleEl.textContent = "❚❚";
}

function schedule(raw, mySession) {
  if (mySession !== session) return;
  const buf = ctx.createBuffer(1, raw.audio.length, raw.sampling_rate);
  buf.copyToChannel(raw.audio, 0);
  const src = ctx.createBufferSource();
  src.buffer = buf;
  src.connect(ctx.destination);
  const at = Math.max(playhead, ctx.currentTime + 0.05);
  src.start(at);
  playhead = at + buf.duration;
  liveSources.push(src);
  src.onended = () => {
    liveSources = liveSources.filter((s) => s !== src);
    if (!liveSources.length && !generating && mySession === session) setStatus("");
  };
}

async function read(text, label) {
  // must be called from a user gesture so the AudioContext is allowed to start
  ctx ??= new (window.AudioContext || window.webkitAudioContext)();
  ctx.resume();
  stopAll();
  const mySession = session;
  setStatus(ttsPromise ? label : "Downloading voice (first time only, ~90 MB)…");
  let tts;
  try {
    tts = await loadTTS();
  } catch (e) {
    setStatus("");
    speakFallback(text);
    return;
  }
  if (mySession !== session) return;
  setStatus(label);
  playhead = ctx.currentTime + 0.1;
  generating = true;
  const sentences = text.match(/[^.!?\n]+[.!?]+["')\]]?|[^.!?\n]+/g) || [text];
  for (const sentence of sentences) {
    if (mySession !== session) { generating = false; return; }
    const t = sentence.trim();
    if (!t) continue;
    try {
      const raw = await tts.generate(t, { voice: VOICE });
      schedule(raw, mySession);
    } catch (e) { /* skip a bad sentence, keep reading */ }
  }
  generating = false;
  if (!liveSources.length && mySession === session) setStatus("");
}

toggleEl.addEventListener("click", () => {
  if (!ctx) return;
  if (ctx.state === "running") { ctx.suspend(); toggleEl.textContent = "▶"; }
  else { ctx.resume(); toggleEl.textContent = "❚❚"; }
});
bar.querySelector("#tts-stop").addEventListener("click", stopAll);

// ---- what to read -----------------------------------------------------
function storyText(article) {
  const parts = [article.querySelector("h2").textContent + "."];
  article.querySelectorAll("h3").forEach((h) => {
    if (h.closest(".vocab")) return;
    const p = h.nextElementSibling;
    if (p && p.tagName === "P") parts.push(h.textContent + ". " + p.textContent);
  });
  return parts.join(" ");
}

function digestText() {
  const parts = [];
  const date = document.querySelector(".date");
  const summary = document.querySelector(".day-summary");
  parts.push("Daily Digest, " + (date ? date.textContent : "") + ".");
  if (summary) parts.push(summary.textContent);
  document.querySelectorAll("article").forEach((a, i) => {
    parts.push(`Story ${i + 1}. ` + storyText(a));
  });
  const follow = document.querySelector(".follow-ups");
  if (follow) parts.push("Since you read. " + follow.textContent);
  return parts.join("\n");
}

function speakFallback(text) {
  // browser TTS, prefer a female English voice
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  const en = speechSynthesis.getVoices().filter((v) => v.lang.startsWith("en"));
  u.voice =
    en.find((v) => /female|woman|zira|aria|jenny|neerja|heera|veena|libby|sonia/i.test(v.name)) ||
    en[0] || null;
  u.lang = "en-IN";
  u.rate = 0.85;
  speechSynthesis.speak(u);
}

document.addEventListener("click", (e) => {
  const say = e.target.closest(".say");
  if (say) { read(say.dataset.word, say.dataset.word); return; }
  if (e.target.closest("#listen-all")) { read(digestText(), "Reading the digest…"); return; }
  const listen = e.target.closest(".listen");
  if (listen) {
    const article = listen.closest("article");
    if (article) read(storyText(article), article.querySelector("h2").textContent);
  }
});

// ---- select/long-press ANY word -> small button -> hear it ------------
const btn = document.createElement("button");
btn.id = "speak-selection";
btn.textContent = "\u{1F508} say it";
btn.hidden = true;
document.body.appendChild(btn);

btn.addEventListener("pointerdown", (e) => e.preventDefault()); // keep the selection
btn.addEventListener("click", () => {
  if (btn.dataset.word) read(btn.dataset.word, btn.dataset.word);
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
