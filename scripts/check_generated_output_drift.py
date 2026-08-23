#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Private/transient build inputs and deployment-only artefacts are intentionally
# absent from Git. They must never make a canonical build fail the cleanliness
# gate.
IGNORED_PREFIXES = (
    "artifacts/",
    "assets/site-shell/",
    "data/book-sample-chapters.json",
    "release.json",
    "scripts/__pycache__/",
    "scripts/data/manuscripts.json",
)

# Manuscript samples are produced from private Drive PDFs during the build. The
# source URLs and extracted text cache are intentionally not committed, so the
# public sample routes and the discovery files that reference those routes are
# legitimate build-time output. These files are exempted only when the same
# build has actually generated at least one sample route.
SAMPLE_DERIVED_SHARED_FILES = frozenset(
    {
        "config/crawler-checksums.json",
        "config/crawler-snapshots/sitemap.xml",
        "data/dynamic-route-manifest.json",
        "data/search-visibility-surfaces.json",
        "ebooks/url-manifest.json",
        "sitemap.xml",
    }
)
SAMPLE_ROUTE_RE = re.compile(r"^ebooks/(?P<slug>[^/]+)/sample/index\.html$")
BOOK_ROUTE_RE = re.compile(r"^ebooks/(?P<slug>[^/]+)/index\.html$")


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def status_path(raw_line: str) -> str:
    """Return the path portion of one porcelain-v1 status line."""
    path_text = raw_line[3:].strip()
    if " -> " in path_text:
        path_text = path_text.split(" -> ", 1)[1]
    return path_text.strip('"')


def generated_sample_slugs(status_lines: list[str]) -> set[str]:
    slugs: set[str] = set()
    for raw_line in status_lines:
        if not raw_line.strip():
            continue
        match = SAMPLE_ROUTE_RE.fullmatch(status_path(raw_line))
        if match:
            slugs.add(match.group("slug"))
    return slugs


def is_ignored_build_output(path_text: str, sample_slugs: set[str]) -> bool:
    if any(
        path_text == prefix.rstrip("/") or path_text.startswith(prefix)
        for prefix in IGNORED_PREFIXES
    ):
        return True

    sample_match = SAMPLE_ROUTE_RE.fullmatch(path_text)
    if sample_match and sample_match.group("slug") in sample_slugs:
        return True

    # A canonical book page changes only for books whose genuine sample route
    # was generated in this build (sample CTA, confidence marker and section).
    book_match = BOOK_ROUTE_RE.fullmatch(path_text)
    if book_match and book_match.group("slug") in sample_slugs:
        return True

    if sample_slugs and path_text in SAMPLE_DERIVED_SHARED_FILES:
        return True

    return False


def main() -> int:
    inside = git("rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        print("Generated-output drift check skipped: build is not running in a Git worktree.")
        return 0

    status = git("status", "--porcelain=v1", "--untracked-files=all")
    if status.returncode != 0:
        print(status.stderr.strip() or "Could not inspect Git working-tree status.")
        return 1

    status_lines = [line for line in status.stdout.splitlines() if line.strip()]
    sample_slugs = generated_sample_slugs(status_lines)

    unexpected: list[str] = []
    for raw_line in status_lines:
        path_text = status_path(raw_line)
        if is_ignored_build_output(path_text, sample_slugs):
            continue
        unexpected.append(raw_line)

    if unexpected:
        print("Generated-output drift detected after the canonical build:")
        for line in unexpected:
            print(f"  {line}")
        print("Run the build locally, commit the regenerated files, and rerun CI.")
        return 1

    if sample_slugs:
        print(
            "Generated-output drift check passed: "
            f"{len(sample_slugs)} manuscript sample route(s) were treated as governed build-time output."
        )
    else:
        print("Generated-output drift check passed: the canonical build left the Git worktree clean.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
