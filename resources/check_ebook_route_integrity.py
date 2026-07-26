#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "data" / "ebooks-master.json"


def load_books():
    payload = json.loads(MASTER.read_text(encoding="utf-8"))
    return payload if isinstance(payload, list) else payload.get("books", [])


def extract_jsonld(text: str):
    blocks = re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', text, re.I | re.S)
    result = []
    for block in blocks:
        try:
            value = json.loads(block)
            if isinstance(value, dict):
                result.append(value)
            elif isinstance(value, list):
                result.extend(x for x in value if isinstance(x, dict))
        except json.JSONDecodeError:
            pass
    return result


def canonical_from(text: str) -> str:
    match = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)', text, re.I)
    if not match:
        match = re.search(r'<link[^>]+href=["\']([^"\']+)["\'][^>]+rel=["\']canonical["\']', text, re.I)
    return match.group(1).strip() if match else ""


def h1_from(text: str) -> str:
    match = re.search(r'<h1[^>]*>(.*?)</h1>', text, re.I | re.S)
    return re.sub(r'<[^>]+>', '', match.group(1)).strip() if match else ""


def body_slug(text: str) -> str:
    match = re.search(r'<body[^>]+data-book-slug=["\']([^"\']+)', text, re.I)
    return match.group(1).strip() if match else ""


def main() -> int:
    errors: list[str] = []
    canonical_seen: dict[str, str] = {}
    hash_seen: dict[str, str] = {}
    books = load_books()

    for book in books:
        slug = str(book.get("slug", "")).strip()
        title = str(book.get("title", "")).strip()
        expected = str(book.get("canonical_url", "")).strip() or f"https://jonathan-harris.online/ebooks/{slug}/"
        path = ROOT / "ebooks" / slug / "index.html"
        if not path.exists():
            errors.append(f"missing generated ebook page: {slug}")
            continue
        text = path.read_text(encoding="utf-8")
        actual_canonical = canonical_from(text)
        if actual_canonical != expected:
            errors.append(f"{slug}: canonical {actual_canonical!r} != {expected!r}")
        if h1_from(text) != title:
            errors.append(f"{slug}: H1 does not match governed title")
        if body_slug(text) != slug:
            errors.append(f"{slug}: data-book-slug does not match route")

        book_schema = next((x for x in extract_jsonld(text) if x.get("@type") == "Book"), None)
        if not book_schema:
            errors.append(f"{slug}: Book JSON-LD missing")
        else:
            if str(book_schema.get("name", "")).strip() != title:
                errors.append(f"{slug}: Book JSON-LD name mismatch")
            if str(book_schema.get("url", "")).strip() != expected:
                errors.append(f"{slug}: Book JSON-LD URL mismatch")
            expected_id = expected.rstrip('/') + '/#book'
            if str(book_schema.get("@id", "")).strip() != expected_id:
                errors.append(f"{slug}: Book JSON-LD @id mismatch")

        previous = canonical_seen.get(actual_canonical)
        if actual_canonical and previous and previous != slug:
            errors.append(f"duplicate canonical {actual_canonical}: {previous}, {slug}")
        elif actual_canonical:
            canonical_seen[actual_canonical] = slug

        # Normalise only truly volatile generated timestamps before duplicate checking.
        normalised = re.sub(r'Last verified \d{4}-\d{2}-\d{2}', 'Last verified DATE', text)
        digest = hashlib.sha256(normalised.encode('utf-8')).hexdigest()
        previous_hash = hash_seen.get(digest)
        if previous_hash and previous_hash != slug:
            errors.append(f"indexable ebook pages are byte-equivalent after normalisation: {previous_hash}, {slug}")
        else:
            hash_seen[digest] = slug

    if errors:
        print("EBOOK ROUTE INTEGRITY: FAIL")
        for err in errors:
            print(f"- {err}")
        return 1
    print(f"EBOOK ROUTE INTEGRITY: PASS ({len(books)} governed books)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
