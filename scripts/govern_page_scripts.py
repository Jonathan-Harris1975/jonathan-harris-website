#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARTIALS_DIR = ROOT / 'assets' / 'partials'
SITE_SHELL_DIR = ROOT / 'assets' / 'site-shell'
LEGACY_SCRIPT_PATH = ROOT / 'assets' / 'js' / 'consent-managed-scripts.min.js'
GTM_ID = 'GTM-PC4K9KRK'
FUNNEL_SCRIPT = '<script defer src="/assets/js/funnel-events.min.js"></script>'

GTM_HEAD_BLOCK = f'''<!-- Google Tag Manager -->
<script>(function(w,d,s,l,i){{w[l]=w[l]||[];w[l].push({{'gtm.start':
new Date().getTime(),event:'gtm.js'}});var f=d.getElementsByTagName(s)[0],
j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
}})(window,document,'script','dataLayer','{GTM_ID}');</script>
<!-- End Google Tag Manager -->'''

GTM_BODY_BLOCK = f'''<!-- Google Tag Manager (noscript) -->
<noscript><iframe src="https://www.googletagmanager.com/ns.html?id={GTM_ID}"
height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>
<!-- End Google Tag Manager (noscript) -->'''

RUNTIME_HEAD_BLOCK = '''<link href="https://tracker.metricool.com" rel="dns-prefetch"/>
<script defer data-cookieyes="ignore" data-cookieconsent="ignore" src="/assets/js/script-governance.min.js"></script>'''

GOOGLE_PATTERNS = [
    re.compile(r'\s*<!--\s*Google Tag Manager\s*-->.*?googletagmanager\.com/gtm\.js.*?</script>\s*<!--\s*End Google Tag Manager\s*-->', re.I | re.S),
    re.compile(r'\s*<!--\s*Google Tag Manager \(noscript\)\s*-->.*?googletagmanager\.com/ns\.html\?id=.*?</noscript>\s*<!--\s*End Google Tag Manager \(noscript\)\s*-->', re.I | re.S),
    re.compile(r'\s*<!--\s*Google tag \(gtag\.js\)\s*-->\s*<script[^>]*src="https://www\.googletagmanager\.com/gtag/js\?id=[^"]+"[^>]*></script>\s*<script>.*?gtag\(["\']config["\']\s*,\s*["\'][^"\']+["\']\);.*?</script>', re.I | re.S),
    re.compile(r'\s*<script[^>]*src="https://www\.googletagmanager\.com/gtag/js\?id=[^"]+"[^>]*></script>', re.I | re.S),
    re.compile(r'\s*<script>\s*\(function\(w,d,s,l,i\).*?googletagmanager\.com/gtm\.js.*?</script>', re.I | re.S),
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
    re.compile(r'\s*<script[^>]*src="https://cdn-cookieyes\.com/client_data/c981d18033783598d2216add/script\.js"[^>]*id="cookieyes"[^>]*></script>\s*', re.I | re.S),
    re.compile(r'\s*<script[^>]*src="/assets/js/consent-managed-scripts(?:\.min)?\.js"[^>]*></script>\s*', re.I),
    re.compile(r'\s*<script[^>]*src="/assets/js/script-governance\.min\.js"[^>]*></script>\s*', re.I),
    re.compile(r'\s*<script[^>]*src="/assets/js/funnel-events\.min\.js"[^>]*></script>\s*', re.I),
    re.compile(r'\s*<script\b[^>]*>(?:(?!</script>).)*tracker\.metricool\.com/resources/be\.js(?:(?!</script>).)*</script>\s*', re.I | re.S),
    re.compile(r'\s*<script[^>]*src="https://tracker\.metricool\.com/resources/be\.js"[^>]*></script>\s*', re.I),
    re.compile(r'\s*<!--\s*Chatbot(?:[^>]*)?-->\s*', re.I),
    re.compile(r'\s*<script[^>]*src="https://botsailor\.com/script/webchat-link\.js\?code=1744067063128291"[^>]*></script>\s*', re.I),
    re.compile(r'\s*<script\b[^>]*>(?:(?!</script>).)*botsailor\.com/script/webchat-link\.js\?code=1744067063128291(?:(?!</script>).)*</script>\s*', re.I | re.S),
]


def collect_pages() -> list[Path]:
    pages: list[Path] = []
    for path in sorted(ROOT.rglob('*.html')):
        if path.is_relative_to(PARTIALS_DIR) or path.is_relative_to(SITE_SHELL_DIR):
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

    if not re.search(r'<head\b[^>]*>', updated, re.I):
        errors.append('missing <head>')
    else:
        updated = re.sub(r'(<head\b[^>]*>\s*)', lambda match: match.group(1) + GTM_HEAD_BLOCK + '\n', updated, count=1, flags=re.I)

    if not re.search(r'<body\b[^>]*>', updated, re.I):
        errors.append('missing <body>')
    else:
        updated = re.sub(r'(<body\b[^>]*>\s*)', lambda match: match.group(1) + GTM_BODY_BLOCK + '\n', updated, count=1, flags=re.I)

    if '</head>' not in updated:
        errors.append('missing </head>')
    else:
        updated = updated.replace('</head>', f'{RUNTIME_HEAD_BLOCK}\n</head>', 1)

    if '</body>' not in updated:
        errors.append('missing </body>')
    else:
        updated = updated.replace('</body>', f'{FUNNEL_SCRIPT}\n</body>', 1)

    return re.sub(r'\n{3,}', '\n\n', updated), errors


def validate_page(text: str) -> list[str]:
    errors: list[str] = []
    if GTM_ID not in text or 'https://www.googletagmanager.com/gtm.js' not in text:
        errors.append('missing Google Tag Manager head snippet')
    if f'https://www.googletagmanager.com/ns.html?id={GTM_ID}' not in text:
        errors.append('missing Google Tag Manager noscript snippet')
    if 'https://cdn-cookieyes.com/client_data/c981d18033783598d2216add/script.js' in text:
        errors.append('contains deprecated CookieYes direct loader')

    has_governed_loader = '/assets/js/script-governance.min.js' in text
    has_governed_loader_ignore = 'data-cookieyes="ignore"' in text and 'data-cookieconsent="ignore"' in text
    has_metricool_inline = 'https://tracker.metricool.com/resources/be.js' in text
    has_metricool_init = (
        'beTracker.t({hash: "fe05ab38be8b4875d12740b632198511"});' in text
        or "beTracker.t({hash: 'fe05ab38be8b4875d12740b632198511'});" in text
    )

    if has_governed_loader and not has_governed_loader_ignore:
        errors.append('governed loader missing consent-ignore attributes')

    if not (has_governed_loader or has_metricool_inline):
        errors.append('missing Metricool loader script')
    if not (has_governed_loader or has_metricool_init):
        errors.append('missing Metricool tracker initialiser')
    if 'botsailor.com' in text.lower():
        errors.append('contains removed BotSailor reference')

    if re.search(r'GTM-TFM7Q3RB|G-NLC3RN7H86|\bgtag\(', text, re.I):
        errors.append('contains stale Google analytics/tag code')
    if text.count('/assets/js/funnel-events.min.js') != 1:
        errors.append('must contain exactly one first-party funnel event loader')
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
