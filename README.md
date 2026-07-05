# Daily Digest

Once-daily AI news digest. A GitHub Actions cron job fetches every article from the RSS
feeds in `feeds.txt`, Gemini selects and writes the 5–7 stories that matter, and the result
is published as a static page on GitHub Pages. One page a day. It ends. See `product.md`
for the full product vision.

Live at <https://sameerjadav.github.io/daily-digest/>.

## How it works

- `feeds.txt` — one feed per line (`Name URL`). Edit this to add or remove sources.
- `digest.py` — fetch articles since the last digest → Gemini selects stories → full
  article text fetched for grounding → Gemini writes → `data/YYYY-MM-DD.json` → HTML.
  The model remembers the last 7 days (continuing stories become updates, closed ones
  become "Since you read" follow-ups) and skips vocab explained in the last 14 days.
- `data/` — the digest content, one JSON per day. HTML is always derived from these.
- `docs/` — GitHub Pages root. `index.html` is today; `docs/archive/` has every day + an index.
- Reading aloud is on-demand in the browser: `docs/app.js` runs Kokoro-82M (voice
  `af_heart`) via kokoro-js; the model downloads on first listen (~90 MB) and is cached.
- `.github/workflows/digest.yml` — daily pipeline. Cron fires at 21:47 UTC with two
  backups (23:17, 00:47); scheduled runs are `--if-missing`, so exactly one generates.
  GitHub delays free-tier crons 1–4 h, which is why the schedule starts that early.
- `.github/workflows/render.yml` — re-renders HTML from `data/` (no AI) whenever
  `digest.py`, `docs/`, or `data/` change, or manually via workflow dispatch.

## Changing the UI (no AI involved)

- **CSS / JS**: edit `docs/style.css` or `docs/app.js`, push. Served as-is.
- **HTML structure**: edit the templates in `digest.py`, push — the render workflow
  regenerates every page from `data/`. Or locally: `uv run digest.py render`.

## Debugging a bad run

Open the run in Actions and read the `[debug]` lines: per-feed article counts, the
article window, what memory was fed in, selection topics, full-text hit rate, and the
written stories/follow-ups. None of this appears on the site.

Known-transient: Pages deployments sometimes fail with "Deployment failed, try again
later" — the deploy job retries once automatically, and the backup crons re-deploy.

## Run locally

```sh
GEMINI_API_KEY=... uv run digest.py   # full pipeline
uv run digest.py render               # re-render only, no key needed
```

Note: GitHub disables scheduled workflows after 60 days without repo activity; the daily
digest commit itself keeps this alive.
