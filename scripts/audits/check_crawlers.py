#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
import re
from dataclasses import dataclass
from typing import Dict, List
from urllib import error, request
import xml.etree.ElementTree as ET

from scripts.ebook_pipeline import (
    CRAWLER_CHECKSUMS_PATH,
    EXTERNAL_CRAWLER_FILES,
    ROOT,
    build_crawler_checksums,
    build_crawler_snapshot_paths,
    build_published_crawler_paths,
    build_crawler_snapshot_payloads,
    clean_paragraph,
    load_master,
    read_json,
)

DEFAULT_TIMEOUT = 15.0
DEFAULT_USER_AGENT = "JonathanHarrisCrawlerValidator/1.0 (+https://jonathan-harris.online)"


@dataclass
class FetchResult:
    url: str
    final_url: str | None
    status_code: int | None
    body: str
    error: str | None = None


@dataclass
class LiveCheckResult:
    name: str
    url: str
    ok: bool
    message: str
    status_code: int | None = None
    final_url: str | None = None


def _normalise_text(value: str) -> str:
    lines = value.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(line.rstrip() for line in lines).strip()


def build_expected_files() -> Dict[Path, str]:
    return build_crawler_snapshot_paths(load_master())


def get_expected_live_payloads() -> Dict[str, str]:
    payloads = build_crawler_snapshot_payloads(load_master())
    return {
        "robots": payloads["robots.txt"],
        "sitemap": payloads["sitemap.xml"],
        "llms": payloads["llms.txt"],
    }


def run_repo_snapshot_checks() -> List[str]:
    errors: List[str] = []
    books = load_master()
    expected_files = build_crawler_snapshot_paths(books)
    for path, expected in expected_files.items():
        relative_path = path.relative_to(ROOT)
        if not path.exists():
            errors.append(f"Crawler check failed: missing {relative_path}")
            continue
        actual = path.read_text(encoding="utf-8")
        if actual != expected:
            errors.append(f"Crawler check failed: generated snapshot drift in {relative_path}")

    checksum_payload = read_json(CRAWLER_CHECKSUMS_PATH, default={}) or {}
    expected_checksums = build_crawler_checksums(books).get("files", {})
    actual_checksums = checksum_payload.get("files", {})
    if set(expected_checksums.keys()) != set(actual_checksums.keys()):
        errors.append("Crawler check failed: config/crawler-checksums.json is incomplete")
    for name, payload in expected_checksums.items():
        if actual_checksums.get(name, {}).get("sha256") != payload.get("sha256"):
            errors.append(f"Crawler check failed: checksum drift in {name}")

    redirects_path = ROOT / "_redirects"
    if not redirects_path.exists():
        errors.append("Crawler check failed: missing _redirects")
        return errors

    redirects_text = redirects_path.read_text(encoding="utf-8")
    forbidden_rules = [
        ("/robots.txt", EXTERNAL_CRAWLER_FILES["robots"]),
        ("/sitemap.xml", EXTERNAL_CRAWLER_FILES["sitemap"]),
    ]
    for source, url in forbidden_rules:
        if url in redirects_text and source in redirects_text:
            errors.append(f"Crawler check failed: _redirects still redirects {source} instead of serving the governed root file")

    alias_rules = [
        "/robot.txt    /robots.txt   301",
        "/Sitemap.xml  /sitemap.xml  301",
        "/site-map.xml  /sitemap.xml  301",
    ]
    for rule in alias_rules:
        if rule not in redirects_text:
            errors.append(f"Crawler check failed: _redirects is missing crawler alias rule {rule}")

    published_files = build_published_crawler_paths(books)
    for path, expected in published_files.items():
        if not path.exists():
            errors.append(f"Crawler check failed: missing published crawler file {path.relative_to(ROOT)}")
            continue
        actual = path.read_text(encoding="utf-8")
        if actual != expected:
            errors.append(f"Crawler check failed: published crawler file drift in {path.relative_to(ROOT)}")

    legacy_duplicates = [
        ROOT / "sitemap (1).xml",
        ROOT / "config" / "crawler-snapshots" / "site-map.xml",
    ]
    for path in legacy_duplicates:
        if path.exists():
            errors.append(
                f"Crawler check failed: delete legacy duplicate crawler file {path.relative_to(ROOT)} so sitemap.xml remains the only published sitemap source"
            )

    deployable_html_files = [
        path for path in ROOT.rglob("*.html")
        if "node_modules" not in path.parts and "templates" not in path.parts and "assets" not in path.parts
    ]
    unresolved_pattern = re.compile(r"{{[^{}]+}}")
    for path in deployable_html_files:
        matches = unresolved_pattern.findall(path.read_text(encoding="utf-8", errors="ignore"))
        if matches:
            errors.append(
                f"Crawler check failed: unresolved template tokens in deployable HTML {path.relative_to(ROOT)} -> {', '.join(sorted(set(matches))[:5])}"
            )

    if EXTERNAL_CRAWLER_FILES["robots"].rstrip("/") != "https://jonathan-harris.online/robots.txt":
        errors.append("Crawler check failed: robots.txt publication target is not pinned to the primary domain")
    if EXTERNAL_CRAWLER_FILES["sitemap"].rstrip("/") != "https://jonathan-harris.online/sitemap.xml":
        errors.append("Crawler check failed: sitemap.xml publication target is not pinned to the primary domain")
    if EXTERNAL_CRAWLER_FILES["llms"].rstrip("/") != "https://jonathan-harris.online/llms.txt":
        errors.append("Crawler check failed: llms.txt publication target is not pinned to the primary domain")

    return errors


