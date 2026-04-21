"""
sync_podcast_episodes.py
Build-time script: fetches the Turing's Torch: AI Weekly RSS feed and
refreshes any optional recent-episodes section of podcast/index.html with live data.

Called from build.sh before deployment_ci.py.
"""

from __future__ import annotations

import html
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

RSS_URL = os.environ.get(
    "PODCAST_RSS_URL",
    "https://podcast-rss-feeds.jonathan-harris.online/turing-torch.xml",
)
SITE_BASE_URL = os.environ.get("PODCAST_SITE_BASE_URL", "https://jonathan-harris.online").rstrip("/")
SERIES_URL = f"{SITE_BASE_URL}/podcast/"
HTML_FILE = Path("podcast/index.html")
LIMIT = 4
NS = {"podcast": "https://podcastindex.org/namespace/1.0"}


def slugify(value: str) -> str:
    slug = (value or "").lower()
    slug = re.sub(r"['’]", "", slug)
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")[:80]


def is_absolute_http_url(value: str | None) -> bool:
    return bool(value and re.match(r"^https?://", value.strip(), flags=re.IGNORECASE))


def is_first_party_episode_url(value: str | None) -> bool:
    if not is_absolute_http_url(value):
        return False
    candidate = str(value).strip().rstrip("/") + "/"
    return candidate.startswith(f"{SITE_BASE_URL}/podcast/episodes/")


def is_transcript_asset_url(value: str | None) -> bool:
    if not is_absolute_http_url(value):
        return False
    stripped = str(value).strip().lower()
    return "transcript" in stripped and (stripped.endswith(".txt") or stripped.endswith(".html"))


def episode_page_url(title: str) -> str:
    return f"{SITE_BASE_URL}/podcast/episodes/{slugify(title)}/"


def resolve_item_url(item: ET.Element, title: str) -> str:
    link = (item.findtext("link", "") or "").strip()

    if is_first_party_episode_url(link):
        return link

    if is_absolute_http_url(link) and not is_transcript_asset_url(link) and link.rstrip("/") != SERIES_URL.rstrip("/"):
        return episode_page_url(title)

    return episode_page_url(title)


def fetch_episodes() -> list[dict]:
    request = urllib.request.Request(RSS_URL, headers={"User-Agent": "PodcastEpisodeSync/1.0"})
    with urllib.request.urlopen(request, timeout=15) as response:
        tree = ET.parse(response)

    episodes = []
    for item in tree.findall(".//item")[:LIMIT]:
        title = (item.findtext("title", "") or "").strip()
        if not title:
            continue
        pub_date = (item.findtext("pubDate", "") or "").strip()
        formatted_date = _format_date(pub_date)
        episodes.append(
            {
                "title": title,
                "link": resolve_item_url(item, title),
                "formatted_date": formatted_date,
            }
        )
    return episodes


def _format_date(pub_date_str: str) -> str:
    if not pub_date_str:
        return pub_date_str
    try:
        dt = parsedate_to_datetime(pub_date_str)
        return dt.strftime("%-d %B %Y")
    except Exception:
        return pub_date_str


def build_html(episodes: list[dict]) -> str:
    rows = []
    for ep in episodes:
        t = html.escape(ep["title"])
        u = html.escape(ep["link"])
        d = html.escape(ep["formatted_date"])
        rows.append(
            '<div class="podcast-episode-item">\n'
            '  <span aria-hidden="true" class="podcast-episode-item__num">&#9654;</span>\n'
            '  <div class="podcast-episode-item__body">\n'
            '    <div class="podcast-episode-item__title">\n'
            f'      <a href="{u}">{t}</a>\n'
            "    </div>\n"
            f'    <div class="podcast-episode-item__date">{d}</div>\n'
            "  </div>\n"
            "</div>"
        )
    return "\n".join(rows)


def inject(episodes: list[dict]) -> None:
    src = HTML_FILE.read_text(encoding="utf-8")
    pattern = (
        r"(<section[^>]*podcast-episodes-static[^>]*>.*?</p>)"
        r".*?"
        r"(<p[^>]*u-s40[^>]*>.*?</section>)"
    )

    fresh_html = build_html(episodes)
    replacement = r"\1" + "\n" + fresh_html + "\n" + r"\2"

    new_src, count = re.subn(pattern, replacement, src, flags=re.DOTALL)

    if count == 0:
        print(
            "INFO: Recent episodes section is not present in podcast/index.html — skipping sync.",
            file=sys.stderr,
        )
        return

    HTML_FILE.write_text(new_src, encoding="utf-8")
    print(f"Injected {len(episodes)} episodes into podcast/index.html.")


def main() -> None:
    try:
        episodes = fetch_episodes()
    except Exception as exc:
        print(
            f"WARNING: RSS fetch failed — {exc}. podcast/index.html left unchanged.",
            file=sys.stderr,
        )
        sys.exit(0)

    inject(episodes)


if __name__ == "__main__":
    main()
