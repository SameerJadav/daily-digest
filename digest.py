"""Fetch RSS feeds, have Gemini write a once-daily digest, render static HTML into docs/.

Usage:
  uv run digest.py               # full pipeline: fetch -> select -> read articles -> write -> render
  uv run digest.py --if-missing  # same, but exit quietly if today's digest already exists
  uv run digest.py render        # re-render every page from data/*.json (no AI, no API key)

The digest content for each day lives in data/YYYY-MM-DD.json; HTML in docs/ is always
derived from it. To change the UI, edit docs/style.css / docs/app.js (take effect on push)
or the templates below (then run `digest.py render`).
"""

import calendar
import html
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser

ROOT = Path(__file__).parent
DATA = ROOT / "data"
DOCS = ROOT / "docs"
ARCHIVE = DOCS / "archive"
IST = timezone(timedelta(hours=5, minutes=30))
MODEL = "gemini-3.5-flash"


# ---------------------------------------------------------------- fetch


def fetch_entries() -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    feeds = [
        line.split()
        for line in (ROOT / "feeds.txt").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    entries = []
    for parts in feeds:
        url = parts[-1]
        feed = feedparser.parse(url)
        if feed.bozo and not feed.entries:
            print(f"warning: could not parse {url}", file=sys.stderr)
            continue
        outlet = (
            parts[0].replace("-", " ")
            if len(parts) > 1
            else feed.feed.get("title", url)
        )
        for e in feed.entries:
            parsed = e.get("published_parsed") or e.get("updated_parsed")
            if not parsed:
                continue
            published = datetime.fromtimestamp(calendar.timegm(parsed), timezone.utc)
            if published < cutoff:
                continue
            summary = html.unescape(re.sub(r"<[^>]+>", " ", e.get("summary", "")))
            entries.append(
                {
                    "outlet": outlet,
                    "title": e.get("title", "").strip(),
                    "url": e.get("link", ""),
                    "summary": " ".join(summary.split())[:500],
                }
            )
    return entries


def fetch_fulltext(urls: list[str]) -> dict[str, str]:
    """Full article text for grounding, best effort — paywalled/broken pages just drop out."""
    import trafilatura

    texts = {}
    for url in urls:
        try:
            page = trafilatura.fetch_url(url)
            text = trafilatura.extract(page) if page else None
            if text:
                texts[url] = text[:4000]
        except Exception as e:
            print(f"warning: fulltext failed for {url}: {e}", file=sys.stderr)
    return texts


# ---------------------------------------------------------------- memory


def load_memory(exclude_date: str) -> dict:
    """What the reader has already seen, from past days' data files."""
    days = [
        json.loads(p.read_text())
        for p in sorted(DATA.glob("*.json"))
        if p.stem != exclude_date
    ]
    covered = [
        f"[{d['date']}] {s['headline']} — was watching: {s['what_to_watch_next'][:150]}"
        for d in days[-7:]
        for s in d["stories"]
    ]
    vocab = sorted(
        {
            v["term"]
            for d in days[-14:]
            for s in d["stories"]
            for v in s.get("vocab", [])
        }
    )
    return {"covered": covered, "vocab": vocab}


# ---------------------------------------------------------------- gemini

SELECT_SCHEMA = {
    "type": "object",
    "properties": {
        "stories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "A few words naming the story.",
                    },
                    "source_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Ids of the up-to-4 most substantial articles about this story.",
                    },
                },
                "required": ["topic", "source_ids"],
            },
        },
    },
    "required": ["stories"],
}

SELECT_PROMPT = """\
You are selecting stories for a once-daily news digest for a curious, intelligent reader \
in India who wants global and Indian news with as little bias as possible.

Below is every article published in the last 24 hours by a geographically diverse set of \
outlets, as a numbered list. Cluster articles about the same event and select the 5 to 7 \
stories that matter most.

Selection rules:
- Prefer stories with concrete real-world consequences over outrage, gossip, or horse-race politics.
- Include at least one story about India and at least one story from a region or topic that \
mainstream feeds under-cover.
- The reader already followed these stories on previous days; re-select one only if there is \
a genuine new development, not for a repeat of what they already know:
{covered}
- For each selected story, give the ids of the up-to-4 most substantial articles covering it.

Articles:
{articles}
"""

