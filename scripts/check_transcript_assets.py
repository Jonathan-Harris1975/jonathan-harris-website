#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib import error
from urllib.parse import urlparse, urlunparse

ROOT = Path(__file__).resolve().parents[1]
RSS_URL = (
    os.environ.get(
        'PODCAST_RSS_URL',
        'https://podcast-rss-feeds.jonathan-harris.online/turing-torch.xml',
    )
)
DEFAULT_TIMEOUT = 15.0
LIMIT = 24
NS = {'podcast': 'https://podcastindex.org/namespace/1.0'}
HTML_FILE_RE = re.compile(r'\.html?$', re.IGNORECASE)
TXT_FILE_RE = re.compile(r'\.txt$', re.IGNORECASE)

# If the CF_PAGES environment variable is set we are running inside a Cloudflare
# Pages build. Live HTTP checks are skipped automatically in this context because:
#   1. The R2 binding is not yet active on the deployment being built.
#   2. The build runner's egress may be restricted.
# Set SKIP_TRANSCRIPT_LIVE_CHECK=1 to force-skip live checks in any other CI env.
_IN_CF_PAGES = os.environ.get('CF_PAGES') == '1'
_SKIP_LIVE_ENV = os.environ.get('SKIP_TRANSCRIPT_LIVE_CHECK', '').strip() not in ('', '0', 'false', 'no')
_AUTO_SKIP_LIVE = _IN_CF_PAGES or _SKIP_LIVE_ENV
_VALIDATE_EXTERNAL_ENV = os.environ.get('VALIDATE_EXTERNAL_PODCAST_TRANSCRIPTS', '').strip().lower()
_VALIDATE_EXTERNAL = _VALIDATE_EXTERNAL_ENV in ('1', 'true', 'yes', 'on')


@dataclass
class TranscriptItem:
    title: str
    pub_date: str
    transcript_url: str


@dataclass
class LiveResult:
    url: str
    ok: bool
    message: str
    status_code: int | None = None
    final_url: str | None = None
    content_type: str | None = None


def is_absolute_http_url(value: str | None) -> bool:
    return bool(value and re.match(r'^https?://', value.strip(), flags=re.IGNORECASE))


def fetch_rss_items(limit: int) -> list[TranscriptItem]:
    request = urllib.request.Request(RSS_URL, headers={'User-Agent': 'JonathanHarrisTranscriptCheck/1.0'})
    with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as response:
        tree = ET.parse(response)

    items: list[TranscriptItem] = []
    for item in tree.findall('.//item')[:limit]:
        title = (item.findtext('title', '') or '').strip()
        if not title:
            continue
        tx = item.find('podcast:transcript', NS)
        if tx is None:
            continue
        candidates = [tx.get('url'), tx.get('href'), tx.text]
        transcript_url = ''
        for candidate in candidates:
            if is_absolute_http_url(candidate):
                transcript_url = str(candidate).strip()
                break
        if not transcript_url:
            continue
        items.append(
            TranscriptItem(
                title=title,
                pub_date=(item.findtext('pubDate', '') or '').strip(),
                transcript_url=transcript_url,
            )
        )
    return items


def infer_counterpart_url(url: str) -> str | None:
    parsed = urlparse(url)
    path = parsed.path
    if HTML_FILE_RE.search(path):
        counterpart = HTML_FILE_RE.sub('.txt', path)
    elif TXT_FILE_RE.search(path):
        counterpart = TXT_FILE_RE.sub('.html', path)
    else:
        return None
    return urlunparse(parsed._replace(path=counterpart))


def expected_kind(url: str) -> str | None:
    path = urlparse(url).path
    if HTML_FILE_RE.search(path):
        return 'html'
    if TXT_FILE_RE.search(path):
        return 'txt'
    return None


def validate_url_contract(label: str, url: str) -> list[str]:
    errors: list[str] = []
    if not is_absolute_http_url(url):
        return [f'{label}: transcript URL must be absolute http(s): {url}']
    parsed = urlparse(url)
    if parsed.scheme != 'https':
        errors.append(f'{label}: transcript URL must use https: {url}')
    kind = expected_kind(url)
    if kind is None:
        errors.append(f'{label}: transcript URL must point to a .html or .txt transcript asset until 1:1 routes exist: {url}')
    counterpart = infer_counterpart_url(url)
    if counterpart is None:
        errors.append(f'{label}: unable to derive transcript counterpart file (.html/.txt) from {url}')
    return errors


