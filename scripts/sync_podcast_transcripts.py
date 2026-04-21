"""
sync_podcast_transcripts.py
Build-time script: fetches the podcast RSS feed and rewrites the transcript list
in podcast/index.html with the latest transcript-capable episode links.
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
HTML_FILE = Path("podcast/index.html")
LIMIT = 24
NS = {"podcast": "https://podcastindex.org/namespace/1.0"}


def is_absolute_http_url(value: str | None) -> bool:
    return bool(value and re.match(r"^https?://", value.strip(), flags=re.IGNORECASE))


def extract_transcript_url(item: ET.Element) -> str:
    tx = item.find("podcast:transcript", NS)
    if tx is None:
        return ""
    for candidate in (tx.get("url"), tx.get("href"), tx.text):
        if is_absolute_http_url(candidate):
            return str(candidate).strip()
    return ""


def format_date(pub_date_str: str) -> str:
    if not pub_date_str:
        return ""
    try:
        dt = parsedate_to_datetime(pub_date_str)
        return dt.strftime("%d %B %Y").lstrip("0")
    except Exception:
        return pub_date_str


def fetch_transcripts() -> list[dict]:
    request = urllib.request.Request(RSS_URL, headers={"User-Agent": "PodcastTranscriptSync/1.0"})
    with urllib.request.urlopen(request, timeout=15) as response:
        tree = ET.parse(response)

    items: list[dict] = []
    for item in tree.findall(".//item")[:LIMIT]:
        title = (item.findtext("title", "") or "").strip()
        if not title:
            continue
        pub_date = (item.findtext("pubDate", "") or "").strip()
        url = extract_transcript_url(item)
        if not is_absolute_http_url(url):
            continue
        items.append({
            "title": title,
            "url": url,
            "date": format_date(pub_date),
        })
    return items


def build_list_html(items: list[dict]) -> str:
    rows = []
    for item in items:
        title = html.escape(item["title"])
        url = html.escape(item["url"])
        date = html.escape(item.get("date", ""))
        meta = f"Published {date} · transcript archive entry" if date else "Transcript archive entry"
        rows.append(
            "<li>"
            f'<a href="{url}" rel="noopener noreferrer" target="_blank">{title}</a>'
            f'<span class="transcript-meta">{meta}</span>'
            "</li>"
        )
    return "\n".join(rows)


def inject(items: list[dict]) -> None:
    src = HTML_FILE.read_text(encoding="utf-8")
    pattern = r'(<ul[^>]*id="transcriptList"[^>]*>).*?(</ul>)'
    replacement = r"\1\n" + build_list_html(items) + "\n" + r"\2"
    new_src, count = re.subn(pattern, replacement, src, count=1, flags=re.DOTALL)
    if count == 0:
        print("WARNING: transcriptList not found in podcast/index.html — file left unchanged.", file=sys.stderr)
        return
    HTML_FILE.write_text(new_src, encoding="utf-8")
    print(f"Injected {len(items)} transcript entries into podcast/index.html.")


def main() -> None:
    try:
        items = fetch_transcripts()
    except Exception as exc:
        print(f"WARNING: RSS fetch failed — {exc}. transcript list left unchanged.", file=sys.stderr)
        sys.exit(0)

    if not items:
        print("WARNING: no transcript-capable podcast items found — transcript list left unchanged.", file=sys.stderr)
        sys.exit(0)

    inject(items)


if __name__ == "__main__":
    main()