WRITE_SCHEMA = {
    "type": "object",
    "properties": {
        "day_summary": {
            "type": "string",
            "description": "One or two plain sentences describing the day in news.",
        },
        "stories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "headline": {"type": "string"},
                    "what_happened": {"type": "string"},
                    "why_it_matters": {"type": "string"},
                    "what_to_watch_next": {"type": "string"},
                    "source_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Article ids from the input this story draws on.",
                    },
                    "vocab": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "term": {"type": "string"},
                                "say": {
                                    "type": "string",
                                    "description": "Simple phonetic respelling with the stressed syllable in capitals, e.g. sovereignty -> SOV-rin-tee.",
                                },
                                "meaning": {
                                    "type": "string",
                                    "description": "One or two plain sentences: what the term is, and what it refers to in this story.",
                                },
                            },
                            "required": ["term", "say", "meaning"],
                        },
                    },
                },
                "required": [
                    "headline",
                    "what_happened",
                    "why_it_matters",
                    "what_to_watch_next",
                    "source_ids",
                    "vocab",
                ],
            },
        },
        "follow_ups": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "about": {
                        "type": "string",
                        "description": "A few words naming the previously covered story this updates.",
                    },
                    "update": {
                        "type": "string",
                        "description": "One or two plain sentences on what has happened since.",
                    },
                },
                "required": ["about", "update"],
            },
        },
    },
    "required": ["day_summary", "stories", "follow_ups"],
}

WRITE_PROMPT = """\
You are the writer of a once-daily news digest for a curious, intelligent reader in India \
who wants global and Indian news with as little bias as possible. The reader's goal is to \
understand and learn, not just stay aware.

Today's selected stories are below, each with its source articles. Where full article text \
is present, write strictly from it; where only an RSS summary is present, stick to what it \
supports and clearly attribute anything beyond it.

Writing rules (non-negotiable):
- Plain language. A bright 16-year-old with no background knowledge must be able to follow it. \
No jargon or acronym without an immediate plain-language explanation.
- Neutral attribution: say who claims what ("the ministry says", "Reuters reports", "witnesses \
told the BBC"). Never present a contested claim as settled fact.
- Where outlets disagree or facts are still uncertain, say so explicitly.
- Short sentences. Active voice. Concrete nouns. Write what things ARE, not just what they do.
- Full context, always: never assume the reader knows the backstory. Include the one or two \
sentences of background a first-time reader needs to genuinely understand the story, not just \
be aware of it.
- Each section 2-5 sentences. "What to watch next" names 1-3 specific future signposts \
(a date, a decision, an event) so the reader knows when they'll learn more.
- source_ids must be the ids of the actual input articles the story draws on. Never invent ids.
- vocab: for each story, list 2-6 terms a bright 16-year-old might not know or might mispronounce: \
jargon, technical or financial terms, institutions (what they are and what power they have), \
places, treaties, titles. For each give "say", a simple phonetic respelling with the stressed \
syllable in capitals (e.g. Ayatollah -> eye-uh-TOH-luh), and "meaning", one or two plain sentences \
explaining the term as used in this story.

The reader has been following this digest daily. Stories they already read, and what those \
stories said to watch for:
{covered}

Memory rules:
- If a today's story continues one of those, write it as an UPDATE: lead with what is new, \
recap the old story in at most one sentence, and explicitly connect to what they were watching for.
- follow_ups: one or two sentence updates on previously covered stories that had a real \
development in today's articles but are NOT among today's selected stories. Only report \
developments supported by today's articles. Empty list if none.
- Do not repeat these vocab terms the reader learned recently (pick new ones instead): {vocab}

Today's selected stories and source articles:
{stories_block}
"""


def _call(client, **kwargs):
    for attempt in range(4):
        try:
            return client.models.generate_content(**kwargs)
        except (
            Exception
        ) as e:  # ponytail: blanket retry; free-tier 429s and 5xx look the same to us
            if attempt == 3:
                raise
            print(
                f"gemini attempt {attempt + 1} failed, retrying in 75s: {e}",
                file=sys.stderr,
            )
            time.sleep(75)