def fetch_url(url: str, *, timeout: float) -> LiveResult:
    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': 'JonathanHarrisTranscriptCheck/1.0 (+https://jonathan-harris.online)',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Accept': 'text/html,text/plain,application/xhtml+xml,*/*;q=0.8',
        },
        method='GET',
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status = getattr(response, 'status', None) or response.getcode()
            final_url = response.geturl()
            content_type = response.headers.get('Content-Type', '')
            return LiveResult(url=url, ok=200 <= status < 400, message='OK', status_code=status, final_url=final_url, content_type=content_type)
    except error.HTTPError as exc:
        return LiveResult(url=url, ok=False, message=f'HTTP {exc.code}', status_code=exc.code, final_url=getattr(exc, 'url', url), content_type=exc.headers.get('Content-Type', '') if getattr(exc, 'headers', None) else None)
    except error.URLError as exc:
        return LiveResult(url=url, ok=False, message=f'Request failed: {exc.reason}')


def validate_content_type(label: str, url: str, content_type: str | None) -> list[str]:
    errors: list[str] = []
    ct = (content_type or '').lower()
    kind = expected_kind(url)
    if kind == 'html' and 'html' not in ct:
        errors.append(f'{label}: expected HTML content type for {url}, got {content_type or "(missing)"}')
    if kind == 'txt' and ('text/plain' not in ct and not ct.startswith('text/')):
        errors.append(f'{label}: expected plain-text content type for {url}, got {content_type or "(missing)"}')
    return errors


def static_checks(items: list[TranscriptItem]) -> list[str]:
    errors: list[str] = []
    if not items:
        errors.append('No transcript-capable podcast items were found in the RSS feed.')
        return errors
    for item in items:
        label = item.title
        errors.extend(validate_url_contract(label, item.transcript_url))
        counterpart = infer_counterpart_url(item.transcript_url)
        if counterpart:
            errors.extend(validate_url_contract(f'{label} counterpart', counterpart))
    return errors


def live_checks(items: list[TranscriptItem], *, timeout: float) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    targets: list[tuple[str, str]] = []
    for item in items:
        targets.append((item.title, item.transcript_url))
        counterpart = infer_counterpart_url(item.transcript_url)
        if counterpart:
            targets.append((f'{item.title} counterpart', counterpart))

    for label, url in targets:
        if url in seen:
            continue
        seen.add(url)
        result = fetch_url(url, timeout=timeout)
        if not result.ok:
            errors.append(f'{label}: {url} -> {result.message}')
            continue
        if result.final_url and not is_absolute_http_url(result.final_url):
            errors.append(f'{label}: final transcript URL is invalid: {result.final_url}')
        if result.final_url and not (result.final_url.startswith('https://') and expected_kind(result.final_url)):
            errors.append(f'{label}: final transcript URL must resolve to a .html or .txt file, got {result.final_url}')
        errors.extend(validate_content_type(label, result.final_url or url, result.content_type))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description='Validate transcript asset URLs from the podcast RSS feed.')
    parser.add_argument('--limit', type=int, default=LIMIT, help='Maximum number of RSS items to inspect.')
    parser.add_argument('--timeout', type=float, default=DEFAULT_TIMEOUT, help='HTTP timeout in seconds for live checks.')
    parser.add_argument('--skip-live', action='store_true', help='Only validate the static RSS/file contract; skip HTTP fetches.')
    parser.add_argument(
        '--validate-external',
        action='store_true',
        help='Opt in to validating externally governed podcast RSS/transcript assets.',
    )
    args = parser.parse_args()

    if not (args.validate_external or _VALIDATE_EXTERNAL):
        print(
            'Transcript asset validation skipped: podcast episodes/transcripts are externally governed. '
            'Set VALIDATE_EXTERNAL_PODCAST_TRANSCRIPTS=1 or pass --validate-external to run this check.'
        )
        return 0

    try:
        items = fetch_rss_items(args.limit)
    except Exception as exc:
        print(f'Failed to load podcast RSS feed: {exc}')
        return 1

    # Static checks (RSS contract) are always a hard gate — these catch malformed
    # URLs in the RSS feed before they reach production.
    errors = static_checks(items)
    if errors:
        for error_text in errors:
            print(error_text)
        print(f'Transcript static contract check failed with {len(errors)} issue(s).')
        return 1

    # Live HTTP checks are skipped during Cloudflare Pages builds because the R2
    # binding is not yet active on the deployment under construction, causing every
    # object fetch to 404 and blocking the build that would fix the problem.
    # They are also skipped when --skip-live is passed or SKIP_TRANSCRIPT_LIVE_CHECK=1.
    skip_live = args.skip_live or _AUTO_SKIP_LIVE
    if skip_live:
        reason = '--skip-live flag' if args.skip_live else ('CF_PAGES=1' if _IN_CF_PAGES else 'SKIP_TRANSCRIPT_LIVE_CHECK env var')
        print(f'Live HTTP checks skipped ({reason}). Static contract check passed for {len(items)} podcast item(s).')
        return 0

    live_errors = live_checks(items, timeout=args.timeout)
    if live_errors:
        for error_text in live_errors:
            print(error_text)
        print(f'Transcript live check failed with {len(live_errors)} issue(s).')
        return 1

    print(f'Transcript asset contract check passed for {len(items)} podcast item(s).')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
