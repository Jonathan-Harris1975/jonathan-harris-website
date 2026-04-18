#!/usr/bin/env python3
"""
generate_podcast_episodes.py
Build-time script: generates first-party episode pages under /podcast/episodes/<slug>/
from a podcast episodes data file (data/podcast-episodes.json).

Each page includes:
  - Episode summary and key takeaways
  - Transcript text or external transcript URL
  - Related topic guide and book links
  - PodcastEpisode JSON-LD schema

Creates data/podcast-episodes.json from the RSS feed if it does not exist,
using the same RSS URL as sync_podcast_episodes.py.
"""
from __future__ import annotations

import html as html_mod
import json
import re
import sys
import urllib.request

import openpyxl
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADER_PARTIAL = ROOT / "assets" / "partials" / "header.html"
FOOTER_PARTIAL = ROOT / "assets" / "partials" / "footer.html"


def load_partial(path: Path, label: str) -> str:
    if not path.exists():
        raise FileNotFoundError(f"{label} partial missing: {path}")
    return path.read_text(encoding="utf-8").rstrip("\n")
EPISODES_DATA = ROOT / "data" / "podcast-episodes.json"
EPISODES_DIR = ROOT / "podcast" / "episodes"
RSS_URL = "https://podcast-rss-feeds.jonathan-harris.online/turing-torch.xml"
SITE = "https://jonathan-harris.online"
SERIES_NAME = "Turing's Torch: AI Weekly"
SERIES_URL = f"{SITE}/podcast/"


def slugify(title: str) -> str:
    slug = title.lower()
    slug = re.sub(r"[''']", "", slug)
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")[:80]


def fetch_rss_episodes(limit: int = 20) -> list[dict]:
    with urllib.request.urlopen(RSS_URL, timeout=20) as resp:
        tree = ET.parse(resp)
    episodes = []
    for item in tree.findall(".//item")[:limit]:
        title = item.findtext("title", "").strip()
        pub_date = item.findtext("pubDate", "").strip()
        link = item.findtext("link", "").strip()
        guid = item.findtext("guid", "").strip()
        description = item.findtext("description", "").strip()
        # Clean HTML from description if present
        description = re.sub(r"<[^>]+>", " ", description)
        description = re.sub(r"\s+", " ", description).strip()

        if not link or link == SERIES_URL:
            link = guid

        date_iso = ""
        if pub_date:
            try:
                date_iso = parsedate_to_datetime(pub_date).strftime("%Y-%m-%d")
            except Exception:
                pass

        if not title:
            continue

        episodes.append({
            "title": title,
            "slug": slugify(title),
            "date": date_iso,
            "external_url": link,
            "summary": description[:500] if description else "",
            "key_takeaways": [],
            "transcript_url": "",
            "transcript_text": "",
            "related_topic": "",
            "related_books": [],
        })
    return episodes


