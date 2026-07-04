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
"""Generate spoken audio for the latest digest into docs/audio/ (gitignored, deployed
via the Pages artifact). Voice: Kokoro-82M af_heart (female). Failure here must never
block publishing — workflows run this step non-fatally.

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


def slug(term: str) -> str:
    # must match slug() in docs/app.js
    return re.sub(r"[^a-z0-9]+", "-", term.lower()).strip("-")


def main() -> None:
    days = sorted((ROOT / "data").glob("*.json"))
    if not days:
        print("no data/*.json; nothing to voice")
        return
    day = json.loads(days[-1].read_text())

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

    shutil.rmtree(AUDIO, ignore_errors=True)
    (AUDIO / "v").mkdir(parents=True)

    wavs = [synth(f"Daily Digest, {day['date_label']}. {day['day_summary']}")]
    for i, s in enumerate(day["stories"]):
        text = (
            f"{s['headline']}. What happened. {s['what_happened']} "
            f"Why it matters. {s['why_it_matters']} "
            f"What to watch next. {s['what_to_watch_next']}"
        )
        wav = synth(text)
        encode(wav, AUDIO / f"s{i}.mp3")
        wavs.append(wav)
        print(f"s{i}.mp3 ok", file=sys.stderr)
        for v in s.get("vocab", []):
            encode(synth(v["term"]), AUDIO / "v" / f"{slug(v['term'])}.mp3")

    # one continuous file for "listen to today's digest" — a single <audio> src
    # never hits mobile autoplay policies the way a JS playlist does
    gap = np.zeros(int(0.8 * 24000), dtype=wavs[0].dtype)
    encode(np.concatenate([x for w in wavs for x in (w, gap)][:-1]), AUDIO / "full.mp3")

    print(f"voiced {len(day['stories'])} stories + full.mp3 for {day['date']}")


if __name__ == "__main__":
    main()
