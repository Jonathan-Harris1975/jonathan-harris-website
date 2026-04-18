#!/usr/bin/env python3
"""
inject_partials.py
==================
Build-time injection of shared HTML partials into every page.

The canonical header lives in:
    assets/partials/header.html

Every .html page in the repo (outside assets/partials/) contains a baked-in
copy of this block.  This script replaces that copy with the current partial
content, keeping all other page content untouched.

Usage
-----
    python3 scripts/inject_partials.py              # inject + report
    python3 scripts/inject_partials.py --validate   # assert all pages match partial (CI gate)
    python3 scripts/inject_partials.py --dry-run    # show what would change, write nothing

Exit codes
----------
    0  All pages in sync (or successfully updated)
    1  One or more pages could not be processed / failed validation
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
PARTIALS_DIR = ROOT / "assets" / "partials"
HEADER_PARTIAL = PARTIALS_DIR / "header.html"
FOOTER_PARTIAL = PARTIALS_DIR / "footer.html"

# Directories / files excluded from processing
EXCLUDE_DIRS = {
    PARTIALS_DIR,
}

_COMPAT_REDIRECT_RE = re.compile(r"^podcast/TT-\d{4}-\d{2}-\d{2}/index\.html$")

# ---------------------------------------------------------------------------
# Font head contract
# ---------------------------------------------------------------------------
FONT_HEAD_BLOCK = """<link href="https://fonts.googleapis.com" rel="preconnect"/>
<link crossorigin="" href="https://fonts.gstatic.com" rel="preconnect"/>
<link href="https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,400;0,600;0,700;0,800&display=swap" rel="stylesheet"/>"""

VIEWPORT_META_VARIANTS = {
    '<meta content="width=device-width, initial-scale=1, viewport-fit=cover" name="viewport"/>',
    '<meta content="width=device-width, initial-scale=1.0, viewport-fit=cover" name="viewport"/>',
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>',
    '<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover"/>',
    '<meta content="width=device-width, initial-scale=1, viewport-fit=cover" name="viewport">',
    '<meta content="width=device-width, initial-scale=1.0, viewport-fit=cover" name="viewport">',
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">',
    '<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">',
}

# ---------------------------------------------------------------------------
# Regex
# ---------------------------------------------------------------------------
# Matches the full header block as it appears in pages:
#   <a class="skip-link" ...>...</a>   (optional whitespace)
#   <header ... class="jh-header" ...> ... </header>
#
# Uses a non-greedy match so it stops at the FIRST </header>, protecting any
# subsequent <header class="hero"> elements (e.g. blog-post.html).
_HEADER_BLOCK_RE = re.compile(
    r'<a class="skip-link".*?</header>',
    re.DOTALL,
)

_FOOTER_BLOCK_RE = re.compile(
    r'<footer aria-label="Website footer".*?</footer>',
    re.DOTALL,
)

_FONT_HEAD_BLOCK_RE = re.compile(
    r'(?:\s*<link[^>]+href="https://fonts.googleapis.com"[^>]*>\s*\n?\s*<link[^>]+href="https://fonts.gstatic.com"[^>]*>\s*\n?\s*<link[^>]+href="https://fonts.googleapis.com/css2\?family=Inter:ital,wght@0,400;0,600;0,700;0,800&display=swap"[^>]*>)',
    re.IGNORECASE,
)

_SITE_CSS_LINK_RE = re.compile(r'<link[^>]+href="/assets/css/site\.css"[^>]*>', re.IGNORECASE)
_VIEWPORT_META_RE = re.compile(r'<meta[^>]+name=\"viewport\"[^>]*>', re.IGNORECASE)


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def load_partial(partial_path: Path, label: str) -> str:
    """Return a canonical shared partial as a string."""
    if not partial_path.exists():
        raise FileNotFoundError(
            f"{label} partial not found: {partial_path}\n"
            f"Expected: assets/partials/{partial_path.name}"
        )
    return partial_path.read_text(encoding="utf-8").rstrip("\n")


def should_skip_page(path: Path) -> bool:
    """Return True when a page is intentionally outside shared header/footer governance."""
    rel = path.relative_to(ROOT).as_posix()
    if _COMPAT_REDIRECT_RE.match(rel):
        return True
    return False


def collect_pages() -> list[Path]:
    """Return all governed .html files in the repo, excluding partials and hidden dirs."""
    pages: list[Path] = []
    for path in sorted(ROOT.rglob("*.html")):
        # Skip the partials directory itself
        if any(path.is_relative_to(ex) for ex in EXCLUDE_DIRS):
            continue
        # Skip hidden directories (e.g. .git)
        if any(part.startswith(".") for part in path.relative_to(ROOT).parts):
            continue
        # Skip intentional compatibility redirect stubs generated under /podcast/TT-YYYY-MM-DD/
        if should_skip_page(path):
            continue
        pages.append(path)
    return pages


def find_header_block(text: str) -> re.Match | None:
    """Return the regex match for the header block, or None if not found."""
    return _HEADER_BLOCK_RE.search(text)


def find_footer_block(text: str) -> re.Match | None:
    """Return the regex match for the footer block, or None if not found."""
    return _FOOTER_BLOCK_RE.search(text)


def ensure_font_head_block(text: str) -> tuple[str, bool]:
    """Normalise the shared Inter font loading block ahead of site.css."""
    if validate_font_head_block(text) is None:
        return text, False

    cleaned = _FONT_HEAD_BLOCK_RE.sub("", text, count=1)
    match = _SITE_CSS_LINK_RE.search(cleaned)
    if match is None:
        return text, False

    updated = cleaned[:match.start()] + FONT_HEAD_BLOCK + "\n" + cleaned[match.start():]
    return updated, updated != text


def validate_viewport_head_block(text: str) -> str | None:
    matches = _VIEWPORT_META_RE.findall(text)
    if not matches:
        return "viewport meta tag is missing from the page head"
    if len(matches) != 1:
        return f"expected exactly one viewport meta tag, found {len(matches)}"
    if matches[0].strip() not in VIEWPORT_META_VARIANTS:
        return "viewport meta tag differs from the governed accepted forms"
    return None


def validate_font_head_block(text: str) -> str | None:
    match = _SITE_CSS_LINK_RE.search(text)
    if match is None:
        return "site.css link not found"

    font_match = _FONT_HEAD_BLOCK_RE.search(text)
    if font_match is None:
        return "shared Inter font head block is missing"

    if font_match.start() > match.start():
        return "shared Inter font head block must appear before site.css"

    if font_match.group(0).strip() != FONT_HEAD_BLOCK:
        return "shared Inter font head block differs from the canonical block"

    return None


# ---------------------------------------------------------------------------
# Inject
# ---------------------------------------------------------------------------

def inject(dry_run: bool = False) -> int:
    """
    Inject the partial into every page.

    Returns 0 on success, 1 if any page could not be processed.
    """
    header_partial = load_partial(HEADER_PARTIAL, "Header")
    footer_partial = load_partial(FOOTER_PARTIAL, "Footer")
    pages = collect_pages()

    in_sync = 0
    updated = 0
    failed: list[tuple[Path, str]] = []

    for page in pages:
        rel = page.relative_to(ROOT)
        try:
            original = page.read_text(encoding="utf-8")
        except Exception as exc:
            failed.append((rel, f"Read error: {exc}"))
            continue

        header_match = find_header_block(original)
        if header_match is None:
            failed.append((rel, "Header block not found - no <a class=\"skip-link\"> before <header class=\"jh-header\">"))
            continue

        footer_match = find_footer_block(original)
        if footer_match is None:
            failed.append((rel, "Footer block not found - no canonical <footer aria-label=\"Website footer\"> block"))
            continue

        existing_header_block = header_match.group(0)
        existing_footer_block = footer_match.group(0)

        # Replace the canonical header first, then replace the footer in the updated text.
        updated_text = original[:header_match.start()] + header_partial + original[header_match.end():]
        footer_match = find_footer_block(updated_text)
        if footer_match is None:
            failed.append((rel, "Footer block could not be relocated after header injection"))
            continue
        updated_text = updated_text[:footer_match.start()] + footer_partial + updated_text[footer_match.end():]
        updated_text, font_changed = ensure_font_head_block(updated_text)

        if existing_header_block == header_partial and existing_footer_block == footer_partial and not font_changed:
            in_sync += 1
            print(f"  [OK]      {rel}")
            continue

        if dry_run:
            updated += 1
            print(f"  [DRY-RUN] {rel}  (would update)")
        else:
            try:
                stat_result = page.stat()
                page.write_text(updated_text, encoding="utf-8")
                os.utime(page, (stat_result.st_atime, stat_result.st_mtime))
                updated += 1
                print(f"  [UPDATED] {rel}")
            except Exception as exc:
                failed.append((rel, f"Write error: {exc}"))

    # Summary
    print()
    print("=" * 60)
    print("inject_partials  -  Header + footer injection summary")
    print("=" * 60)
    print(f"  Pages scanned : {len(pages)}")
    print(f"  Already in sync: {in_sync}")
    print(f"  {'Would update' if dry_run else 'Updated'}     : {updated}")
    print(f"  Failed          : {len(failed)}")

    if failed:
        print()
        print("FAILURES:")
        for path, reason in failed:
            print(f"  {path}")
            print(f"    → {reason}")
        return 1

    return 0


# ---------------------------------------------------------------------------
# Validate  (CI gate — read-only, exits non-zero on any drift)
# ---------------------------------------------------------------------------

def validate() -> int:
    """
    Assert that every page's header block is byte-for-byte identical to the
    partial.  Does not modify any files.  Returns 1 if any drift is found.
    """
    header_partial = load_partial(HEADER_PARTIAL, "Header")
    footer_partial = load_partial(FOOTER_PARTIAL, "Footer")
    pages = collect_pages()

    drift: list[tuple[Path, str]] = []
    ok = 0

    for page in pages:
        rel = page.relative_to(ROOT)
        try:
            text = page.read_text(encoding="utf-8")
        except Exception as exc:
            drift.append((rel, f"Read error: {exc}"))
            continue

        header_match = find_header_block(text)
        if header_match is None:
            drift.append((rel, "Header block not located"))
            continue

        footer_match = find_footer_block(text)
        if footer_match is None:
            drift.append((rel, "Footer block not located"))
            continue

        header_reason = None if header_match.group(0) == header_partial else "Header differs from partial"
        footer_reason = None if footer_match.group(0) == footer_partial else "Footer differs from partial"
        font_reason = validate_font_head_block(text)
        viewport_reason = validate_viewport_head_block(text)
        if not header_reason and not footer_reason and not font_reason and not viewport_reason:
            ok += 1
        else:
            reasons = "; ".join(reason for reason in [header_reason, footer_reason, font_reason, viewport_reason] if reason)
            drift.append((rel, reasons))

    print()
    print("=" * 60)
    print("inject_partials  -  Header + footer validation")
    print("=" * 60)
    print(f"  Pages checked  : {len(pages)}")
    print(f"  In sync        : {ok}")
    print(f"  Drifted / failed: {len(drift)}")

    if drift:
        print()
        print("DRIFT DETECTED — run  python3 scripts/inject_partials.py  to fix:")
        for path, reason in drift:
            print(f"  {path}  ({reason})")
        return 1

    print()
    print("All pages match the partial. ✓")
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inject the shared header/footer partials and canonical font head block into every page at build time."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--validate",
        action="store_true",
        help="Read-only CI gate: fail if any page's header differs from the partial.",
    )
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Show which pages would be updated without writing any files.",
    )
    args = parser.parse_args()

    print(f"\nPartial source : {HEADER_PARTIAL.relative_to(ROOT)}")
    print(f"Repo root      : {ROOT}")
    print()

    if args.validate:
        return validate()
    return inject(dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
