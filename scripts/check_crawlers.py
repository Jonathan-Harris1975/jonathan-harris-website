#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
from dataclasses import dataclass
from typing import Dict, List
from urllib import error, request
import xml.etree.ElementTree as ET

from scripts.ebook_pipeline import (
    CRAWLER_CHECKSUMS_PATH,
    EXTERNAL_CRAWLER_FILES,
    ROOT,
    build_crawler_checksums,
    build_llms_txt,
    build_robots_txt,
    build_sitemap_xml,
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
    books = load_master()
    return {
        ROOT / "robots.txt": build_robots_txt(),
        ROOT / "sitemap.xml": build_sitemap_xml(books),
        ROOT / "llms.txt": build_llms_txt(books),
    }


def get_expected_live_payloads() -> Dict[str, str]:
    expected_files = build_expected_files()
    return {
        "robots": expected_files[ROOT / "robots.txt"],
        "sitemap": expected_files[ROOT / "sitemap.xml"],
        "llms": expected_files[ROOT / "llms.txt"],
    }


def run_repo_snapshot_checks() -> List[str]:
    errors: List[str] = []
    books = load_master()
    expected_files = build_expected_files()
    for path, expected in expected_files.items():
        relative_path = path.relative_to(ROOT)
        if not path.exists():
            errors.append(f"Crawler check failed: missing {relative_path}")
            continue
        actual = path.read_text(encoding="utf-8")
        if actual != expected:
            errors.append(f"Crawler check failed: snapshot drift in {relative_path}")

    checksum_payload = read_json(CRAWLER_CHECKSUMS_PATH, default={}) or {}
    if checksum_payload.get("files") != build_crawler_checksums(books).get("files"):
        errors.append("Crawler check failed: config/crawler-checksums.json drift detected")
    return errors


def fetch_url(url: str, timeout: float = DEFAULT_TIMEOUT) -> FetchResult:
    req = request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    try:
        with request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            final_url = response.geturl()
            status_code = getattr(response, "status", None)
            return FetchResult(url=url, final_url=final_url, status_code=status_code, body=body)
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return FetchResult(url=url, final_url=getattr(exc, "url", None), status_code=exc.code, body=body, error=str(exc))
    except Exception as exc:
        return FetchResult(url=url, final_url=None, status_code=None, body="", error=str(exc))


def validate_sitemap_xml(body: str) -> str | None:
    try:
        ET.fromstring(body)
        return None
    except ET.ParseError as exc:
        return f"Invalid XML: {exc}"


def run_live_checks(timeout: float = DEFAULT_TIMEOUT, verify_content: bool = True) -> List[LiveCheckResult]:
    expected_payloads = get_expected_live_payloads()
    results: List[LiveCheckResult] = []
    for name, url in EXTERNAL_CRAWLER_FILES.items():
        fetch = fetch_url(url, timeout=timeout)
        if fetch.error:
            results.append(
                LiveCheckResult(
                    name=name,
                    url=url,
                    ok=False,
                    message=f"Fetch failed: {fetch.error}",
                    status_code=fetch.status_code,
                    final_url=fetch.final_url,
                )
            )
            continue
        if fetch.status_code and fetch.status_code >= 400:
            results.append(
                LiveCheckResult(
                    name=name,
                    url=url,
                    ok=False,
                    message=f"Unexpected HTTP status {fetch.status_code}",
                    status_code=fetch.status_code,
                    final_url=fetch.final_url,
                )
            )
            continue
        if name == "sitemap":
            xml_error = validate_sitemap_xml(fetch.body)
            if xml_error:
                results.append(
                    LiveCheckResult(
                        name=name,
                        url=url,
                        ok=False,
                        message=xml_error,
                        status_code=fetch.status_code,
                        final_url=fetch.final_url,
                    )
                )
                continue

        if verify_content:
            expected = _normalise_text(expected_payloads[name])
            actual = _normalise_text(fetch.body)
            if actual != expected:
                results.append(
                    LiveCheckResult(
                        name=name,
                        url=url,
                        ok=False,
                        message="Live content does not match the governed repo snapshot",
                        status_code=fetch.status_code,
                        final_url=fetch.final_url,
                    )
                )
                continue

        results.append(
            LiveCheckResult(
                name=name,
                url=url,
                ok=True,
                message="OK",
                status_code=fetch.status_code,
                final_url=fetch.final_url,
            )
        )
    return results


def print_live_summary(results: List[LiveCheckResult]) -> None:
    for result in results:
        status_bits = [result.name, result.message]
        if result.status_code is not None:
            status_bits.append(f"HTTP {result.status_code}")
        if result.final_url and result.final_url != result.url:
            status_bits.append(f"final={result.final_url}")
        print(" | ".join(status_bits))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate repo crawler snapshots and, optionally, the published crawler URLs")
    parser.add_argument("--live", action="store_true", help="Also validate the externally hosted crawler URLs")
    parser.add_argument(
        "--strict-live",
        action="store_true",
        help="Fail the command when a live crawler URL is unreachable or drifts from the governed snapshot. Implies --live.",
    )
    parser.add_argument(
        "--skip-live-content",
        action="store_true",
        help="When running live checks, confirm reachability and syntax only, without exact content comparison.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"HTTP timeout in seconds for live checks. Default: {DEFAULT_TIMEOUT}",
    )
    args = parser.parse_args()

    if args.strict_live:
        args.live = True

    repo_errors = run_repo_snapshot_checks()
    if repo_errors:
        for error_message in repo_errors:
            print(error_message)
        if not args.live:
            return 1

    if not args.live:
        if repo_errors:
            return 1
        print("Crawler snapshot checks passed.")
        return 0

    live_results = run_live_checks(timeout=args.timeout, verify_content=not args.skip_live_content)
    print_live_summary(live_results)
    if repo_errors or (args.strict_live and any(not result.ok for result in live_results)):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