def load_or_fetch_episodes() -> list[dict]:
    if EPISODES_DATA.exists():
        return json.loads(EPISODES_DATA.read_text(encoding="utf-8"))
    print("data/podcast-episodes.json not found — fetching from RSS feed…")
    episodes = fetch_rss_episodes()
    EPISODES_DATA.parent.mkdir(parents=True, exist_ok=True)
    EPISODES_DATA.write_text(json.dumps(episodes, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {len(episodes)} episodes to {EPISODES_DATA.relative_to(ROOT)}")
    return episodes


def build_episode_page(ep: dict) -> str:
    title = ep["title"]
    slug = ep["slug"]
    date = ep.get("date", "")
    summary = ep.get("summary", "")
    takeaways = ep.get("key_takeaways", [])
    transcript_text = ep.get("transcript_text", "")
    transcript_url = ep.get("transcript_url", "")
    external_url = ep.get("external_url", "")
    related_topic = ep.get("related_topic", "")
    related_books = ep.get("related_books", [])
    canonical = f"{SITE}/podcast/episodes/{slug}/"

    # Takeaways HTML
    takeaways_html = ""
    if takeaways:
        items = "".join(f"<li>{html_mod.escape(t)}</li>" for t in takeaways)
        takeaways_html = f'<section class="card u-s21"><h2>Key takeaways</h2><ul>{items}</ul></section>'

    # Transcript HTML
    transcript_html = ""
    if transcript_text:
        paras = "".join(f"<p>{html_mod.escape(p.strip())}</p>" for p in transcript_text.split("\n\n") if p.strip())
        transcript_html = f'<section class="card u-s22"><h2>Transcript</h2><div class="episode-transcript">{paras}</div></section>'
    elif transcript_url:
        transcript_html = (
            f'<section class="card u-s22"><h2>Transcript</h2>'
            f'<p><a href="{html_mod.escape(transcript_url)}" rel="noopener noreferrer" target="_blank">Read the full transcript</a></p>'
            f'</section>'
        )

    # Related topic HTML
    related_topic_html = ""
    if related_topic and related_topic.get("url"):
        related_topic_html = (
            f'<p>Related topic guide: <a href="{html_mod.escape(related_topic["url"])}">'
            f'{html_mod.escape(related_topic["name"])}</a></p>'
        )

    # Related books HTML
    related_books_html = ""
    if related_books:
        links = " · ".join(
            f'<a href="{html_mod.escape(b["url"])}">{html_mod.escape(b["title"])}</a>'
            for b in related_books
        )
        related_books_html = f'<section class="card u-s21"><h2>Related books</h2><p>{links}</p></section>'

    # JSON-LD
    schema: dict = {
        "@context": "https://schema.org",
        "@type": "PodcastEpisode",
        "name": title,
        "url": canonical,
        "datePublished": date,
        "description": summary,
        "partOfSeries": {
            "@type": "PodcastSeries",
            "name": SERIES_NAME,
            "url": SERIES_URL,
        },
        "author": {"@id": f"{SITE}/#person"},
    }
    if transcript_url:
        schema["transcript"] = transcript_url
    if external_url:
        schema["associatedMedia"] = {"@type": "AudioObject", "contentUrl": external_url}

    breadcrumb = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{SITE}/"},
            {"@type": "ListItem", "position": 2, "name": "Podcast", "item": SERIES_URL},
            {"@type": "ListItem", "position": 3, "name": title, "item": canonical},
        ],
    }

    listen_link = (
        f'<p><a class="button" href="{html_mod.escape(external_url)}" '
        f'rel="noopener noreferrer" target="_blank">Listen to this episode ↗</a></p>'
        if external_url else ""
    )

    related_section = ""
    if related_topic_html or related_books_html:
        related_section = f'<section class="card u-s21"><h2>Related reading</h2>{related_topic_html}</section>{related_books_html}'

    display_date = date if date else ""

    return f"""<!DOCTYPE html>
<html lang="en-GB">
<head>
<meta charset="utf-8"/>
<link href="https://assets.jonathan-harris.online/favicon.ico" rel="icon" type="image/x-icon"/>
<link href="https://images.jonathan-harris.online" rel="preconnect"/>
<link href="https://assets.jonathan-harris.online" rel="preconnect"/>
<meta content="width=device-width, initial-scale=1, viewport-fit=cover" name="viewport"/>
<title>{html_mod.escape(title)} | Turing&#39;s Torch | Jonathan Harris</title>
<meta content="{html_mod.escape(summary[:155])}" name="description"/>
<meta content="index,follow" name="robots"/>
<meta content="#0D1420" name="theme-color"/>
<link href="https://fonts.googleapis.com" rel="preconnect"/>
<link crossorigin="" href="https://fonts.gstatic.com" rel="preconnect"/>
<link href="https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,400;0,600;0,700;0,800&display=swap" rel="stylesheet"/>
<link as="style" href="/assets/css/site.css" rel="preload"/>
<script>document.documentElement.classList.add('js-enabled');</script><link href="/assets/css/site.css" rel="stylesheet"/>
<meta content="article" property="og:type"/>
<meta content="{html_mod.escape(canonical)}" property="og:url"/>
<meta content="{html_mod.escape(title)} | Turing&#39;s Torch" property="og:title"/>
<meta content="{html_mod.escape(summary[:155])}" property="og:description"/>
<meta content="https://images.jonathan-harris.online/site-logo" property="og:image"/>
<meta content="summary_large_image" name="twitter:card"/>
<meta content="{html_mod.escape(title)} | Turing&#39;s Torch" name="twitter:title"/>
<meta content="{html_mod.escape(summary[:155])}" name="twitter:description"/>
<link href="{html_mod.escape(canonical)}" rel="canonical"/>
<script type="application/ld+json">{json.dumps(schema, ensure_ascii=False)}</script>
<script type="application/ld+json">{json.dumps(breadcrumb, ensure_ascii=False)}</script>
<link href="https://cdn-cookieyes.com" rel="dns-prefetch"/>
<link href="https://tracker.metricool.com" rel="dns-prefetch"/>
<script async="" id="cookieyes" src="https://cdn-cookieyes.com/client_data/c981d18033783598d2216add/script.js" type="text/javascript"></script>
<script defer="" src="/assets/js/consent-managed-scripts.min.js"></script>
</head>
<body class="page-podcast-episode jh-no-hero-page">
<a class="skip-link" href="#main">Skip to main content</a>
{load_partial(HEADER_PARTIAL, "header")}
<main class="main" id="main" role="main">
  <div class="wrap ebook-shell">
    <section class="card ebook-index-intro">
      <p class="breadcrumb-hint"><a href="/podcast/">← Podcast</a></p>
      <h1>{html_mod.escape(title)}</h1>
      {f'<p class="episode-meta">Published {html_mod.escape(display_date)}</p>' if display_date else ""}
      <p>{html_mod.escape(summary)}</p>
      {listen_link}
    </section>
    {takeaways_html}
    {transcript_html}
    {related_section}
  </div>
</main>
{load_partial(FOOTER_PARTIAL, "footer")}
<script defer="" src="/assets/js/site-ui.min.js"></script>
</body>
</html>"""