def generate_day(entries: list[dict], memory: dict, today: datetime) -> dict:
    from google import genai
    from google.genai import types

    client = genai.Client()
    covered = "\n".join(memory["covered"]) or "(nothing yet — this is the first digest)"

    articles = "\n".join(
        f"[{i}] ({e['outlet']}) {e['title']} — {e['summary']}"
        for i, e in enumerate(entries)
    )
    selection = json.loads(
        _call(
            client,
            model=MODEL,
            contents=SELECT_PROMPT.format(covered=covered, articles=articles),
            config=types.GenerateContentConfig(
                response_mime_type="application/json", response_schema=SELECT_SCHEMA
            ),
        ).text
    )

    chosen = [
        (
            s["topic"],
            [i for i in dict.fromkeys(s["source_ids"]) if 0 <= i < len(entries)][:4],
        )
        for s in selection["stories"]
    ]
    texts = fetch_fulltext([entries[i]["url"] for _, ids in chosen for i in ids])
    print(
        f"selected {len(chosen)} stories; full text for "
        f"{sum(1 for _, ids in chosen for i in ids if entries[i]['url'] in texts)}"
        f"/{sum(len(ids) for _, ids in chosen)} articles"
    )

    blocks = []
    for topic, ids in chosen:
        parts = [f"## {topic}"]
        for i in ids:
            e = entries[i]
            body = texts.get(e["url"]) or f"(RSS summary only) {e['summary']}"
            parts.append(f"[{i}] ({e['outlet']}) {e['title']}\n{body}")
        blocks.append("\n\n".join(parts))
    stories_block = "\n\n----\n\n".join(blocks)

    digest = json.loads(
        _call(
            client,
            model=MODEL,
            contents=WRITE_PROMPT.format(
                covered=covered,
                vocab=", ".join(memory["vocab"]) or "(none yet)",
                stories_block=stories_block,
            ),
            config=types.GenerateContentConfig(
                response_mime_type="application/json", response_schema=WRITE_SCHEMA
            ),
        ).text
    )

    stories = []
    for s in digest["stories"]:
        sources = [
            {"outlet": entries[i]["outlet"], "url": entries[i]["url"]}
            for i in dict.fromkeys(s["source_ids"])
            if 0 <= i < len(entries)
        ]
        stories.append(
            {
                "headline": s["headline"],
                "what_happened": s["what_happened"],
                "why_it_matters": s["why_it_matters"],
                "what_to_watch_next": s["what_to_watch_next"],
                "vocab": s["vocab"],
                "sources": sources,
            }
        )
    return {
        "date": f"{today:%Y-%m-%d}",
        "date_label": today.strftime("%A, %d %B %Y"),
        "day_summary": digest["day_summary"],
        "stories": stories,
        "follow_ups": digest["follow_ups"],
    }


# ---------------------------------------------------------------- render

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#faf8f4">
<title>{title}</title>
<link rel="stylesheet" href="{prefix}style.css">
<link rel="manifest" href="{prefix}manifest.json">
<link rel="icon" href="{prefix}icon-192.png">
<link rel="apple-touch-icon" href="{prefix}icon-192.png">
<script src="{prefix}app.js" defer></script>
</head>
<body data-prefix="{prefix}">
{body}
<footer>{footer}</footer>
</body>
</html>
"""


def render_vocab(vocab: list[dict]) -> str:
    if not vocab:
        return ""
    esc = html.escape
    items = "".join(
        f"""<dt><span class="term">{esc(v["term"])}</span>
<button class="say" data-word="{esc(v["term"], quote=True)}" aria-label="pronounce {esc(v["term"], quote=True)}"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11 4.702a.705.705 0 0 0-1.203-.498L6.413 7.587A1.4 1.4 0 0 1 5.416 8H3a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2.416a1.4 1.4 0 0 1 .997.413l3.383 3.384A.705.705 0 0 0 11 19.298z"/><path d="M16 9a5 5 0 0 1 0 6"/><path d="M19.364 18.364a9 9 0 0 0 0-12.728"/></svg></button>
<span class="pron">{esc(v["say"])}</span></dt>
<dd>{esc(v["meaning"])}</dd>"""
        for v in vocab
    )
    return f'<aside class="vocab"><h3>Words to know</h3><dl>{items}</dl></aside>'


def render_story(story: dict, i: int, audio: bool) -> str:
    esc = html.escape
    sources = "".join(
        f'<a href="{esc(s["url"], quote=True)}" target="_blank" rel="noopener">{esc(s["outlet"])}</a>'
        for s in story["sources"]
    )
    listen = (
        (
            f'<button class="listen" data-audio="audio/s{i}.mp3">'
            f'<svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">'
            f'<path d="M5 5a2 2 0 0 1 3.008-1.728l11.997 6.998a2 2 0 0 1 .003 3.458l-12 7A2 2 0 0 1 5 19z"/></svg> Listen</button>'
        )
        if audio
        else ""
    )
    return f"""
