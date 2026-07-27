#!/usr/bin/env python3
"""Validate the shared header, footer and top-spacing contract.

The site is deployed from the repository root, so generated pages must be safe
and complete even before a browser script runs. This gate prevents three
regressions:

* generated pages drifting from the canonical header/footer partials;
* hero pages missing their full branded masthead;
* the compact header appearing before the hero has scrolled out of view.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import inject_partials  # noqa: E402

CSS_PATH = ROOT / "assets" / "css" / "site.css"
REQUIRED_CSS_SNIPPETS = (
    ".jh-header.jh-header--hero-mode{position:fixed!important",
    ".jh-header.jh-header--hero-mode:not(.is-visible){opacity:0!important",
    "transform:translateY(-110%)!important",
    ".jh-header.jh-header--hero-mode.is-visible{opacity:1!important",
    ".jh-page-hero__logo",
    ".hero .inline-newsletter",
    ".jh-growth-page .card",
)

DYNAMIC_CHROME_FILES = (
    ROOT / "functions" / "podcast" / "[[slug]].js",
    ROOT / "functions" / "podcast" / "episodes" / "[[slug]].js",
    ROOT / "functions" / "transcripts" / "[[slug]].js",
)
SHARED_CHROME_HELPER = ROOT / "functions" / "_shared" / "chrome.js"


def fail(message: str) -> None:
    print(f"[FAIL] {message}")


def main() -> int:
    errors: list[str] = []
    header = inject_partials.load_partial(inject_partials.HEADER_PARTIAL, "Header")
    footer = inject_partials.load_partial(inject_partials.FOOTER_PARTIAL, "Footer")

    if 'class="jh-nav-desktop"' not in header:
        errors.append("canonical header is missing the jh-nav-desktop class")
    if 'class="site-footer"' not in footer:
        errors.append("canonical footer is missing the site-footer class")

    checked = 0
    for page in inject_partials.collect_pages():
        rel = page.relative_to(ROOT).as_posix()
        text = page.read_text(encoding="utf-8")
        header_match = inject_partials.find_header_block(text)
        footer_match = inject_partials.find_footer_block(text)
        if header_match is None:
            errors.append(f"{rel}: shared header block is missing")
            continue
        if footer_match is None:
            errors.append(f"{rel}: shared footer block is missing")
            continue
        checked += 1
        if header_match.group(0) != header:
            errors.append(f"{rel}: shared header differs from the canonical partial")
        if footer_match.group(0) != footer:
            errors.append(f"{rel}: shared footer differs from the canonical partial")
        if header_match.start() > footer_match.start():
            errors.append(f"{rel}: footer appears before the shared header")
        if '<nav aria-label="Primary navigation" class="jh-nav-desktop">' not in header_match.group(0):
            errors.append(f"{rel}: desktop navigation class is missing")
        if 'data-jh-mobile-menu-toggle' not in header_match.group(0) or 'aria-controls="jh-mobile-nav"' not in header_match.group(0):
            errors.append(f"{rel}: hamburger toggle contract is missing")
        if 'id="jh-mobile-nav"' not in header_match.group(0):
            errors.append(f"{rel}: mobile navigation drawer is missing")
        if text.count('/assets/js/site-ui.min.js') != 1:
            errors.append(f"{rel}: expected exactly one shared site-ui script for hamburger behaviour")
        if text.count('footer aria-label="Website footer"') != 1:
            errors.append(f"{rel}: expected exactly one governed website footer")
        if 'jh-growth-page' in text:
            hero_pos = text.find('jh-page-hero')
            main_pos = text.find('<main')
            if hero_pos < 0:
                errors.append(f"{rel}: generated growth page is missing the full page hero")
            elif main_pos >= 0 and hero_pos > main_pos:
                errors.append(f"{rel}: generated growth page hero is trapped inside the content wrapper")
            if 'jh-page-hero__logo' not in text:
                errors.append(f"{rel}: generated growth page hero is missing the governed Jonathan Harris logo")
            if 'data-jh-header-reveal-anchor' not in text:
                errors.append(f"{rel}: generated growth page hero is missing the compact-header reveal anchor")

    site_ui = (ROOT / "assets" / "js" / "site-ui.min.js").read_text(encoding="utf-8", errors="ignore")
    for snippet in ("jh-header--hero-mode", "is-visible", "data-jh-header-show-immediately"):
        if snippet not in site_ui:
            errors.append(f"assets/js/site-ui.min.js: hero-aware compact-header logic is missing {snippet}")

    css = CSS_PATH.read_text(encoding="utf-8")
    for snippet in REQUIRED_CSS_SNIPPETS:
        if snippet not in css:
            errors.append(f"shared chrome reveal contract is missing required rule: {snippet}")
    if ".jh-header.jh-header--hero-mode:not(.is-visible){opacity:1!important" in css:
        errors.append("shared chrome still forces the compact header visible before the hero has scrolled away")

    if not SHARED_CHROME_HELPER.exists():
        errors.append("functions/_shared/chrome.js: shared runtime chrome helper is missing")
    else:
        helper_text = SHARED_CHROME_HELPER.read_text(encoding="utf-8")
        for snippet in ('/assets/partials/header.html', '/assets/partials/footer.html', '/assets/js/site-ui.min.js'):
            if snippet not in helper_text:
                errors.append(f"functions/_shared/chrome.js: runtime helper is missing {snippet}")

    for dynamic_path in DYNAMIC_CHROME_FILES:
        rel = dynamic_path.relative_to(ROOT).as_posix()
        if not dynamic_path.exists():
            errors.append(f"{rel}: dynamic route file is missing")
            continue
        dynamic_text = dynamic_path.read_text(encoding="utf-8")
        if 'ensureSharedChrome' not in dynamic_text:
            errors.append(f"{rel}: dynamic route does not use ensureSharedChrome")
        if '/assets/js/site-ui.min.js' in dynamic_text and 'ensureSharedChrome' not in dynamic_text:
            errors.append(f"{rel}: embeds site-ui without the canonical runtime chrome helper")

    if errors:
        print("Shared chrome layout contract failed:\n")
        for error in errors:
            fail(error)
        print(f"\nPages checked: {checked}")
        return 1

    print(
        "Shared chrome layout contract passed: "
        f"{checked} pages use the canonical header/footer and hero-aware compact navigation."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
