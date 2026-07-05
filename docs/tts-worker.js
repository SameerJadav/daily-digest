// Kokoro TTS in a Web Worker: all model loading and synthesis happens on this
// thread, so the page never janks. Audio chunks stream back as transferable
// Float32Arrays. Edit freely — the AI pipeline never touches this file.

const KOKORO_URL = "https://cdn.jsdelivr.net/npm/kokoro-js@1.2.1/+esm";
const MODEL_ID = "onnx-community/Kokoro-82M-v1.0-ONNX";
const VOICE = "af_heart";

let ttsPromise = null;
let current = 0; // latest request id; anything older is cancelled

function load() {
  ttsPromise ??= import(KOKORO_URL)
    .then(({ KokoroTTS }) =>
      KokoroTTS.from_pretrained(MODEL_ID, { dtype: "q8", device: "wasm" })
    )
    .catch((e) => {
      ttsPromise = null;
      throw e;
    });
  return ttsPromise;
}

self.onmessage = async (e) => {
  const { id, text } = e.data;
  current = id;
  try {
    const loaded = !!ttsPromise;
    if (!loaded) postMessage({ id, type: "downloading" });
    const tts = await load();
    if (current !== id) return;
    postMessage({ id, type: "start" });
    const sentences = text.match(/[^.!?\n]+[.!?]+["')\]]?|[^.!?\n]+/g) || [text];
    for (const sentence of sentences) {
      if (current !== id) return;
      const t = sentence.trim();
      if (!t) continue;
      const raw = await tts.generate(t, { voice: VOICE });
      if (current !== id) return;
      postMessage(
        { id, type: "chunk", audio: raw.audio, sr: raw.sampling_rate },
        [raw.audio.buffer]
      );
    }
    if (current === id) postMessage({ id, type: "done" });
  } catch (err) {
    postMessage({ id, type: "error", message: String(err) });
  }
};
