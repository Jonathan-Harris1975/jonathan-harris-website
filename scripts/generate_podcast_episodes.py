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
REDIRECTS_FILE = ROOT / "_redirects"
RSS_URL = os.environ.get(
    "PODCAST_RSS_URL",
    "https://podcast-rss-feeds.jonathan-harris.online/turing-torch.xml",
)
SITE = os.environ.get("PODCAST_SITE_BASE_URL", "https://jonathan-harris.online").rstrip("/")
SERIES_NAME = "Turing's Torch: AI Weekly"
SERIES_URL = f"{SITE}/podcast/"
NS = {"podcast": "https://podcastindex.org/namespace/1.0"}
PAGE_HEADER_ROW = 5
GENERIC_PODCAST_SLUGS = {"artificial-intelligence-weekly"}



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


def episode_slug_suffix(ep: dict) -> str:
    date_value = first_non_empty(ep.get("date"))
    session_id = first_non_empty(ep.get("session_id"))
    date_match = re.search(r"\d{4}-\d{2}-\d{2}", first_non_empty(date_value, session_id))
    if date_match:
        return date_match.group(0)
    return slugify(first_non_empty(session_id, ep.get("title")))[:40]


def ensure_unique_episode_slugs(episodes: list[dict]) -> list[dict]:
    """Guarantee one stable canonical episode URL per episode record.

    RSS titles can collapse into generic slugs such as
    ``artificial-intelligence-weekly``. That creates multiple records with one
    canonical URL, so append the ISO episode date or session identifier whenever
    the base slug is generic or already taken.
    """
    seen: set[str] = set()
    normalised: list[dict] = []

    for raw_ep in episodes:
        ep = dict(raw_ep)
        base_slug = slugify(first_non_empty(ep.get("slug"), ep.get("title")))
        if not base_slug:
            base_slug = slugify(first_non_empty(ep.get("session_id"), "podcast-episode")) or "podcast-episode"

        slug = base_slug
        if slug in GENERIC_PODCAST_SLUGS or slug in seen:
            suffix = slugify(episode_slug_suffix(ep))
            slug = f"{base_slug}-{suffix}" if suffix else base_slug

        counter = 2
        candidate = slug
        while candidate in seen:
            candidate = f"{slug}-{counter}"
            counter += 1

        ep["slug"] = candidate
        ep["page_url"] = f"{SITE}/podcast/episodes/{candidate}/"
        seen.add(candidate)
        normalised.append(ep)

    return normalised


def persist_episode_data(episodes: list[dict]) -> None:
    EPISODES_DATA.parent.mkdir(parents=True, exist_ok=True)
    EPISODES_DATA.write_text(json.dumps(episodes, indent=2, ensure_ascii=False), encoding="utf-8")


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


def trim_to_sentence(text: str, limit: int = 155) -> str:
    cleaned = clean_description(text)
    if len(cleaned) <= limit:
        return cleaned
    candidate = cleaned[:limit].rsplit(" ", 1)[0].strip(" ,;:-")
    if not candidate:
        candidate = cleaned[:limit].strip()
    return candidate + "…"


def fallback_episode_summary(title: str) -> str:
    clean_title = clean_description(title) or "this episode"
    return (
        f"Jonathan Harris examines {clean_title} in plain English, cutting through AI hype and focusing on what the story means for work, policy, business, and everyday users."
    )


def normalise_episode_summary(ep: dict) -> str:
    return first_non_empty(ep.get("summary"), fallback_episode_summary(ep.get("title", "")))


def direct_answer_for_episode(ep: dict) -> str:
    summary = normalise_episode_summary(ep)
    title = clean_description(ep.get("title", "this episode"))
    return (
        f"This episode of {SERIES_NAME} explains {title} through the practical lens Jonathan Harris uses across his AI books and commentary. "