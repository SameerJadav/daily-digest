# Daily Digest

Once-daily AI news digest. A GitHub Actions cron job fetches every article from the RSS
feeds in `feeds.txt`, Gemini selects and writes the 5–7 stories that matter, and the result
is published as a static page on GitHub Pages. One page a day. It ends. See `product.md`
for the full product vision.

Live at <https://sameerjadav.github.io/daily-digest/>.

## How it works

- `feeds.txt` — one feed per line (`Name URL`). Edit this to add or remove sources.
- `digest.py` — fetch → Gemini (`gemini-3.5-flash`, free tier) → `data/YYYY-MM-DD.json` → HTML.
- `data/` — the digest content, one JSON per day. HTML is always derived from these.
- `docs/` — GitHub Pages root. `index.html` is today; `docs/archive/` has every day + an index.
- `.github/workflows/digest.yml` — full pipeline daily at 00:30 UTC (06:00 IST).
- `.github/workflows/render.yml` — re-renders HTML from `data/` (no AI) whenever
  `digest.py` is pushed, or manually via workflow dispatch.

## Changing the UI (no AI involved)

- **CSS**: edit `docs/style.css`, push. Done — it's served as-is.
- **HTML structure**: edit the templates in `digest.py`, push — the render workflow
  regenerates every page from `data/`. Or locally: `uv run digest.py render`.

## Run locally

```sh
GEMINI_API_KEY=... uv run digest.py   # full pipeline
uv run digest.py render               # re-render only, no key needed
```

Note: GitHub disables scheduled workflows after 60 days without repo activity; the daily
digest commit itself keeps this alive.
