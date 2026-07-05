// Listening UI. All Kokoro synthesis runs in tts-worker.js (a separate thread),
// so this page never blocks: the main thread only schedules finished audio
// chunks through WebAudio and updates buttons. Voice: af_heart (female).
// Model (~90 MB) downloads on first listen, then lives in the browser cache.
// Browser speechSynthesis is only the fallback if the worker/model fails.
// Edit freely — the AI pipeline never touches this file.

const prefix = document.body.dataset.prefix || "";

// ---- bottom bar (hidden until a listen action starts) ------------------
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

// ---- state --------------------------------------------------------------
let worker = null;
let workerBroken = false;
let reqId = 0;
let ctx = null;
let playhead = 0;
let liveSources = [];
let generationDone = false;
let activeBtn = null;
let activeText = "";

function ensureWorker() {
  if (worker || workerBroken) return worker;
  try {
    worker = new Worker(prefix + "tts-worker.js", { type: "module" });
  } catch {
    workerBroken = true;
    return null;
  }
  worker.onerror = () => {
    workerBroken = true;
    fallbackNow();
  };
  worker.onmessage = (e) => {
    const m = e.data;
    if (m.id !== reqId) return; // stale request
    if (m.type === "downloading") statusEl.textContent = "Downloading voice (first time only, ~90 MB)…";
    else if (m.type === "start") statusEl.textContent = labelText;
    else if (m.type === "chunk") schedule(m.audio, m.sr);
    else if (m.type === "done") {
      generationDone = true;
      if (!liveSources.length) finish();
    } else if (m.type === "error") fallbackNow();
  };
  return worker;
}

let labelText = "";

function schedule(audio, sr) {
  const buf = ctx.createBuffer(1, audio.length, sr);
  buf.copyToChannel(audio, 0);
  const src = ctx.createBufferSource();
  src.buffer = buf;
  src.connect(ctx.destination);
  const at = Math.max(playhead, ctx.currentTime + 0.05);
  src.start(at);
  playhead = at + buf.duration;
  liveSources.push(src);
  src.onended = () => {
    liveSources = liveSources.filter((s) => s !== src);
    if (!liveSources.length && generationDone) finish();
  };
}

function setBtn(btn, playing) {
  if (!btn || !btn.classList.contains("listen")) return;
  btn.classList.toggle("playing", playing);
  const base = btn.id === "listen-all" ? " Listen to this digest" : " Listen";
  btn.innerHTML = (playing ? "&#10074;&#10074;" : "&#9654;") + base;
}

function stopPlayback() {
  reqId += 1; // cancels in-flight worker generation and stale messages
  liveSources.forEach((s) => { try { s.stop(); } catch {} });
  liveSources = [];
  generationDone = false;
  if (ctx && ctx.state === "suspended") ctx.resume();
  toggleEl.innerHTML = "&#10074;&#10074;";
  setBtn(activeBtn, false);
  activeBtn = null;
}

function finish() {
  stopPlayback();
  bar.hidden = true;
}

function fallbackNow() {
  const text = activeText;
  finish();
  if (text) speakFallback(text);
}

function read(text, label, btn) {
  ctx ??= new (window.AudioContext || window.webkitAudioContext)();
  ctx.resume();
  stopPlayback();
  if (workerBroken || !ensureWorker()) { speakFallback(text); return; }
  activeBtn = btn || null;
  activeText = text;
  labelText = label;
  setBtn(activeBtn, true);
  statusEl.textContent = "Preparing voice…";
  bar.hidden = false;
  playhead = 0;
  worker.postMessage({ id: reqId, text });
}

function togglePause() {
  if (!ctx) return;
  if (ctx.state === "running") {
    ctx.suspend();
    toggleEl.innerHTML = "&#9654;";
    setBtn(activeBtn, false);
  } else {
    ctx.resume();
    toggleEl.innerHTML = "&#10074;&#10074;";
    setBtn(activeBtn, true);
  }
}

toggleEl.addEventListener("click", togglePause);
bar.querySelector("#tts-stop").addEventListener("click", finish);

// ---- what to read -------------------------------------------------------
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

// ---- clicks -------------------------------------------------------------
document.addEventListener("click", (e) => {
  const say = e.target.closest(".say");
  if (say) { read(say.dataset.word, say.dataset.word, null); return; }

  const listen = e.target.closest(".listen");
  if (!listen) return;

  if (listen === activeBtn) { togglePause(); return; } // same button = pause/resume

  if (listen.id === "listen-all") read(digestText(), "Reading the digest…", listen);
  else {
    const article = listen.closest("article");
    if (article) read(storyText(article), article.querySelector("h2").textContent, listen);
  }
});

// ---- select/long-press ANY word -> small button -> hear it --------------
const selBtn = document.createElement("button");
selBtn.id = "speak-selection";
selBtn.textContent = "\u{1F508} say it";
selBtn.hidden = true;
document.body.appendChild(selBtn);

selBtn.addEventListener("pointerdown", (e) => e.preventDefault()); // keep the selection
selBtn.addEventListener("click", () => {
  if (selBtn.dataset.word) read(selBtn.dataset.word, selBtn.dataset.word, null);
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