<article>
<h2>{esc(story["headline"])}</h2>
{listen}
<h3>What happened</h3><p>{esc(story["what_happened"])}</p>
<h3>Why it matters</h3><p>{esc(story["why_it_matters"])}</p>
<h3>What to watch next</h3><p>{esc(story["what_to_watch_next"])}</p>
{render_vocab(story.get("vocab", []))}
<p class="sources">{sources}</p>
</article>"""


def render_digest_page(day: dict, prefix: str, footer: str, audio: bool = False) -> str:
    esc = html.escape
    follow = ""
    if day.get("follow_ups"):
        items = "".join(
            f"<p><strong>{esc(f['about'])}</strong> — {esc(f['update'])}</p>"
            for f in day["follow_ups"]
        )
        follow = f'<section class="follow-ups"><h3>Since you read</h3>{items}</section>'
    listen_all = (
        (
            '<button id="listen-all" class="listen" data-audio="audio/full.mp3">'
            '<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">'
            '<path d="M5 5a2 2 0 0 1 3.008-1.728l11.997 6.998a2 2 0 0 1 .003 3.458l-12 7A2 2 0 0 1 5 19z"/></svg> Listen to today\'s digest</button>'
        )
        if audio
        else ""
    )
    body = f"""<header>
<h1>Daily Digest</h1>
<div class="date">{esc(day["date_label"])}</div>
<p class="day-summary">{esc(day["day_summary"])}</p>
{listen_all}
</header>
{"".join(render_story(s, i, audio) for i, s in enumerate(day["stories"]))}
{follow}
<p class="close">That's your digest. You're informed. Come back tomorrow.</p>"""
    return PAGE.format(
        title=f"Digest — {esc(day['date_label'])}",
        prefix=prefix,
        body=body,
        footer=footer,
    )


def render_all() -> None:
    days = sorted(
        (json.loads(p.read_text()) for p in DATA.glob("*.json")),
        key=lambda d: d["date"],
        reverse=True,
    )
    if not days:
        print("no data/*.json to render; nothing to do")
        return
    ARCHIVE.mkdir(parents=True, exist_ok=True)

    for day in days:
        (ARCHIVE / f"{day['date']}.html").write_text(
            render_digest_page(
                day, "../", '<a href="./">All digests</a> <a href="../">Latest</a>'
            )
        )
    (DOCS / "index.html").write_text(
        render_digest_page(
            days[0], "", '<a href="archive/">All past digests</a>', audio=True
        )
    )

    items = "".join(
        f"""<li><a href="{day["date"]}.html">{html.escape(day["date_label"])}</a>
<span class="summary">{html.escape(day["day_summary"])}</span></li>"""
        for day in days
    )
    (ARCHIVE / "index.html").write_text(
        PAGE.format(
            title="Daily Digest — Archive",
            prefix="../",
            body=f'<header><h1>All digests</h1></header>\n<ul class="archive-list">{items}</ul>',
            footer='<a href="../">Latest digest</a>',
        )
    )
    print(f"rendered {len(days)} day(s) into docs/")


def main() -> None:
    if sys.argv[1:] == ["render"]:
        render_all()
        return
    today = datetime.now(IST)
    if "--if-missing" in sys.argv and (DATA / f"{today:%Y-%m-%d}.json").exists():
        print("today's digest already exists; nothing to do")
        return
    entries = fetch_entries()
    print(f"{len(entries)} articles from the last 24h")
    if len(entries) < 10:
        sys.exit("too few articles — check feeds.txt")
    memory = load_memory(exclude_date=f"{today:%Y-%m-%d}")
    day = generate_day(entries, memory, today)
    if not day["stories"]:
        sys.exit("model returned no stories")
    DATA.mkdir(exist_ok=True)
    (DATA / f"{day['date']}.json").write_text(
        json.dumps(day, ensure_ascii=False, indent=1)
    )
    render_all()


if __name__ == "__main__":
    main()
