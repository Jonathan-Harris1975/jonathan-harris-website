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
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
PARTIALS_DIR = ROOT / "assets" / "partials"
HEADER_PARTIAL = PARTIALS_DIR / "header.html"

# Directories / files excluded from processing
EXCLUDE_DIRS = {
    PARTIALS_DIR,
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


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def load_partial() -> str:
    """Return the canonical header partial as a string."""
    if not HEADER_PARTIAL.exists():
        raise FileNotFoundError(
            f"Header partial not found: {HEADER_PARTIAL}\n"
            "Expected: assets/partials/header.html"
        )
    return HEADER_PARTIAL.read_text(encoding="utf-8").rstrip("\n")


def collect_pages() -> list[Path]:
    """Return all .html files in the repo, excluding partials and hidden dirs."""
    pages: list[Path] = []
    for path in sorted(ROOT.rglob("*.html")):
        # Skip the partials directory itself
        if any(path.is_relative_to(ex) for ex in EXCLUDE_DIRS):
            continue
        # Skip hidden directories (e.g. .git)
        if any(part.startswith(".") for part in path.relative_to(ROOT).parts):
            continue
        pages.append(path)
    return pages


def find_header_block(text: str) -> re.Match | None:
    """Return the regex match for the header block, or None if not found."""
    return _HEADER_BLOCK_RE.search(text)


# ---------------------------------------------------------------------------
# Inject
# ---------------------------------------------------------------------------

def inject(dry_run: bool = False) -> int:
    """
    Inject the partial into every page.

    Returns 0 on success, 1 if any page could not be processed.
    """
    partial = load_partial()
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

        match = find_header_block(original)
        if match is None:
            failed.append((rel, "Header block not found — no <a class=\"skip-link\"> before <header class=\"jh-header\">"))
            continue

        existing_block = match.group(0)

        if existing_block == partial:
            in_sync += 1
            print(f"  [OK]      {rel}")
            continue

        # Replace only the first occurrence (there should only be one)
        updated_text = original[:match.start()] + partial + original[match.end():]

        if dry_run:
            updated += 1
            print(f"  [DRY-RUN] {rel}  (would update)")
        else:
            try:
                page.write_text(updated_text, encoding="utf-8")
                updated += 1
                print(f"  [UPDATED] {rel}")
            except Exception as exc:
                failed.append((rel, f"Write error: {exc}"))

    # Summary
    print()
    print("=" * 60)
    print("inject_partials  —  Header injection summary")
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
    partial = load_partial()
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

        match = find_header_block(text)
        if match is None:
            drift.append((rel, "Header block not located"))
            continue

        if match.group(0) == partial:
            ok += 1
        else:
            drift.append((rel, "Header differs from partial"))

    print()
    print("=" * 60)
    print("inject_partials  —  Header validation")
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
        description="Inject assets/partials/header.html into every page at build time."
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
