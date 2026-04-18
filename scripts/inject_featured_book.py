#!/usr/bin/env python3
"""
inject_featured_book.py
Build-time script: selects the featured book for the current ISO week using the
same rotation logic as functions/api/v1/featured-book.json.js and rewrites the
static featured-book block in index.html.

This eliminates the source-vs-rendered divergence reported in audit finding XSM-01.
Called from deployment_ci.py before other build steps.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOKS_JSON = ROOT / "api" / "v1" / "books.json"
INDEX_HTML = ROOT / "index.html"


def iso_week(now: datetime) -> int:
    """Return the ISO week number using the same algorithm as featured-book.json.js."""
    date = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    day = date.isoweekday()  # Mon=1 … Sun=7
    thursday = date + timedelta(days=4 - day)
    year_start = datetime(thursday.year, 1, 1, tzinfo=timezone.utc)
    return int(((thursday - year_start).days + 1) / 7) + 1


def select_featured(books: list[dict], now: datetime | None = None) -> dict:
    if now is None:
        now = datetime.now(timezone.utc)
    week = iso_week(now)
    return books[week % len(books)]


def inject(book: dict) -> None:
    slug = book["slug"]
    title = book["title"]
    short = book.get("short", "")
    cover = book.get("cover", book.get("main_image", ""))
    topic = book.get("filter", "")
    pages = book.get("pages")
    meta = (f"{topic} · " if topic else "") + (f"{pages} pages" if pages else "")
    url = book.get("canonical_url", f"/ebooks/{slug}/")
    # canonical_url is absolute; we want a root-relative href for the static page
    url_rel = re.sub(r"^https://jonathan-harris\.online", "", url)
    buy_rel = book.get("buy_route", f"{url_rel}buy-now")

    src = INDEX_HTML.read_text(encoding="utf-8")

    # featuredEbookPage href
    src = re.sub(
        r'(<a aria-label="View featured book" href=")[^"]+(" id="featuredEbookPage")',
        rf'\g<1>{url_rel}\g<2>', src
    )
    # featuredEbookCover alt + src
    src = re.sub(
        r'(<img alt=")[^"]+(" class="featured-cover-img"[^>]+src=")[^"]+(")',
        rf'\g<1>{title} cover\g<2>{cover}\g<3>', src
    )
    # featuredEbookMeta
    src = re.sub(
        r'(<span class="featured-meta" id="featuredEbookMeta">)[^<]*(</span>)',
        rf'\g<1>{meta}\g<2>', src
    )
    # featuredEbookTitle
    src = re.sub(
        r'(<h3 class="featured-title" id="featuredEbookTitle">)[^<]*(</h3>)',
        rf'\g<1>{title}\g<2>', src
    )
    # featuredEbookDesc
    src = re.sub(
        r'(<p class="featured-desc" id="featuredEbookDesc">)[^<]*(</p>)',
        rf'\g<1>{short}\g<2>', src
    )
    # featuredEbookLink href
    src = re.sub(
        r'(<a class="button" href=")[^"]+(" id="featuredEbookLink">)',
        rf'\g<1>{url_rel}\g<2>', src
    )
    # featuredEbookBuy href
    src = re.sub(
        r'(<a class="button secondary" href=")[^"]+(" id="featuredEbookBuy">)',
        rf'\g<1>{buy_rel}\g<2>', src
    )

    INDEX_HTML.write_text(src, encoding="utf-8")
    print(f"Featured book injected: {title} (ISO week {iso_week(datetime.now(timezone.utc))})")


def main() -> int:
    if not BOOKS_JSON.exists():
        print(f"ERROR: Books catalogue not found at {BOOKS_JSON}", file=sys.stderr)
        return 1
    books = json.loads(BOOKS_JSON.read_text(encoding="utf-8"))
    if not books:
        print("ERROR: Books catalogue is empty.", file=sys.stderr)
        return 1
    book = select_featured(books)
    inject(book)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
