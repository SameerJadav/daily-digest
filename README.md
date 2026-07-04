# Daily Digest

Once-daily AI news digest. A GitHub Actions cron job fetches every article from the RSS
feeds in `feeds.txt`, Gemini selects and writes the 5–7 stories that matter, and the result
is published as a static page on GitHub Pages. One page a day. It ends. See `product.md`
for the full product vision.

## How it works

- `feeds.txt` — one RSS URL per line. Edit this to add or remove sources.
- `digest.py` — the whole pipeline: fetch → Gemini (`gemini-2.5-flash`, free tier) → HTML.
- `.github/workflows/digest.yml` — runs daily at 00:30 UTC (06:00 IST), commits `docs/`.
- `docs/` — GitHub Pages root. `index.html` is today's digest; `docs/archive/` keeps every day.

## Setup (one time)

1. Create a free API key at <https://aistudio.google.com> and add it as a repo secret
   named `GEMINI_API_KEY` (Settings → Secrets and variables → Actions).
2. Enable Pages: Settings → Pages → deploy from branch `main`, folder `/docs`.

## Run locally

```sh
GEMINI_API_KEY=... uv run digest.py
```

Note: GitHub disables scheduled workflows after 60 days without repo activity; the daily
digest commit itself keeps this alive.
