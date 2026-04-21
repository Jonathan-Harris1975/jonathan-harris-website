#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARTIALS_DIR = ROOT / 'assets' / 'partials'
LEGACY_SCRIPT_PATH = ROOT / 'assets' / 'js' / 'consent-managed-scripts.min.js'

CANONICAL_HEAD_BLOCK = '''<link href="https://cdn-cookieyes.com" rel="dns-prefetch"/>
<link href="https://tracker.metricool.com" rel="dns-prefetch"/>
<link href="https://botsailor.com" rel="dns-prefetch"/>
<!-- CookieYes -->
<script id="cookieyes" type="text/javascript" src="https://cdn-cookieyes.com/client_data/c981d18033783598d2216add/script.js" async></script>
<script defer data-cookieyes="ignore" data-cookieconsent="ignore" src="/assets/js/script-governance.min.js"></script>'''

GOOGLE_PATTERNS = [
    re.compile(r'\s*<!--\s*Google Tag Manager\s*-->.*?googletagmanager\.com/gtm\.js.*?</script>\s*<!--\s*End Google Tag Manager[^>]*-->', re.I | re.S),
    re.compile(r'\s*<!--\s*Google Tag Manager \(noscript\)\s*-->.*?googletagmanager\.com/ns\.html\?id=.*?</noscript>\s*<!--\s*End Google Tag Manager \(noscript\)[^>]*-->', re.I | re.S),
    re.compile(r'\s*<!--\s*Google tag \(gtag\.js\)\s*-->\s*<script[^>]*src="https://www\.googletagmanager\.com/gtag/js\?id=[^"]+"[^>]*></script>\s*<script>.*?gtag\(["\']config["\']\s*,\s*["\'][^"\']+["\']\);.*?</script>', re.I | re.S),
    re.compile(r'\s*<script[^>]*src="https://www\.googletagmanager\.com/gtag/js\?id=[^"]+"[^>]*></script>', re.I | re.S),
    re.compile(r'\s*<script>.*?googletagmanager\.com/gtm\.js.*?</script>', re.I | re.S),
    re.compile(r'\s*<script>.*?\bgtag\s*\(.*?</script>', re.I | re.S),
    re.compile(r'\s*<noscript>\s*<iframe[^>]+googletagmanager\.com/ns\.html\?id=[^>]+></iframe>\s*</noscript>', re.I | re.S),
]

CLEANUP_PATTERNS = [
    re.compile(r'\s*<link[^>]+href="https://cdn-cookieyes\.com"[^>]*>\s*', re.I),
    re.compile(r'\s*<link[^>]+href="https://tracker\.metricool\.com"[^>]*>\s*', re.I),
    re.compile(r'\s*<link[^>]+href="https://botsailor\.com"[^>]*>\s*', re.I),
    re.compile(r'\s*<!--\s*CookieYes\s*-->\s*', re.I),
    re.compile(r'\s*<!--\s*Metricool Tracking with error handling\s*-->\s*', re.I),
    re.compile(r'\s*<script[^>]*id="cookieyes"[^>]*src="https://cdn-cookieyes\.com/client_data/c981d18033783598d2216add/script\.js"[^>]*></script>\s*', re.I | re.S),
    re.compile(r'\s*<script[^>]*src="/assets/js/consent-managed-scripts(?:\.min)?\.js"[^>]*></script>\s*', re.I),
    re.compile(r'\s*<script[^>]*src="/assets/js/script-governance\.min\.js"[^>]*></script>\s*', re.I),
    re.compile(r'\s*<script\b[^>]*>(?:(?!</script>).)*tracker\.metricool\.com/resources/be\.js(?:(?!</script>).)*</script>\s*', re.I | re.S),
    re.compile(r'\s*<script[^>]*src="https://tracker\.metricool\.com/resources/be\.js"[^>]*></script>\s*', re.I),
    re.compile(r'\s*<!--\s*Chatbot(?:[^>]*)?-->\s*', re.I),
    re.compile(r'\s*<script[^>]*src="https://botsailor\.com/script/webchat-link\.js\?code=1744067063128291"[^>]*></script>\s*', re.I),
    re.compile(r'\s*<script\b[^>]*>(?:(?!</script>).)*botsailor\.com/script/webchat-link\.js\?code=1744067063128291(?:(?!</script>).)*</script>\s*', re.I | re.S),
]


