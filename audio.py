# /// script
# requires-python = ">=3.12"
# dependencies = ["kokoro>=0.9", "soundfile", "numpy", "torch", "pip"]
#
# [[tool.uv.index]]
# name = "pytorch-cpu"
# url = "https://download.pytorch.org/whl/cpu"
# explicit = true
#
# [tool.uv.sources]
# torch = { index = "pytorch-cpu" }
# ///
"""Pre-generate spoken audio (Kokoro-82M, female voice af_heart) for the last 7 digest
days into docs/audio/YYYY-MM-DD/ — committed to git and served as plain MP3s.

Idempotent: only synthesizes days whose audio is missing, prunes days older than the
last 7, exits fast when there is nothing to do. Failure here must never block
publishing — workflows run this step non-fatally, and the second render pass only
puts listen buttons on pages whose audio actually exists.

  uv run audio.py
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent
AUDIO = ROOT / "docs" / "audio"
VOICE = "af_heart"
KEEP_DAYS = 7


def slug(term: str) -> str:
    # must match slug() in docs/app.js
    return re.sub(r"[^a-z0-9]+", "-", term.lower()).strip("-")


def main() -> None:
    days = sorted((ROOT / "data").glob("*.json"))[-KEEP_DAYS:]
    if not days:
        print("no data/*.json; nothing to voice")
        return

    AUDIO.mkdir(parents=True, exist_ok=True)
    keep = {p.stem for p in days}
    for d in AUDIO.iterdir():
        if d.is_dir() and d.name not in keep:
            shutil.rmtree(d)
            print(f"pruned audio/{d.name}")

    todo = [json.loads(p.read_text()) for p in days if not (AUDIO / p.stem / "full.mp3").exists()]
    if not todo:
        print("audio up to date")
        return

    import numpy as np
    import soundfile as sf
    from kokoro import KPipeline

    pipeline = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")

    def synth(text: str):
        return np.concatenate([audio for _, _, audio in pipeline(text, voice=VOICE)])

    def encode(wav, mp3: Path) -> None:
        with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
            sf.write(tmp.name, wav, 24000)
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-i", tmp.name,
                 "-ac", "1", "-b:a", "64k", str(mp3)],
                check=True,
            )

    for day in todo:
        out = AUDIO / day["date"]
        shutil.rmtree(out, ignore_errors=True)  # clear any partial previous attempt
        (out / "v").mkdir(parents=True)
        wavs = [synth(f"Daily Digest, {day['date_label']}. {day['day_summary']}")]
        for i, s in enumerate(day["stories"]):
            text = (
                f"{s['headline']}. What happened. {s['what_happened']} "
                f"Why it matters. {s['why_it_matters']} "
                f"What to watch next. {s['what_to_watch_next']}"
            )
            wav = synth(text)
            encode(wav, out / f"s{i}.mp3")
            wavs.append(wav)
            print(f"{day['date']}/s{i}.mp3 ok", file=sys.stderr)
            for v in s.get("vocab", []):
                encode(synth(v["term"]), out / "v" / f"{slug(v['term'])}.mp3")
        gap = np.zeros(int(0.8 * 24000), dtype=wavs[0].dtype)
        encode(np.concatenate([x for w in wavs for x in (w, gap)][:-1]), out / "full.mp3")
        print(f"voiced {day['date']} ({len(day['stories'])} stories)")


if __name__ == "__main__":
    main()
