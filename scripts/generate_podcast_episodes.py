#!/usr/bin/env python3
"""
generate_podcast_episodes.py
Build-time script: generates first-party episode pages under /podcast/episodes/<slug>/
from live podcast RSS data merged with any existing manual enrichment stored in
data/podcast-episodes.json.

Each page includes:
  - Episode summary and key takeaways
  - Transcript text or external transcript URL
  - Related topic guide and book links
  - PodcastEpisode JSON-LD schema
  - A compatibility redirect page for bare session IDs like /podcast/TT-2026-04-10/
"""
from __future__ import annotations

import html as html_mod
import json
import os
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
EPISODES_DATA = ROOT / "data" / "podcast-episodes.json"
EPISODES_DIR = ROOT / "podcast" / "episodes"
PODCAST_COMPAT_DIR = ROOT / "podcast"
RSS_URL = os.environ.get(
    "PODCAST_RSS_URL",
    "https://podcast-rss-feeds.jonathan-harris.online/turing-torch.xml",
)
SITE = os.environ.get("PODCAST_SITE_BASE_URL", "https://jonathan-harris.online").rstrip("/")
SERIES_NAME = "Turing's Torch: AI Weekly"
SERIES_URL = f"{SITE}/podcast/"
NS = {"podcast": "https://podcastindex.org/namespace/1.0"}
PAGE_HEADER_ROW = 5


def load_partial(path: Path, label: str) -> str:
    if not path.exists():
        raise FileNotFoundError(f"{label} partial missing: {path}")
    return path.read_text(encoding="utf-8").rstrip("\n")


def slugify(title: str) -> str:
    slug = (title or "").lower()
    slug = re.sub(r"['’]", "", slug)
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")[:80]


def is_absolute_http_url(value: str | None) -> bool:
    return bool(value and re.match(r"^https?://", value.strip(), flags=re.IGNORECASE))


