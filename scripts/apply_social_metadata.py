#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IMAGE = "https://images.jonathan-harris.online/site-logo"
IGNORED_DIRS = {
    ".git",
    "artifacts",
    "assets",
    "config",
    "data",
    "docs",
    "functions",
    "node_modules",
    "scripts",
}

TITLE_RE = re.compile(r"<title>([\s\S]*?)</title>", re.I)
DESCRIPTION_RE = re.compile(r'<meta\b[^>]*\bname=["\']description["\'][^>]*>', re.I)
CANONICAL_RE = re.compile(r'<link\b[^>]*\brel=["\']canonical["\'][^>]*>', re.I)
CONTENT_RE = re.compile(r'\bcontent=["\']([^"\']*)["\']', re.I)
HREF_RE = re.compile(r'\bhref=["\']([^"\']*)["\']', re.I)


def public_html_files() -> list[Path]:
    return [
        path
        for path in sorted(ROOT.rglob("*.html"))
        if not any(part in IGNORED_DIRS for part in path.relative_to(ROOT).parts)
    ]


def attr_value(tag: str, pattern: re.Pattern[str]) -> str:
    match = pattern.search(tag)
    return html.unescape(match.group(1)).strip() if match else ""


def page_values(text: str) -> tuple[str, str, str]:
    title_match = TITLE_RE.search(text)
    title = html.unescape(re.sub(r"<[^>]+>", "", title_match.group(1))).strip() if title_match else ""
    desc_match = DESCRIPTION_RE.search(text)
    description = attr_value(desc_match.group(0), CONTENT_RE) if desc_match else ""
    canonical_match = CANONICAL_RE.search(text)
    canonical = attr_value(canonical_match.group(0), HREF_RE) if canonical_match else ""
    return title, description, canonical


def has_meta(text: str, *, name: str | None = None, prop: str | None = None) -> bool:
    if name:
        return bool(re.search(rf'<meta\b[^>]*\bname=["\']{re.escape(name)}["\'][^>]*>', text, re.I))
    if prop:
        return bool(re.search(rf'<meta\b[^>]*\bproperty=["\']{re.escape(prop)}["\'][^>]*>', text, re.I))
    return False


def missing_contract(text: str) -> list[str]:
    missing: list[str] = []
    for prop in ("og:title", "og:description", "og:image"):
        if not has_meta(text, prop=prop):
            missing.append(prop)
    if not has_meta(text, name="twitter:card"):
        missing.append("twitter:card")
    return missing


def apply_to_text(text: str) -> tuple[str, list[str]]:
    missing = missing_contract(text)
    if not missing:
        return text, []

    title, description, canonical = page_values(text)
    if not title or not description or not canonical:
        return text, missing

    values = {
        "title": html.escape(title, quote=True),
        "description": html.escape(description, quote=True),
        "canonical": html.escape(canonical, quote=True),
        "image": DEFAULT_IMAGE,
    }
    tags: list[str] = []
    if not has_meta(text, prop="og:type"):
        tags.append('<meta property="og:type" content="website"/>')
    if not has_meta(text, prop="og:title"):
        tags.append(f'<meta property="og:title" content="{values["title"]}"/>')
    if not has_meta(text, prop="og:description"):
        tags.append(f'<meta property="og:description" content="{values["description"]}"/>')
    if not has_meta(text, prop="og:url"):
        tags.append(f'<meta property="og:url" content="{values["canonical"]}"/>')
    if not has_meta(text, prop="og:image"):
        tags.extend([
            f'<meta property="og:image" content="{values["image"]}"/>',
            '<meta property="og:image:width" content="1200"/>',
            '<meta property="og:image:height" content="630"/>',
        ])
    if not has_meta(text, name="twitter:card"):
        tags.append('<meta name="twitter:card" content="summary_large_image"/>')
    if not has_meta(text, name="twitter:title"):
        tags.append(f'<meta name="twitter:title" content="{values["title"]}"/>')
    if not has_meta(text, name="twitter:description"):
        tags.append(f'<meta name="twitter:description" content="{values["description"]}"/>')
    if not has_meta(text, name="twitter:image"):
        tags.append(f'<meta name="twitter:image" content="{values["image"]}"/>')

    block = "\n<!-- SOCIAL-METADATA START -->\n" + "\n".join(tags) + "\n<!-- SOCIAL-METADATA END -->\n"
    updated, count = re.subn(r"</head>", block + "</head>", text, count=1, flags=re.I)
    if count != 1:
        return text, missing
    return updated, missing


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply or validate the social sharing metadata contract on public HTML pages.")
    parser.add_argument("--validate", action="store_true", help="Report missing tags without changing files.")
    args = parser.parse_args()

    changed = 0
    failures: list[str] = []
    for path in public_html_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        if args.validate:
            missing = missing_contract(text)
            if missing:
                failures.append(f"{path.relative_to(ROOT)}: {', '.join(missing)}")
            continue

        updated, missing = apply_to_text(text)
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            changed += 1
        elif missing:
            failures.append(f"{path.relative_to(ROOT)}: could not apply {', '.join(missing)}")

    if failures:
        for failure in failures:
            print(failure)
        print(f"Social metadata contract failed on {len(failures)} page(s).")
        return 1

    if args.validate:
        print("Social metadata contract passed.")
    else:
        print(f"Social metadata applied to {changed} page(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