def fetch_url(url: str, *, timeout: float = DEFAULT_TIMEOUT) -> FetchResult:
    req = request.Request(
        url,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Accept": "text/plain, application/xml, text/xml;q=0.9, */*;q=0.8",
        },
        method="GET",
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return FetchResult(
                url=url,
                final_url=response.geturl(),
                status_code=getattr(response, "status", None) or response.getcode(),
                body=body,
            )
    except error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return FetchResult(
            url=url,
            final_url=getattr(exc, "url", url),
            status_code=exc.code,
            body=body,
            error=f"HTTP {exc.code}",
        )
    except error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        return FetchResult(url=url, final_url=None, status_code=None, body="", error=str(reason))
    except Exception as exc:  # pragma: no cover
        return FetchResult(url=url, final_url=None, status_code=None, body="", error=str(exc))


def _validate_sitemap_structure(body: str) -> str | None:
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        return f"XML parse failed: {exc}"
    local_name = root.tag.rsplit("}", 1)[-1]
    if local_name not in {"urlset", "sitemapindex"}:
        return f"Unexpected XML root element <{local_name}>"
    return None


def _sitemap_loc_lastmod_map(body: str) -> Dict[str, str]:
    root = ET.fromstring(body)
    entries: Dict[str, str] = {}
    for url in root.findall('.//{*}url'):
        loc = clean_paragraph(url.findtext('{*}loc', default=''))
        lastmod = clean_paragraph(url.findtext('{*}lastmod', default=''))
        if loc:
            entries[loc] = lastmod
    return entries


def validate_live_body(name: str, body: str, expected_text: str) -> str | None:
    normalised_body = _normalise_text(body)
    normalised_expected = _normalise_text(expected_text)
    if not normalised_body:
        return "Response body was empty"

    if name == "robots":
        if "User-agent:" not in body or "Sitemap:" not in body:
            return "robots.txt is reachable but does not contain the expected crawler directives"
    elif name == "llms":
        if "## Canonical books" not in body:
            return "llms.txt is reachable but missing the expected canonical book manifest"
    elif name == "sitemap":
        sitemap_error = _validate_sitemap_structure(body)
        if sitemap_error:
            return f"sitemap file is reachable but invalid: {sitemap_error}"
        expected_sitemap_error = _validate_sitemap_structure(expected_text)
        if expected_sitemap_error:
            return f"governed sitemap snapshot is invalid: {expected_sitemap_error}"
        if _sitemap_loc_lastmod_map(body) != _sitemap_loc_lastmod_map(expected_text):
            return "Live sitemap entries do not match the governed snapshot"
        return None

    if normalised_body != normalised_expected:
        return "Live content does not match the governed snapshot"
    return None


def run_live_checks(*, timeout: float = DEFAULT_TIMEOUT, verify_content: bool = True) -> List[LiveCheckResult]:
    expected_payloads = get_expected_live_payloads()
    results: List[LiveCheckResult] = []

    for name, url in EXTERNAL_CRAWLER_FILES.items():
        fetch_result = fetch_url(url, timeout=timeout)
        if fetch_result.status_code != 200:
            message = fetch_result.error or f"Unexpected HTTP status {fetch_result.status_code}"
            results.append(
                LiveCheckResult(
                    name=name,
                    url=url,
                    ok=False,
                    message=message,
                    status_code=fetch_result.status_code,
                    final_url=fetch_result.final_url,
                )
            )
            continue

        if verify_content:
            validation_error = validate_live_body(name, fetch_result.body, expected_payloads[name])
            if validation_error:
                results.append(
                    LiveCheckResult(
                        name=name,
                        url=url,
                        ok=False,
                        message=validation_error,
                        status_code=fetch_result.status_code,
                        final_url=fetch_result.final_url,
                    )
                )
                continue

        success_message = "reachable"
        if verify_content:
            success_message += " and content matches the governed snapshot"
        results.append(
            LiveCheckResult(
                name=name,
                url=url,
                ok=True,
                message=success_message,
                status_code=fetch_result.status_code,
                final_url=fetch_result.final_url,
            )
        )

    return results


def print_repo_snapshot_summary() -> None:
    print("Crawler file check passed: robots.txt, canonical sitemap.xml, static sitemap compatibility mirrors, redirect aliases, and llms.txt are governed in-repo. Use --live to verify publication from the primary domain.")
    for name, url in EXTERNAL_CRAWLER_FILES.items():
        print(f"- {name}: {url}")


def print_live_summary(results: List[LiveCheckResult]) -> None:
    print("Live crawler publication check:")
    for result in results:
        status = result.status_code if result.status_code is not None else "n/a"
        final_url_text = f" -> {result.final_url}" if result.final_url and result.final_url != result.url else ""
        state = "PASS" if result.ok else "FAIL"
        print(f"- [{state}] {result.name}: HTTP {status}{final_url_text} | {result.message}")


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate governed crawler snapshots in the repo and, optionally, at their live publication URLs.")
    parser.add_argument("--live", action="store_true", help="Also validate the published crawler URLs with live GET requests.")
    parser.add_argument(
        "--strict-live",
        action="store_true",
        help="Treat live publication failures as fatal. Implies --live.",
    )
    parser.add_argument(
        "--skip-live-content",
        action="store_true",
        help="When running live checks, confirm reachability only and skip exact content comparison.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"HTTP timeout in seconds for live checks. Default: {DEFAULT_TIMEOUT}",
    )
    return parser


def main() -> int:
    parser = build_argument_parser()
    args = parser.parse_args()

    if args.strict_live:
        args.live = True

    errors = run_repo_snapshot_checks()
    if errors:
        print("Crawler file check failed:")
        for error_text in errors:
            print(f"- {error_text}")
        return 1

    print_repo_snapshot_summary()

    if not args.live:
        return 0

    live_results = run_live_checks(timeout=args.timeout, verify_content=not args.skip_live_content)
    print_live_summary(live_results)

    if args.strict_live and any(not result.ok for result in live_results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