def first_non_empty(*values: object) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def clean_description(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    return re.sub(r"\s+", " ", text).strip()


def format_date_iso(pub_date: str) -> str:
    if not pub_date:
        return ""
    try:
        return parsedate_to_datetime(pub_date).strftime("%Y-%m-%d")
    except Exception:
        return ""


def is_first_party_episode_url(value: str | None) -> bool:
    if not is_absolute_http_url(value):
        return False
    candidate = str(value).strip().rstrip("/") + "/"
    return candidate.startswith(f"{SITE}/podcast/episodes/")


def parse_episode_page_url(link: str, title: str) -> str:
    if is_first_party_episode_url(link):
        return link
    return f"{SITE}/podcast/episodes/{slugify(title)}/"


def parse_audio_url(item: ET.Element) -> str:
    enclosure = item.find("enclosure")
    if enclosure is None:
        return ""
    candidate = first_non_empty(enclosure.get("url"), enclosure.get("href"))
    return candidate if is_absolute_http_url(candidate) else ""


def parse_transcript_url(item: ET.Element) -> str:
    tx = item.find("podcast:transcript", NS)
    if tx is None:
        return ""
    candidate = first_non_empty(tx.get("url"), tx.get("href"), tx.text)
    return candidate if is_absolute_http_url(candidate) else ""


def fetch_rss_episodes(limit: int = 20) -> list[dict]:
    request = urllib.request.Request(RSS_URL, headers={"User-Agent": "PodcastEpisodePageSync/1.0"})
    with urllib.request.urlopen(request, timeout=20) as resp:
        tree = ET.parse(resp)

    episodes: list[dict] = []
    for item in tree.findall(".//item")[:limit]:
        title = (item.findtext("title", "") or "").strip()
        if not title:
            continue

        pub_date = (item.findtext("pubDate", "") or "").strip()
        link = (item.findtext("link", "") or "").strip()
        guid = (item.findtext("guid", "") or "").strip()
        description = clean_description((item.findtext("description", "") or "").strip())
        session_id = guid if guid and not is_absolute_http_url(guid) else ""
        slug = slugify(title)

        episodes.append(
            {
                "title": title,
                "slug": slug,
                "session_id": session_id,
                "date": format_date_iso(pub_date),
                "page_url": parse_episode_page_url(link, title),
                "audio_url": parse_audio_url(item),
                "external_url": "",
                "summary": description[:500] if description else "",
                "key_takeaways": [],
                "transcript_url": parse_transcript_url(item),
                "transcript_text": "",
                "related_topic": {},
                "related_books": [],
            }
        )
    return episodes


def load_existing_episodes() -> dict[str, dict]:
    if not EPISODES_DATA.exists():
        return {}
    try:
        items = json.loads(EPISODES_DATA.read_text(encoding="utf-8"))
    except Exception:
        return {}
    existing: dict[str, dict] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        key = first_non_empty(item.get("session_id"), item.get("slug"), item.get("title"))
        if key:
            existing[key] = item
    return existing


def merge_episode(rss_ep: dict, existing_lookup: dict[str, dict]) -> dict:
    existing = existing_lookup.get(first_non_empty(rss_ep.get("session_id"), rss_ep.get("slug"), rss_ep.get("title")), {})
    merged = dict(existing)
    merged.update(rss_ep)

    merged["title"] = rss_ep["title"]
    merged["slug"] = rss_ep["slug"]
    merged["session_id"] = first_non_empty(rss_ep.get("session_id"), existing.get("session_id"))
    merged["date"] = first_non_empty(rss_ep.get("date"), existing.get("date"))
    merged["page_url"] = first_non_empty(rss_ep.get("page_url"), existing.get("page_url"), f"{SITE}/podcast/episodes/{rss_ep['slug']}/")
    merged["audio_url"] = first_non_empty(rss_ep.get("audio_url"), existing.get("audio_url"))
    merged["external_url"] = first_non_empty(existing.get("external_url"), rss_ep.get("external_url"))
    merged["summary"] = first_non_empty(existing.get("summary"), rss_ep.get("summary"))
    merged["transcript_url"] = first_non_empty(rss_ep.get("transcript_url"), existing.get("transcript_url"))
    merged["transcript_text"] = first_non_empty(existing.get("transcript_text"), rss_ep.get("transcript_text"))
    merged["key_takeaways"] = existing.get("key_takeaways") or rss_ep.get("key_takeaways") or []
    merged["related_topic"] = existing.get("related_topic") or rss_ep.get("related_topic") or {}
    merged["related_books"] = existing.get("related_books") or rss_ep.get("related_books") or []
    return merged


def load_and_merge_episodes() -> list[dict]:
    rss_episodes = fetch_rss_episodes()
    existing_lookup = load_existing_episodes()
    merged = [merge_episode(ep, existing_lookup) for ep in rss_episodes]
    EPISODES_DATA.parent.mkdir(parents=True, exist_ok=True)
    EPISODES_DATA.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {len(merged)} merged episode record(s) to {EPISODES_DATA.relative_to(ROOT)}")
    return merged


def build_episode_page(ep: dict) -> str:
    title = ep["title"]
    slug = ep["slug"]
    date = ep.get("date", "")
    summary = ep.get("summary", "")
    takeaways = ep.get("key_takeaways", [])
    transcript_text = ep.get("transcript_text", "")
    transcript_url = ep.get("transcript_url", "")
    audio_url = ep.get("audio_url", "")
    external_url = ep.get("external_url", "")
    related_topic = ep.get("related_topic", {}) or {}
    related_books = ep.get("related_books", []) or []
    canonical = ep.get("page_url") or f"{SITE}/podcast/episodes/{slug}/"

    takeaways_html = ""
    if takeaways:
        items = "".join(f"<li>{html_mod.escape(t)}</li>" for t in takeaways)
        takeaways_html = f'<section class="card u-s21"><h2>Key takeaways</h2><ul>{items}</ul></section>'

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

    related_topic_html = ""
    if isinstance(related_topic, dict) and related_topic.get("url"):
        related_topic_html = (
            f'<p>Related topic guide: <a href="{html_mod.escape(related_topic["url"])}">'
            f'{html_mod.escape(related_topic.get("name", "Related topic"))}</a></p>'
        )

    related_books_html = ""
    if related_books:
        links = " · ".join(
            f'<a href="{html_mod.escape(b["url"])}">{html_mod.escape(b["title"])}</a>'
            for b in related_books
            if isinstance(b, dict) and b.get("url") and b.get("title")
        )
        if links:
            related_books_html = f'<section class="card u-s21"><h2>Related books</h2><p>{links}</p></section>'

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
    if audio_url:
        schema["associatedMedia"] = {"@type": "AudioObject", "contentUrl": audio_url}

    breadcrumb = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{SITE}/"},
            {"@type": "ListItem", "position": 2, "name": "Podcast", "item": SERIES_URL},
            {"@type": "ListItem", "position": 3, "name": title, "item": canonical},
        ],
    }

    audio_player = (
        f'<section class="card u-s21"><h2>Listen</h2>'
        f'<audio class="podcast-episode-audio" controls preload="none">'
        f'<source src="{html_mod.escape(audio_url)}" type="audio/mpeg"/>'
        f'Your browser does not support the audio element.'
        f'</audio></section>'
        if audio_url else ""
    )

    listen_link = (
        f'<p><a class="button" href="{html_mod.escape(external_url)}" '
        f'rel="noopener noreferrer" target="_blank">Open external episode link ↗</a></p>'
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
    {audio_player}
    {takeaways_html}
    {transcript_html}
    {related_section}
  </div>
</main>
{load_partial(FOOTER_PARTIAL, "footer")}
<script defer="" src="/assets/js/site-ui.min.js"></script>
</body>
</html>"""


def build_compat_redirect(session_id: str, slug: str) -> str:
    canonical = f"/podcast/episodes/{slug}/"
    return f"""<!DOCTYPE html>
<html lang="en-GB">
<head>
<meta charset="utf-8"/>
<meta http-equiv="refresh" content="0; url={canonical}"/>
<link rel="canonical" href="{canonical}"/>
<title>Redirecting…</title>
<script>window.location.replace({json.dumps(canonical)});</script>
</head>
<body>
<p>Redirecting to <a href="{canonical}">{canonical}</a>.</p>
</body>
</html>"""


def validate_recent_episode_contract(expected_count: int) -> list[str]:
    if not HTML_INDEX.exists():
        return [f"Missing podcast index: {HTML_INDEX}"]

    src = HTML_INDEX.read_text(encoding="utf-8")
    failures: list[str] = []
    count = src.count('class="podcast-episode-item"')
    if count != expected_count:
        failures.append(f"Recent episode card count mismatch: expected {expected_count}, found {count}")

    pattern = (
        r"<section[^>]*podcast-episodes-static[^>]*>.*?</p>(?P<body>.*?)<p[^>]*u-s40[^>]*>"
    )
    match = re.search(pattern, src, flags=re.DOTALL)
    if not match:
        failures.append("Unable to locate recent-episodes body in podcast/index.html")
        return failures

    hrefs = re.findall(r'<a href="([^"]+)"', match.group("body"))
    for href in hrefs[:expected_count]:
        if not href.startswith(f"{SITE}/podcast/episodes/") and not href.startswith("/podcast/episodes/"):
            failures.append(f"Recent episode href is not a first-party episode page: {href}")
    return failures


HTML_INDEX = ROOT / "podcast" / "index.html"


def validate_generated_pages(episodes: list[dict]) -> list[str]:
    failures: list[str] = []
    expected_recent = min(4, len(episodes))
    failures.extend(validate_recent_episode_contract(expected_recent))

    for ep in episodes[:expected_recent]:
        slug = ep.get("slug", "")
        if not slug:
            failures.append(f"Episode missing slug: {ep.get('title', '(untitled)')}")
            continue

        page_path = EPISODES_DIR / slug / "index.html"
        if not page_path.exists():
            failures.append(f"Missing generated page: {page_path.relative_to(ROOT)}")
            continue

        page_html = page_path.read_text(encoding="utf-8")
        audio_url = (ep.get("audio_url") or "").strip()
        if audio_url:
            if '<audio controls' not in page_html:
                failures.append(f"Audio player missing from episode page: {slug}")
            if html_mod.escape(audio_url) not in page_html:
                failures.append(f"Audio URL missing from episode page: {slug}")

        transcript_url = (ep.get("transcript_url") or "").strip()
        if transcript_url and html_mod.escape(transcript_url) not in page_html and "<h2>Transcript</h2>" not in page_html:
            failures.append(f"Transcript handling missing from episode page: {slug}")

        session_id = (ep.get("session_id") or "").strip()
        if session_id:
            compat_path = PODCAST_COMPAT_DIR / session_id / "index.html"
            if not compat_path.exists():
                failures.append(f"Missing compatibility redirect: {compat_path.relative_to(ROOT)}")

    return failures


def register_in_workbook(slugs_generated: list[str]) -> None:
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
        title_m = re.search(r"<title>(.*?)</title>", page.read_text(encoding="utf-8"))
        title = html_mod.unescape(title_m.group(1).strip()) if title_m else slug
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
    try:
        episodes = load_and_merge_episodes()
    except Exception as exc:
        print(f"Failed to fetch or merge podcast episodes: {exc}", file=sys.stderr)
        return 1

    if not episodes:
        print("No episode data found.", file=sys.stderr)
        return 1

    EPISODES_DIR.mkdir(parents=True, exist_ok=True)
    created = 0
    generated_slugs: list[str] = []
    for ep in episodes:
        slug = ep.get("slug")
        if not slug:
            continue
        ep_dir = EPISODES_DIR / slug
        ep_dir.mkdir(parents=True, exist_ok=True)
        (ep_dir / "index.html").write_text(build_episode_page(ep), encoding="utf-8")
        created += 1
        generated_slugs.append(slug)
        print(f"  Generated: podcast/episodes/{slug}/")

        session_id = ep.get("session_id")
        if session_id:
            compat_dir = PODCAST_COMPAT_DIR / session_id
            compat_dir.mkdir(parents=True, exist_ok=True)
            (compat_dir / "index.html").write_text(build_compat_redirect(session_id, slug), encoding="utf-8")
            print(f"  Generated compatibility redirect: podcast/{session_id}/")

    print(f"Generated {created} episode page(s) under podcast/episodes/")

    validation_failures = validate_generated_pages(episodes)
    if validation_failures:
        for failure in validation_failures:
            print(f"[FAIL] {failure}", file=sys.stderr)
        return 1

    print("Podcast episode generation checks passed.")
    register_in_workbook(generated_slugs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
