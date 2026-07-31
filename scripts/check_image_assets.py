#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib import error, request
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ebook_pipeline import ROOT, EBOOKS_DIR, clean_paragraph, load_master

DEFAULT_TIMEOUT = 15.0
ALLOWED_IMAGE_HOST = "images.jonathan-harris.online"
LOGO_URL = f"https://{ALLOWED_IMAGE_HOST}/site-logo"
SRC_RE = re.compile(r'\bsrc="([^"]+)"', re.I)


@dataclass
class LiveResult:
    url: str
    ok: bool
    message: str
    status_code: int | None = None
    final_url: str | None = None


def fetch_url(url: str, *, timeout: float) -> LiveResult:
    req = request.Request(
        url,
        headers={
            "User-Agent": "JonathanHarrisImageCheck/1.0 (+https://jonathan-harris.online)",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
        },
        method="GET",
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            status = getattr(response, "status", None) or response.getcode()
            final_url = response.geturl()
            return LiveResult(url=url, ok=200 <= status < 400, message="OK", status_code=status, final_url=final_url)
    except error.HTTPError as exc:
        return LiveResult(url=url, ok=False, message=f"HTTP {exc.code}", status_code=exc.code, final_url=getattr(exc, "url", url))
    except error.URLError as exc:
        return LiveResult(url=url, ok=False, message=f"Request failed: {exc.reason}")


def extract_img_src(tag: str) -> str:
    match = SRC_RE.search(tag)
    return clean_paragraph(match.group(1)) if match else ""


def validate_remote_image_url(label: str, url: str) -> list[str]:
    errors: list[str] = []
    cleaned = clean_paragraph(url)
    if not cleaned:
        return [f"{label}: image URL is blank."]
    parsed = urlparse(cleaned)
    if parsed.scheme != "https":
        errors.append(f"{label}: image URL must use https: {cleaned}")
    if parsed.netloc.lower() != ALLOWED_IMAGE_HOST:
        errors.append(f"{label}: image URL host must be {ALLOWED_IMAGE_HOST}: {cleaned}")
    if "/cdn-cgi/image/" in cleaned:
        errors.append(f"{label}: remote image URL must not point at a generated /cdn-cgi/image path: {cleaned}")
    return errors


def static_checks() -> list[str]:
    errors: list[str] = []
    books = load_master()

    errors.extend(validate_remote_image_url("site logo", LOGO_URL))

    index_text = (ROOT / "index.html").read_text(encoding="utf-8", errors="ignore")
    homepage_tag_match = re.search(r'<img\b[^>]*id="featuredEbookCover"[^>]*>', index_text, re.I)
    if not homepage_tag_match:
        errors.append("Homepage featured cover image tag is missing from index.html.")
    else:
        homepage_tag = homepage_tag_match.group(0)
        homepage_src = extract_img_src(homepage_tag)
        errors.extend(validate_remote_image_url("homepage featured cover", homepage_src))
        if not re.search(r'\bwidth="[1-9][0-9]*"', homepage_tag, re.I) or not re.search(r'\bheight="[1-9][0-9]*"', homepage_tag, re.I):
            errors.append("Homepage featured cover must declare intrinsic width and height.")

    for book in books:
        cover = clean_paragraph(book.get("cover", ""))
        errors.extend(validate_remote_image_url(f"{book['slug']} cover", cover))
        page_path = EBOOKS_DIR / book["slug"] / "index.html"
        if not page_path.exists():
            errors.append(f"{book['slug']} cover check: canonical page is missing.")
            continue
        page_text = page_path.read_text(encoding="utf-8", errors="ignore")
        cover_match = re.search(r'<img\b[^>]*class="([^"]*\bebook-showcase__cover\b[^"]*)"[^>]*>', page_text, re.I)
        if not cover_match:
            errors.append(f"{book['slug']} cover check: showcase image tag is missing.")
            continue
        cover_tag = cover_match.group(0)
        page_src = extract_img_src(cover_tag)
        if page_src != cover:
            errors.append(f"{book['slug']} cover check: page src does not match the governed cover URL.")
        if not re.search(r'\bwidth="[1-9][0-9]*"', cover_tag, re.I) or not re.search(r'\bheight="[1-9][0-9]*"', cover_tag, re.I):
            errors.append(f"{book['slug']} cover check: intrinsic width and height are required.")

    return errors


def live_urls() -> list[tuple[str, str]]:
    books = load_master()
    urls = [("site logo", LOGO_URL)]
    urls.extend((f"{book['slug']} cover", clean_paragraph(book.get("cover", ""))) for book in books)
    return urls


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate governed image URLs for logos and ebook covers")
    parser.add_argument("--live", action="store_true", help="Also fetch the governed image URLs over HTTP")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="HTTP timeout in seconds for --live checks")
    args = parser.parse_args()

    errors = static_checks()
    if errors:
        for item in errors:
            print(item)
        print(f"Image asset validation failed with {len(errors)} issue(s).")
        return 1

    print("Image asset contract check passed.")

    if not args.live:
        return 0

    live_failures: list[LiveResult] = []
    for label, url in live_urls():
        result = fetch_url(url, timeout=args.timeout)
        if result.ok:
            print(f"[PASS] {label}: {url} -> {result.final_url or url} ({result.status_code})")
        else:
            live_failures.append(result)
            print(f"[FAIL] {label}: {url} ({result.message})")

    if live_failures:
        print(f"Live image asset validation failed with {len(live_failures)} issue(s).")
        return 1

    print("Live image asset validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
