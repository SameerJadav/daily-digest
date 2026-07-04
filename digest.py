"""Fetch RSS feeds, have Gemini write a once-daily digest, render static HTML into docs/."""

import calendar
import html
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
from google import genai
from google.genai import types

ROOT = Path(__file__).parent
DOCS = ROOT / "docs"
ARCHIVE = DOCS / "archive"
IST = timezone(timedelta(hours=5, minutes=30))
MODEL = "gemini-2.5-flash"


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
        outlet = parts[0].replace("-", " ") if len(parts) > 1 else feed.feed.get("title", url)
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


SCHEMA = {
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
                        "description": "Article ids from the input list this story draws on.",
                    },
                },
                "required": [
                    "headline",
                    "what_happened",
                    "why_it_matters",
                    "what_to_watch_next",
                    "source_ids",
                ],
            },
        },
    },
    "required": ["day_summary", "stories"],
}

PROMPT = """\
You are the writer of a once-daily news digest for a curious, intelligent reader in India \
who wants global and Indian news with as little bias as possible.

Below is every article published in the last 24 hours by a geographically diverse set of \
outlets, as a numbered list. Cluster articles about the same event, select the 5 to 7 \
stories that matter most, and write the digest.

Selection rules:
- Prefer stories with concrete real-world consequences over outrage, gossip, or horse-race politics.
- Include at least one story about India and at least one story from a region or topic that \
mainstream feeds under-cover.
- Cover the event once, drawing on every outlet that reported it.

Writing rules (non-negotiable):
- Plain language. A bright 16-year-old with no background knowledge must be able to follow it. \
No jargon or acronym without an immediate plain-language explanation.
- Neutral attribution: say who claims what ("the ministry says", "Reuters reports", "witnesses \
told the BBC"). Never present a contested claim as settled fact.
- Where outlets disagree or facts are still uncertain, say so explicitly.
- Short sentences. Active voice. Concrete nouns. Write what things ARE, not just what they do.
- Each section 2-5 sentences. "What to watch next" names 1-3 specific future signposts \
(a date, a decision, an event) so the reader knows when they'll learn more.
- source_ids must be the ids of the actual input articles the story draws on. Never invent ids.

Articles:
{articles}
"""


def generate_digest(entries: list[dict]) -> dict:
    articles = "\n".join(
        f"[{i}] ({e['outlet']}) {e['title']} — {e['summary']}" for i, e in enumerate(entries)
    )
    client = genai.Client()
    resp = client.models.generate_content(
        model=MODEL,
        contents=PROMPT.format(articles=articles),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SCHEMA,
        ),
    )
    return json.loads(resp.text)


CSS = """\
:root { color-scheme: light dark; }
body { max-width: 42rem; margin: 0 auto; padding: 2rem 1.25rem 4rem;
  font-family: Georgia, 'Times New Roman', serif; line-height: 1.65; font-size: 1.05rem;
  background: #faf8f4; color: #1a1a1a; }
@media (prefers-color-scheme: dark) { body { background: #191919; color: #ddd; } a { color: #9cc3e5; } }
header { margin-bottom: 2.5rem; }
h1 { font-size: 1.4rem; margin: 0 0 .25rem; }
.date { color: #777; font-size: .95rem; }
.day-summary { font-style: italic; margin-top: 1rem; }
article { margin: 2.5rem 0; border-top: 1px solid #8884; padding-top: 1.5rem; }
h2 { font-size: 1.2rem; margin: 0 0 1rem; }
h3 { font-size: .8rem; text-transform: uppercase; letter-spacing: .08em; color: #877; margin: 1.2rem 0 .2rem; }
article p { margin: .2rem 0 0; }
.sources { font-size: .85rem; margin-top: 1rem; }
.sources a { margin-right: .75rem; }
.close { margin-top: 3.5rem; border-top: 1px solid #8884; padding-top: 2rem;
  text-align: center; font-style: italic; }
footer { margin-top: 3rem; font-size: .85rem; color: #777; }
footer a { color: inherit; margin-right: .75rem; }
"""


def render_story(story: dict, entries: list[dict]) -> str:
    esc = html.escape
    sources = "".join(
        f'<a href="{esc(entries[i]["url"], quote=True)}">{esc(entries[i]["outlet"])}</a>'
        for i in dict.fromkeys(story["source_ids"])
        if 0 <= i < len(entries)
    )
    return f"""
<article>
<h2>{esc(story["headline"])}</h2>
<h3>What happened</h3><p>{esc(story["what_happened"])}</p>
<h3>Why it matters</h3><p>{esc(story["why_it_matters"])}</p>
<h3>What to watch next</h3><p>{esc(story["what_to_watch_next"])}</p>
<p class="sources">{sources}</p>
</article>"""


def render_page(digest: dict, entries: list[dict], date_label: str, footer: str) -> str:
    stories = "".join(render_story(s, entries) for s in digest["stories"])
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Digest — {html.escape(date_label)}</title>
<style>{CSS}</style>
</head>
<body>
<header>
<h1>Daily Digest</h1>
<div class="date">{html.escape(date_label)}</div>
<p class="day-summary">{html.escape(digest["day_summary"])}</p>
</header>
{stories}
<p class="close">That's your digest. You're informed. Come back tomorrow.</p>
<footer>{footer}</footer>
</body>
</html>
"""


def main() -> None:
    entries = fetch_entries()
    print(f"{len(entries)} articles from the last 24h")
    if len(entries) < 10:
        sys.exit("too few articles — check feeds.txt")
    digest = generate_digest(entries)
    if not digest["stories"]:
        sys.exit("model returned no stories")

    today = datetime.now(IST)
    date_label = today.strftime("%A, %d %B %Y")
    ARCHIVE.mkdir(parents=True, exist_ok=True)

    (ARCHIVE / f"{today:%Y-%m-%d}.html").write_text(
        render_page(digest, entries, date_label, '<a href="../">← latest digest</a>')
    )
    past = sorted((p.stem for p in ARCHIVE.glob("*.html")), reverse=True)
    archive_links = "".join(f'<a href="archive/{d}.html">{d}</a>' for d in past)
    (DOCS / "index.html").write_text(
        render_page(digest, entries, date_label, f"Archive: {archive_links}")
    )
    print(f"wrote docs/index.html and docs/archive/{today:%Y-%m-%d}.html")


if __name__ == "__main__":
    main()