def collect_pages() -> list[Path]:
    pages: list[Path] = []
    for path in sorted(ROOT.rglob('*.html')):
        if path.is_relative_to(PARTIALS_DIR):
            continue
        if any(part.startswith('.') for part in path.relative_to(ROOT).parts):
            continue
        pages.append(path)
    return pages


def clean_existing_blocks(text: str) -> str:
    updated = text
    for pattern in GOOGLE_PATTERNS:
        updated = pattern.sub('\n', updated)
    for pattern in CLEANUP_PATTERNS:
        updated = pattern.sub('\n', updated)
    return re.sub(r'\n{3,}', '\n\n', updated)


def inject_blocks(text: str) -> tuple[str, list[str]]:
    errors: list[str] = []
    updated = clean_existing_blocks(text)

    if '</head>' not in updated:
        errors.append('missing </head>')
    else:
        updated = updated.replace('</head>', f'{CANONICAL_HEAD_BLOCK}\n</head>', 1)

    return re.sub(r'\n{3,}', '\n\n', updated), errors


def validate_page(text: str) -> list[str]:
    errors: list[str] = []
    if 'https://cdn-cookieyes.com/client_data/c981d18033783598d2216add/script.js' not in text:
        errors.append('missing CookieYes script')

    has_governed_loader = '/assets/js/script-governance.min.js' in text
    has_governed_loader_ignore = 'data-cookieyes="ignore"' in text and 'data-cookieconsent="ignore"' in text
    has_metricool_inline = 'https://tracker.metricool.com/resources/be.js' in text
    has_metricool_init = (
        'beTracker.t({hash: "fe05ab38be8b4875d12740b632198511"});' in text
        or "beTracker.t({hash: 'fe05ab38be8b4875d12740b632198511'});" in text
    )
    has_botsailor_inline = 'https://botsailor.com/script/webchat-link.js?code=1744067063128291' in text

    if has_governed_loader and not has_governed_loader_ignore:
        errors.append('governed loader missing CookieYes ignore attributes')

    if not (has_governed_loader or has_metricool_inline):
        errors.append('missing Metricool loader script')
    if not (has_governed_loader or has_metricool_init):
        errors.append('missing Metricool tracker initialiser')
    if not (has_governed_loader or has_botsailor_inline):
        errors.append('missing BotSailor script')

    if re.search(r'googletagmanager\.com|\bgtag\(|GTM-TFM7Q3RB|G-NLC3RN7H86', text, re.I):
        errors.append('contains forbidden Google analytics/tag manager code')
    return errors


def run_inject(dry_run: bool = False) -> int:
    pages = collect_pages()
    updated_count = 0
    failed: list[tuple[str, str]] = []
    for page in pages:
        original = page.read_text(encoding='utf-8')
        updated, errors = inject_blocks(original)
        if errors:
            failed.append((page.relative_to(ROOT).as_posix(), '; '.join(errors)))
            continue
        validation_errors = validate_page(updated)
        if validation_errors:
            failed.append((page.relative_to(ROOT).as_posix(), '; '.join(validation_errors)))
            continue
        if updated != original:
            updated_count += 1
            if not dry_run:
                page.write_text(updated, encoding='utf-8')

    if failed:
        for rel, reason in failed:
            print(f'[FAIL] {rel}: {reason}')
        print(f'\nThird-party script governance failed for {len(failed)} page(s).')
        return 1

    action = 'would update' if dry_run else 'updated'
    print(f'Third-party script governance complete: {action} {updated_count} page(s).')
    return 0


def run_validate() -> int:
    failures: list[tuple[str, str]] = []
    if LEGACY_SCRIPT_PATH.exists():
        failures.append((LEGACY_SCRIPT_PATH.relative_to(ROOT).as_posix(), 'legacy consent-managed runtime loader must be deleted'))
    for page in collect_pages():
        errors = validate_page(page.read_text(encoding='utf-8'))
        if errors:
            failures.append((page.relative_to(ROOT).as_posix(), '; '.join(errors)))
    if failures:
        for rel, reason in failures:
            print(f'[FAIL] {rel}: {reason}')
        print(f'\nThird-party script contract failed for {len(failures)} page(s).')
        return 1
    print(f'Third-party script contract passed for {len(collect_pages())} page(s).')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description='Govern page-level third-party script snippets.')
    parser.add_argument('--validate', action='store_true', help='Only validate the script contract without modifying files.')
    parser.add_argument('--dry-run', action='store_true', help='Report changes without writing them.')
    args = parser.parse_args()
    return run_validate() if args.validate else run_inject(dry_run=args.dry_run)


if __name__ == '__main__':
    raise SystemExit(main())