SITE = "https://jonathan-harris.online"
PAGE_HEADER_ROW = 5


def register_in_workbook(slugs_generated: list[str]) -> None:
    """Add newly generated episode pages to the workbook Pages sheet if absent."""
    wb_candidates = sorted(ROOT.glob("*.xlsm")) + sorted(ROOT.glob("*.xlsx"))
    if not wb_candidates:
        print("  [WARN] No workbook found — skipping workbook registration.")
        return
    wb_path = wb_candidates[0]
    wb = openpyxl.load_workbook(wb_path, keep_vba=True)
    if "Pages" not in wb.sheetnames:
        print("  [WARN] Workbook has no Pages sheet — skipping registration.")
        return
    ws = wb["Pages"]

    # Build set of already-governed relative paths
    governed: set[str] = set()
    last_row = PAGE_HEADER_ROW
    for row in range(PAGE_HEADER_ROW + 1, ws.max_row + 1):
        val = ws.cell(row, 1).value
        if val:
            governed.add(str(val).strip())
            last_row = row

    next_row = last_row + 1
    added = 0
    for slug in sorted(slugs_generated):
        rel = f"podcast/episodes/{slug}/index.html"
        if rel in governed:
            continue
        page = ROOT / rel
        if not page.exists():
            continue
        import re as _re
        html = page.read_text(encoding="utf-8")
        title_m = _re.search(r"<title>(.*?)</title>", html)
        title = title_m.group(1).strip() if title_m else slug
        url_path = f"/podcast/episodes/{slug}/"
        ws.cell(next_row, 1).value = rel
        ws.cell(next_row, 2).value = url_path
        ws.cell(next_row, 3).value = SITE + url_path
        ws.cell(next_row, 4).value = title
        ws.cell(next_row, 5).value = "Podcast episode"
        print(f"  Registered in workbook: {rel}")
        next_row += 1
        added += 1

    if added:
        wb.save(wb_path)
        print(f"  Workbook saved — {added} new episode(s) registered.")
    else:
        print("  Workbook: all episode pages already governed.")


def main() -> int:
    episodes = load_or_fetch_episodes()
    if not episodes:
        print("No episode data found.", file=sys.stderr)
        return 1

    EPISODES_DIR.mkdir(parents=True, exist_ok=True)
    created = 0
    for ep in episodes:
        slug = ep.get("slug")
        if not slug:
            continue
        ep_dir = EPISODES_DIR / slug
        ep_dir.mkdir(parents=True, exist_ok=True)
        page = build_episode_page(ep)
        (ep_dir / "index.html").write_text(page, encoding="utf-8")
        created += 1
        print(f"  Generated: podcast/episodes/{slug}/")

    print(f"Generated {created} episode page(s) under podcast/episodes/")
    register_in_workbook([ep["slug"] for ep in episodes if ep.get("slug")])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
