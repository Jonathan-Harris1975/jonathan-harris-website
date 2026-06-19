#!/usr/bin/env python3
"""Validate the shared header, footer and top-spacing contract.

The site is deployed from the repository root, so generated pages must be safe
and complete even before a browser script runs. This gate prevents three
regressions:

* generated pages drifting from the canonical header/footer partials;
* hero-reveal CSS making the primary header invisible on initial load;
* fixed-header compensation leaving large empty bands above page content.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import inject_partials  # noqa: E402

CSS_PATH = ROOT / "assets" / "css" / "site.css"
CONTRACT_MARKER = "JH-SHARED-CHROME-VISIBILITY-CONTRACT"
REQUIRED_CSS_SNIPPETS = (
    ".jh-header.jh-header--hero-mode:not(.is-visible)",
    "opacity:1!important",
    "visibility:visible!important",
    ".site-footer",
    "body.page-home .hero--home",
    "body.page-topics .hero",
    "body:not(.home):not(.jh-no-hero-page)>main:not([class])",
    "body.page-topics #main",
)


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
        if text.count('footer aria-label="Website footer"') != 1:
            errors.append(f"{rel}: expected exactly one governed website footer")

    css = CSS_PATH.read_text(encoding="utf-8")
    marker_index = css.rfind(CONTRACT_MARKER)
    if marker_index < 0:
        errors.append(f"{CSS_PATH.relative_to(ROOT)}: shared chrome contract marker is missing")
        contract = ""
    else:
        contract = css[marker_index:]
        legacy_hide_index = css[:marker_index].rfind(".jh-header--hero-mode:not(.is-visible)")
        if legacy_hide_index >= marker_index:
            errors.append("shared chrome visibility contract must follow all legacy header-hide rules")

    for snippet in REQUIRED_CSS_SNIPPETS:
        if snippet not in contract:
            errors.append(f"shared chrome contract is missing required rule: {snippet}")

    if errors:
        print("Shared chrome layout contract failed:\n")
        for error in errors:
            fail(error)
        print(f"\nPages checked: {checked}")
        return 1

    print(
        "Shared chrome layout contract passed: "
        f"{checked} pages use the canonical visible header and footer with bounded top spacing."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
