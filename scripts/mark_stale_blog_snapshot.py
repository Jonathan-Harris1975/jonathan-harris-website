#!/usr/bin/env python3
"""Mark the checked-in blog fallback as an archive snapshot when it is stale.

The runtime blog feed may be fresher than the repository snapshot. This script keeps
no-JS/crawler fallback copy honest without deleting the saved article.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POSTS = ROOT / "blog" / "posts.json"
INDEX = ROOT / "blog" / "index.html"
MAX_AGE_DAYS = 14
START = "<!-- BLOG-SNAPSHOT-STATUS START -->"
END = "<!-- BLOG-SNAPSHOT-STATUS END -->"


def parse_timestamp(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def replace_marker(text: str, block: str) -> str:
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    if pattern.search(text):
        return pattern.sub(block, text, count=1)
    anchor = '<p class="subtle" id="blogStatus" aria-live="polite">'
    pos = text.find(anchor)
    if pos >= 0:
        return text[:pos] + block + "\n" + text[pos:]
    return text.replace("</section>", block + "\n</section>", 1)


def main() -> int:
    if not POSTS.exists() or not INDEX.exists():
        print("Blog snapshot marker skipped: required blog files are missing.")
        return 0

    data = json.loads(POSTS.read_text(encoding="utf-8"))
    updated = parse_timestamp(str(data.get("updated_at", "")))
    items = data.get("items") if isinstance(data.get("items"), list) else []
    if updated is None and items:
        updated = parse_timestamp(str(items[0].get("published_at", "")))

    html = INDEX.read_text(encoding="utf-8")
    now = datetime.now(timezone.utc)
    stale = updated is not None and (now - updated).days > MAX_AGE_DAYS

    if stale:
        label = updated.strftime("%d %B %Y")
        block = (
            f'{START}<aside class="card blog-snapshot-notice" role="note" aria-label="Blog archive snapshot">'
            f'<strong>Archive snapshot:</strong> this checked-in fallback was last refreshed on {label}. '
            'The live publication feed may contain newer AI Edge analysis. '
            '<a href="/blog/weekly/">Browse the weekly archive</a>.'
            f'</aside>{END}'
        )
        # The server/client feed can replace this state at runtime; the source fallback must not claim freshness.
        html = re.sub(
            r'(<p class="subtle" id="blogStatus" aria-live="polite">).*?(</p>)',
            rf'\1Saved archive snapshot from {label}; checking the live publication feed for anything newer.\2',
            html,
            count=1,
            flags=re.S,
        )
    else:
        block = f"{START}{END}"

    html = replace_marker(html, block)
    INDEX.write_text(html, encoding="utf-8")
    print("Blog fallback marked as stale archive snapshot." if stale else "Blog fallback is within freshness threshold.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
