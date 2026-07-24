#!/usr/bin/env python3
"""Validate the age of the latest published blog briefing.

The production website build uses this check in warning-only mode so an
editorial pipeline incident cannot take the whole static site offline. A
separate scheduled GitHub Actions monitor runs the same check strictly and
raises the operational alert when the feed is stale.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "blog" / "posts.json"


def parse_date(value: object) -> dt.datetime | None:
    text = str(value or "").strip().replace("Z", "+00:00")
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = dt.datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-age-days", type=float, default=float(os.environ.get("BLOG_MAX_AGE_DAYS", "8")))
    parser.add_argument(
        "--warn-only",
        action="store_true",
        default=_truthy(os.environ.get("BLOG_FRESHNESS_WARN_ONLY")),
        help="Report stale/missing blog data without failing the caller.",
    )
    args = parser.parse_args()

    if _truthy(os.environ.get("ALLOW_STALE_BLOG_SNAPSHOT")):
        print("Blog freshness gate bypassed for local/offline diagnostics.")
        return 0

    def fail(message: str) -> int:
        prefix = "Blog freshness warning" if args.warn_only else "Blog freshness gate failed"
        print(f"{prefix}: {message}")
        return 0 if args.warn_only else 1

    try:
        payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except Exception as exc:
        return fail(f"cannot read {MANIFEST.relative_to(ROOT)}: {exc}")

    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list) or not items:
        return fail("blog/posts.json contains no published items.")

    dates: list[dt.datetime] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        for key in ("published_at", "datePublished", "pubDate"):
            parsed = parse_date(item.get(key))
            if parsed:
                dates.append(parsed)
                break
    if not dates:
        return fail("no parseable publication date exists in blog/posts.json.")

    newest = max(dates)
    age_days = max(0.0, (dt.datetime.now(dt.timezone.utc) - newest).total_seconds() / 86400.0)
    if age_days > args.max_age_days:
        return fail(
            "newest published briefing is "
            f"{age_days:.1f} days old ({newest.date().isoformat()}); maximum is {args.max_age_days:g} days."
        )

    print(f"Blog freshness gate passed: newest briefing is {age_days:.1f} days old.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
