"""Fetch RSS feeds, have Gemini write a once-daily digest, render static HTML into docs/.

Usage:
  uv run digest.py          # full pipeline: fetch -> Gemini -> save data/ -> render docs/
  uv run digest.py render   # re-render every page from data/*.json (no AI, no API key)

The digest content for each day lives in data/YYYY-MM-DD.json; HTML in docs/ is always
derived from it. To change the UI, edit docs/style.css (takes effect on push) or the
templates below (then run `digest.py render`).
"""

import calendar
import html
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser

ROOT = Path(__file__).parent
DATA = ROOT / "data"
DOCS = ROOT / "docs"
ARCHIVE = DOCS / "archive"
IST = timezone(timedelta(hours=5, minutes=30))
MODEL = "gemini-3.5-flash"


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


def generate_day(entries: list[dict]) -> dict:
    from google import genai
    from google.genai import types

    articles = "\n".join(
        f"[{i}] ({e['outlet']}) {e['title']} — {e['summary']}" for i, e in enumerate(entries)
    )
    client = genai.Client()
    resp = client.models.generate_content(
        model=MODEL,
        contents=PROMPT.format(articles=articles),
        config=types.GenerateContentConfig(
            # ponytail: no google_search tool — grounding has zero quota on the
            # keyless free tier (429s); re-add if billing is ever enabled
            response_mime_type="application/json",
            response_schema=SCHEMA,
        ),
    )
    digest = json.loads(resp.text)

    today = datetime.now(IST)
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
                "sources": sources,
            }
        )
    return {
        "date": f"{today:%Y-%m-%d}",
        "date_label": today.strftime("%A, %d %B %Y"),
        "day_summary": digest["day_summary"],
        "stories": stories,
    }


PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="{css}">
</head>
<body>
{body}
<footer>{footer}</footer>
</body>
</html>
"""


def render_story(story: dict) -> str:
    esc = html.escape
    sources = "".join(
        f'<a href="{esc(s["url"], quote=True)}" target="_blank" rel="noopener">{esc(s["outlet"])}</a>'
        for s in story["sources"]
    )
    return f"""
<article>
<h2>{esc(story["headline"])}</h2>
<h3>What happened</h3><p>{esc(story["what_happened"])}</p>
<h3>Why it matters</h3><p>{esc(story["why_it_matters"])}</p>
<h3>What to watch next</h3><p>{esc(story["what_to_watch_next"])}</p>
<p class="sources">{sources}</p>
</article>"""


def render_digest_page(day: dict, css: str, footer: str) -> str:
    body = f"""<header>
<h1>Daily Digest</h1>
<div class="date">{html.escape(day["date_label"])}</div>
<p class="day-summary">{html.escape(day["day_summary"])}</p>
</header>
{"".join(render_story(s) for s in day["stories"])}
<p class="close">That's your digest. You're informed. Come back tomorrow.</p>"""
    return PAGE.format(title=f"Digest — {html.escape(day['date_label'])}", css=css, body=body, footer=footer)


def render_all() -> None:
    days = sorted(
        (json.loads(p.read_text()) for p in DATA.glob("*.json")),
        key=lambda d: d["date"],
        reverse=True,
    )
    if not days:
        sys.exit("no data/*.json to render")
    ARCHIVE.mkdir(parents=True, exist_ok=True)

    for day in days:
        (ARCHIVE / f"{day['date']}.html").write_text(
            render_digest_page(day, "../style.css", '<a href="./">All digests</a> <a href="../">Latest</a>')
        )
    (DOCS / "index.html").write_text(
        render_digest_page(days[0], "style.css", '<a href="archive/">All past digests</a>')
    )

    items = "".join(
        f"""<li><a href="{day["date"]}.html">{html.escape(day["date_label"])}</a>
<span class="summary">{html.escape(day["day_summary"])}</span></li>"""
        for day in days
    )
    (ARCHIVE / "index.html").write_text(
        PAGE.format(
            title="Daily Digest — Archive",
            css="../style.css",
            body=f"<header><h1>All digests</h1></header>\n<ul class=\"archive-list\">{items}</ul>",
            footer='<a href="../">Latest digest</a>',
        )
    )
    print(f"rendered {len(days)} day(s) into docs/")


def main() -> None:
    if sys.argv[1:] == ["render"]:
        render_all()
        return
    entries = fetch_entries()
    print(f"{len(entries)} articles from the last 24h")
    if len(entries) < 10:
        sys.exit("too few articles — check feeds.txt")
    day = generate_day(entries)
    if not day["stories"]:
        sys.exit("model returned no stories")
    DATA.mkdir(exist_ok=True)
    (DATA / f"{day['date']}.json").write_text(json.dumps(day, ensure_ascii=False, indent=1))
    render_all()


if __name__ == "__main__":
    main()
