#!/usr/bin/env python3
"""Import the public website catalogue from the KDP D1 read API.

The API is deliberately allow-listed into the website's generated master. R2
object keys, manuscript filenames and manuscript URLs are never copied here.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_API_URL = "https://jonathan-harris.online/api/v1/ebooks.json"
SHEET_FIELDS = [
    ("Slug", "slug"),
    ("Title", "title"),
    ("Short description", "short_description"),
    ("Description", "description"),
    ("Summary", "summary"),
    ("Topic", "topic"),
    ("Tags", "tags"),
    ("Keywords", "keywords"),
    ("Audience", "audience"),
    ("Who this book is for", "who_for"),
    ("What this book covers", "what_this_book_covers"),
    ("What you'll learn", "what_youll_learn"),
    ("Why it matters", "why_it_matters"),
    ("Tone", "tone"),
    ("Author", "author"),
    ("Identifier", "identifier"),
    ("ASIN", "asin"),
    ("Amazon ebook page count", "pages"),
    ("Publication date", "datePublished"),
    ("Book URL", "book_url"),
    ("Buy now URL", "buy_route_full"),
    ("Redirect URL", "buy_url"),
    ("Cover art URL", "cover"),
    ("Legacy alias URL", "legacy_alias_url"),
]
SHEET_HEADERS = [header for header, _field in SHEET_FIELDS]


def fetch_books(url: str) -> list[dict[str, Any]]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "JonathanHarrisWebsiteBuild/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    books = payload.get("books") if isinstance(payload, dict) else None
    if not isinstance(books, list) or not books:
        raise ValueError("KDP D1 API returned no ebook records")

    seen: set[str] = set()
    for index, book in enumerate(books, start=1):
        if not isinstance(book, dict):
            raise ValueError(f"KDP D1 API record {index} is not an object")
        slug = str(book.get("slug") or "").strip()
        if not slug or slug in seen:
            raise ValueError(f"KDP D1 API record {index} has a blank or duplicate slug")
        seen.add(slug)
        missing = [
            name for name in ("title", "asin", "pages", "book_url", "buy_route_full",
                              "buy_url", "cover", "legacy_alias_url")
            if book.get(name) in (None, "")
        ]
        if missing:
            raise ValueError(f"KDP D1 API record {slug} is missing: {', '.join(missing)}")
    return books


def workbook_value(value: Any) -> Any:
    if isinstance(value, list):
        return " | ".join(str(item) for item in value if item not in (None, ""))
    return value if value is not None else ""


def build_import_workbook(books: list[dict[str, Any]], destination: Path) -> None:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Ebooks Master"
    sheet.append(SHEET_HEADERS)
    for book in books:
        row = []
        for _header, field in SHEET_FIELDS:
            row.append(workbook_value(book.get(field)))
        sheet.append(row)

    redirects = workbook.create_sheet("BuyNow Redirects")
    redirects.append(["Slug", "Buy now URL", "Redirect URL", "ASIN", "Status", "Notes"])
    for book in books:
        redirects.append([book["slug"], book.get("buy_route_full", ""), book.get("buy_url", ""), book.get("asin", ""), "active", ""])
    workbook.save(destination)


def main() -> int:
    api_url = os.environ.get("KDP_EBOOKS_API_URL", DEFAULT_API_URL).strip()
    workbook_fallback = Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) > 1 else None
    production_pages_build = (
        os.environ.get("CF_PAGES") == "1"
        and os.environ.get("CF_PAGES_BRANCH", "").strip() == "main"
    )
    try:
        books = fetch_books(api_url)
    except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError) as exc:
        if production_pages_build or not workbook_fallback or not workbook_fallback.is_file():
            raise SystemExit(f"KDP D1 catalogue import failed: {exc}") from exc
        print(
            f"WARN: KDP D1 API unavailable ({exc}); using the workbook only for this "
            "local/preview bootstrap build. Production builds fail closed.",
            file=sys.stderr,
        )
        source = workbook_fallback
    else:
        with tempfile.TemporaryDirectory(prefix="kdp-d1-import-") as temp_dir:
            temp_workbook = Path(temp_dir) / "kdp-d1-catalogue.xlsx"
            build_import_workbook(books, temp_workbook)
            subprocess.run(
                [sys.executable, "scripts/import_ebook_workbook.py", str(temp_workbook)],
                cwd=ROOT,
                check=True,
            )
        print(f"Imported {len(books)} ebook records from KDP D1.")
        return 0

    subprocess.run(
        [sys.executable, "scripts/import_ebook_workbook.py", str(source)],
        cwd=ROOT,
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
