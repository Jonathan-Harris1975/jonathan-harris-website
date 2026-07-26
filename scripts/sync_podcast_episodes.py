#!/usr/bin/env python3
"""Refresh a resilient static podcast fallback from the governed RSS feed.

The live Pages Functions still read the RSS feed at request time. This build-time
snapshot exists so the initial HTML, sitemap and LLM index remain useful if a
crawler does not execute JavaScript or a runtime feed request temporarily fails.
A network failure never deletes the last known-good snapshot.
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "podcast-episodes.json"
DEFAULT_FEED = "https://podcast-rss-feeds.jonathan-harris.online/turing-torch.xml"
SITE = "https://jonathan-harris.online"
MAX_EPISODES = 20


def clean(value: str | None) -> str:
    text = re.sub(r"<[^>]+>", " ", html.unescape(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def slugify(value: str) -> str:
    value = clean(value).lower().replace("’", "").replace("'", "")
    return re.sub(r"^-+|-+$", "", re.sub(r"[^a-z0-9]+", "-", value))[:90]


def date_iso(value: str) -> str:
    try:
        return parsedate_to_datetime(value).date().isoformat()
    except Exception:
        match = re.search(r"\d{4}-\d{2}-\d{2}", value or "")
        return match.group(0) if match else ""


def child_text(item: ET.Element, local_name: str) -> str:
    for child in item.iter():
        if child.tag.split("}")[-1].lower() == local_name.lower():
            return clean(child.text)
    return ""


def child_attr(item: ET.Element, local_name: str, attr: str) -> str:
    for child in item.iter():
        if child.tag.split("}")[-1].lower() == local_name.lower():
            return clean(child.attrib.get(attr, ""))
    return ""


def transcript_site_url(raw_url: str) -> tuple[str, str]:
    if not raw_url:
        return "", ""
    try:
        key = urlparse(raw_url).path.rstrip("/").split("/")[-1]
    except Exception:
        return "", ""
    key = clean(key)
    if not key:
        return "", ""
    session_id = re.sub(r"\.(?:html?|txt|json|xml)$", "", key, flags=re.I)
    return f"{SITE}/transcripts/{key}", session_id


def parse_feed(xml_bytes: bytes) -> list[dict[str, str]]:
    root = ET.fromstring(xml_bytes)
    records: list[dict[str, str]] = []
    for item in [node for node in root.iter() if node.tag.split("}")[-1].lower() == "item"]:
        title = child_text(item, "title")
        if not title:
            continue
        link = child_text(item, "link")
        description = child_text(item, "summary") or child_text(item, "description")
        published = child_text(item, "pubDate")
        enclosure = child_attr(item, "enclosure", "url")
        transcript_raw = child_attr(item, "transcript", "url")
        transcript_url, session_id = transcript_site_url(transcript_raw)
        link_slug = ""
        try:
            link_slug = urlparse(link).path.rstrip("/").split("/")[-1]
        except Exception:
            pass
        slug = slugify(link_slug or title)
        if not slug:
            continue
        records.append({
            "slug": slug,
            "title": title,
            "summary": description,
            "date": date_iso(published),
            "episode_url": link or f"{SITE}/podcast/episodes/{slug}/",
            "audio_url": enclosure,
            "transcript_url": transcript_url,
            "session_id": session_id,
        })
    return records[:MAX_EPISODES]


def fetch_feed(url: str, attempts: int = 4) -> bytes:
    last: Exception | None = None
    for attempt in range(attempts):
        req = urllib.request.Request(url, headers={"Accept": "application/rss+xml, application/xml, text/xml", "User-Agent": "JonathanHarrisBuild/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                if response.status != 200:
                    raise RuntimeError(f"HTTP {response.status}")
                return response.read()
        except Exception as exc:
            last = exc
            if attempt + 1 < attempts:
                time.sleep(0.5 * (2 ** attempt))
    raise last or RuntimeError("podcast feed unavailable")


def main() -> int:
    configured = os.environ.get("PODCAST_RSS_FEED_URL", "").strip() or os.environ.get("R2_PUBLIC_BASE_URL_PODCAST_RSS", "").strip() or DEFAULT_FEED
    feed_url = configured if configured.endswith(".xml") else configured.rstrip("/") + "/turing-torch.xml"
    try:
        records = parse_feed(fetch_feed(feed_url))
        if not records:
            raise RuntimeError("RSS contained no usable podcast items")
        OUT.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Podcast fallback refreshed from RSS: {len(records)} episodes.")
        return 0
    except Exception as exc:
        existing: list[dict] = []
        try:
            payload = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else []
            existing = payload if isinstance(payload, list) else []
        except Exception:
            existing = []
        if existing:
            print(f"WARN: podcast RSS refresh failed ({exc}); retaining {len(existing)} last-known-good episodes.")
            return 0
        print(f"WARN: podcast RSS refresh failed ({exc}); no static fallback is available yet. Runtime RSS rendering remains enabled.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
