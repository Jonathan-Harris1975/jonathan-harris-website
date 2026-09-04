#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from scripts.check_crawlers import _validate_sitemap_structure
from scripts.ebook_pipeline import SITE_URL, load_master


class NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def canonicalise_url(value: str) -> str:
    split = urlsplit(value.strip())
    path = split.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit((split.scheme.lower(), split.netloc.lower(), path, split.query, ""))


def fetch_without_redirect(url: str, timeout: float) -> tuple[int, str, str]:
    opener = build_opener(NoRedirectHandler())
    request = Request(url, headers={"User-Agent": "JonathanHarrisRedirectCheck/1.0"})
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return response.getcode(), response.geturl(), body
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return exc.code, exc.headers.get("Location", ""), body
    except URLError as exc:  # pragma: no cover
        raise RuntimeError(str(exc.reason)) from exc




def _validate_alias_mirror(content_kind: str, body: str) -> str | None:
    normalised_body = body.strip()
    if not normalised_body:
        return "response body was empty"

    if content_kind == "robots":
        if "User-agent:" not in body or "Sitemap:" not in body:
            return "robots mirror is reachable but does not contain the expected crawler directives"
        return None

    if content_kind == "sitemap":
        sitemap_error = _validate_sitemap_structure(body)
        if sitemap_error:
            return f"live sitemap mirror is invalid: {sitemap_error}"
        return None

    return None


def validate_book_chain(book: dict[str, str], timeout: float) -> list[str]:
    slug = book["slug"]
    legacy_url = book.get("legacy_alias_url") or f"{SITE_URL}/book/{slug}/buy-now"
    canonical_url = urljoin(SITE_URL, book["buy_route"])
    final_url = book["buy_url"]
    errors: list[str] = []

    try:
        legacy_status, legacy_location, _ = fetch_without_redirect(legacy_url, timeout)
    except RuntimeError as exc:
        return [f"{slug}: legacy alias request failed: {exc}"]
    if legacy_status < 300 or legacy_status >= 400:
        errors.append(f"{slug}: legacy alias returned HTTP {legacy_status} instead of a redirect")
    elif canonicalise_url(urljoin(legacy_url, legacy_location)) != canonicalise_url(canonical_url):
        errors.append(f"{slug}: legacy alias points to {legacy_location or '[missing Location header]'} instead of the canonical internal buy route")

    try:
        canonical_status, canonical_location, _ = fetch_without_redirect(canonical_url, timeout)
    except RuntimeError as exc:
        return errors + [f"{slug}: canonical buy route request failed: {exc}"]
    if canonical_status < 300 or canonical_status >= 400:
        errors.append(f"{slug}: canonical buy route returned HTTP {canonical_status} instead of a redirect")
    elif canonicalise_url(urljoin(canonical_url, canonical_location)) != canonicalise_url(final_url):
        errors.append(f"{slug}: canonical buy route points to {canonical_location or '[missing Location header]'} instead of the final destination")

    return errors


def validate_support_redirects(timeout: float) -> list[str]:
    checks = [
        (f"{SITE_URL}/robot.txt", f"{SITE_URL}/robots.txt", "robot.txt alias", "robots"),
        (f"{SITE_URL}/Sitemap.xml", f"{SITE_URL}/sitemap.xml", "Sitemap.xml alias", "sitemap"),
        (f"{SITE_URL}/site-map.xml", f"{SITE_URL}/sitemap.xml", "site-map.xml alias", "sitemap"),
    ]
    errors: list[str] = []
    for source, expected_target, label, content_kind in checks:
        try:
            status, location, body = fetch_without_redirect(source, timeout)
        except RuntimeError as exc:
            errors.append(f"{label}: request failed: {exc}")
            continue
        if 300 <= status < 400:
            actual_target = canonicalise_url(urljoin(source, location))
            if actual_target != canonicalise_url(expected_target):
                errors.append(f"{label}: points to {location or '[missing Location header]'} instead of {expected_target}")
            continue
        if status == 200:
            validation_error = _validate_alias_mirror(content_kind, body)
            if validation_error:
                errors.append(f"{label}: returned HTTP 200 but {validation_error.lower()}")
            continue
        errors.append(f"{label}: returned HTTP {status} instead of a redirect or governed compatibility mirror")
    return errors


def run_redirect_checks(timeout: float) -> list[str]:
    books = load_master()
    errors: list[str] = []
    for book in books:
        errors.extend(validate_book_chain(book, timeout))
    errors.extend(validate_support_redirects(timeout))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the live buy-now redirect chains and key support aliases.")
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout in seconds. Default: 15")
    args = parser.parse_args()

    books = load_master()
    errors = run_redirect_checks(args.timeout)

    if errors:
        for error in errors:
            print(error)
        print(f"Live redirect-chain validation failed with {len(errors)} issue(s).")
        return 1

    print(f"Live redirect-chain validation passed for {len(books)} books and the support aliases.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
