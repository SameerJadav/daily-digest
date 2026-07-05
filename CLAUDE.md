# CLAUDE.md

Guide for Claude Code (claude.ai/code) in this repo.

Daily Digest: once-daily AI-written news digest. GitHub Actions cron fetch RSS, Gemini pick+write 5–7 stories, output static site on GitHub Pages. See `README.md` for run details.

## Scope — read before "completing" the product

`product.md` = big vision, not to-do. Current product = **deliberately narrow subset**. Gaps intentional — no close unless user asks. These in `product.md` but **intentionally not built**, no add unprompted:

- Full 5-layer story structure — digest use three sections (what happened / why it matters / what to watch next), not five. No separate "why it happened" or "historical context / parallel" layer.
- "genuine disagreement" section and "solutions" layer.
- Email delivery, accounts, onboarding, personalization, adaptive complexity, "I don't understand this" button — site static, anonymous, same for all (reader persona baked into prompts as "a reader in India").
- Spaced repetition / knowledge library / knowledge checks — only memory features = "Since you read" follow-ups and last-14-day vocab de-dup.
- Any notifications, any second daily touchpoint.

What *is* built, stays: hard close, plain-language "16-year-old test", `vocab` ("Words to know" + pronunciation), source attribution, once-a-day finite page. Doubt if feature belongs → ask, no build.

## Commands

```sh
GEMINI_API_KEY=... uv run digest.py            # full pipeline: fetch → select → read → write → render
GEMINI_API_KEY=... uv run digest.py --if-missing  # same, but no-op if today's data/*.json exists
uv run digest.py render                        # re-render all HTML from data/*.json (no AI, no key)
uv run audio.py                                # (re)generate MP3s for the last 7 days into docs/audio/
```

`audio.py` has inline PEP-723 deps (CPU torch + kokoro), needs `espeak-ng` + `ffmpeg` on PATH. No test suite, linter, build step — `uv run` is whole toolchain.

## Architecture

**`data/YYYY-MM-DD.json` = single source of truth.** Every HTML page + MP3 *derived* from these. Never hand-edit HTML in `docs/` — overwritten on next render. Only AI pipeline writes `data/`; all else reads.

**Two-pass Gemini** (`digest.py`, `generate_day`): *select* pass clusters fetched articles, pick 5–7 topics with source ids; then full text fetched (`trafilatura`, best-effort) for those sources only; then *write* pass composes digest from grounded text. Both passes use JSON schema-constrained output (`SELECT_SCHEMA` / `WRITE_SCHEMA`). Model pinned in `MODEL` constant.

**Memory** (`load_memory`): past `data/*.json` feed prompts so model treats reader as returning — continuing stories = UPDATEs, closed ones = "Since you read" follow-ups (last 7 days), vocab from last 14 days skipped. `article_window` fetches only articles since last `generated_at` (12h floor, 48h cap) so nothing re-digested.

**Dates:** digest day computed in IST (`IST` constant); all else UTC.

**Two workflows.** `digest.yml` runs full AI pipeline on cron (three staggered fires, all `--if-missing` so exactly one generates — GitHub delays free crons 1–4h, hence early start). `render.yml` runs on pushes touching `digest.py`/`docs/`/`data/`, does HTML-only regen (no AI). Both run `audio.py`, then `digest.py render` a **second time** — audio must exist before render so listen buttons only show on pages whose MP3s actually made. Audio failure non-fatal (`|| echo ::warning::`).

### Editing the UI

- CSS/JS: edit `docs/style.css` / `docs/app.js` directly — served as-is, AI never touches.
- HTML structure: edit template strings in `digest.py` (`PAGE`, `render_story`, `render_digest_page`, `render_all`), then `uv run digest.py render`.

## Gotchas

- `slug()` in **both** `audio.py` and `docs/app.js`, must stay identical — maps vocab term to MP3 filename; mismatch silently breaks pronunciation audio.
- `docs/app.js` plays pre-gen MP3s via native `<audio>`; `speechSynthesis` only fallback for pruned days (>7 days old) and select-any-word button.
- `dbg()` output → stderr (Actions log) only, never site — keep verbose; only way to debug scheduled runs after the fact.
- Feeds in `feeds.txt`, one `Name URL` per line (`#` comments). Pipeline aborts if fewer than 10 articles fetched.