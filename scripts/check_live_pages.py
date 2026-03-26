#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib import error, request

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ebook_pipeline import ROOT, SITE_URL, load_master  # noqa: E402

DEFAULT_TIMEOUT = 15.0
DEFAULT_USER_AGENT = "JonathanHarrisPageSmoke/1.0 (+https://jonathan-harris.online)"


@dataclass
class PageCheck:
    label: str
    local_path: Path
    live_url: str
    extractors: list[tuple[str, str]]


@dataclass
class PageResult:
    label: str
    ok: bool
    message: str
    live_url: str
    missing_markers: list[str]


def fetch_url(url: str, *, timeout: float) -> str:
    req = request.Request(
        url,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        },
        method="GET",
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} for {url}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Request failed for {url}: {exc.reason}") from exc


SCRIPT_RE = re.compile(r"<script\b.*?</script>", re.I | re.S)
STYLE_RE = re.compile(r"<style\b.*?</style>", re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")


def normalise_visible_text(raw_html: str) -> str:
    without_scripts = SCRIPT_RE.sub(" ", raw_html)
    without_styles = STYLE_RE.sub(" ", without_scripts)
    stripped = TAG_RE.sub(" ", without_styles)
    return WHITESPACE_RE.sub(" ", html.unescape(stripped)).strip()


def extract_required_snippets(page: PageCheck) -> list[str]:
    source = page.local_path.read_text(encoding="utf-8")
    snippets: list[str] = []
    for label, pattern in page.extractors:
        match = re.search(pattern, source, flags=re.I | re.S)
        if not match:
            raise ValueError(f"Could not extract {label} from {page.local_path.relative_to(ROOT)}")
        snippet = WHITESPACE_RE.sub(" ", html.unescape(match.group(1))).strip()
        if snippet:
            snippets.append(snippet)
    return snippets


def selected_page_checks() -> list[PageCheck]:
    books = {book["slug"]: book for book in load_master()}
    key_book_slug = "the-dumbening-how-ai-is-reshaping-our-minds"
    ai_book_slug = "the-artificial-intelligence-revolution-from-algorithms-to-consciousness"
    pages = [
        PageCheck(
            label="homepage featured merch block",
            local_path=ROOT / "index.html",
            live_url=f"{SITE_URL}/",
            extractors=[
                ("featured title", r'id="featuredEbookTitle">(.*?)</h3>'),
                ("featured description", r'id="featuredEbookDesc">(.*?)</p>'),
            ],
        ),
        PageCheck(
            label="The Dumbening canonical page",
            local_path=ROOT / "ebooks" / key_book_slug / "index.html",
            live_url=books[key_book_slug]["canonical_url"],
            extractors=[
                ("book title", r"<h1>(.*?)</h1>"),
                ("hero summary", r"<h1>.*?</h1>\s*<p>(.*?)</p>"),
                ("faq audience", r"<summary>Who is this book for\?</summary><div><p>(.*?)</p></div>"),
            ],
        ),
        PageCheck(
            label="Artificial intelligence topic page",
            local_path=ROOT / "catalogue" / "artificial-intelligence" / "index.html",
            live_url=f"{SITE_URL}/catalogue/artificial-intelligence/",
            extractors=[
                ("topic heading", r"<h1>(.*?)</h1>"),
                ("topic intro", r"<h1>.*?</h1>\s*<p>(.*?)</p>"),
            ],
        ),
        PageCheck(
            label="Artificial intelligence core book page",
            local_path=ROOT / "ebooks" / ai_book_slug / "index.html",
            live_url=books[ai_book_slug]["canonical_url"],
            extractors=[
                ("book title", r"<h1>(.*?)</h1>"),
                ("faq audience", r"<summary>Who is this book for\?</summary><div><p>(.*?)</p></div>"),
            ],
        ),
    ]
    return pages


def run_checks(*, timeout: float) -> list[PageResult]:
    results: list[PageResult] = []
    for page in selected_page_checks():
        try:
            live_html = fetch_url(page.live_url, timeout=timeout)
        except Exception as exc:
            results.append(PageResult(page.label, False, str(exc), page.live_url, []))
            continue

        live_text = normalise_visible_text(live_html)
        snippets = extract_required_snippets(page)
        missing = [snippet for snippet in snippets if snippet not in live_text]
        if missing:
            results.append(
                PageResult(
                    label=page.label,
                    ok=False,
                    message="Live page is reachable but missing one or more governed content markers",
                    live_url=page.live_url,
                    missing_markers=missing,
                )
            )
            continue
        results.append(PageResult(page.label, True, "Live page contains the governed markers", page.live_url, []))
    return results


def print_results(results: Iterable[PageResult]) -> None:
    for result in results:
        status = "PASS" if result.ok else "FAIL"
        print(f"[{status}] {result.label}: {result.message}")
        print(f"      {result.live_url}")
        for marker in result.missing_markers[:3]:
            print(f"      missing: {marker}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare selected governed HTML markers against live pages.")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="HTTP timeout in seconds. Default: 15")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero if any page is unreachable or missing governed markers.")
    args = parser.parse_args()

    results = run_checks(timeout=max(args.timeout, 1.0))
    print_results(results)
    failures = [result for result in results if not result.ok]
    if failures and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
