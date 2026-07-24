#!/usr/bin/env python3
"""Fail governed builds when the published blog snapshot has gone stale."""
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-age-days", type=float, default=float(os.environ.get("BLOG_MAX_AGE_DAYS", "8")))
    args = parser.parse_args()

    if os.environ.get("ALLOW_STALE_BLOG_SNAPSHOT", "").strip().lower() in {"1", "true", "yes"}:
        print("Blog freshness gate bypassed for local/offline diagnostics.")
        return 0

    try:
        payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Blog freshness gate failed: cannot read {MANIFEST.relative_to(ROOT)}: {exc}")
        return 1

    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list) or not items:
        print("Blog freshness gate failed: blog/posts.json contains no published items.")
        return 1

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
        print("Blog freshness gate failed: no parseable publication date exists in blog/posts.json.")
        return 1

    newest = max(dates)
    age_days = max(0.0, (dt.datetime.now(dt.timezone.utc) - newest).total_seconds() / 86400.0)
    if age_days > args.max_age_days:
        print(
            "Blog freshness gate failed: newest published briefing is "
            f"{age_days:.1f} days old ({newest.date().isoformat()}); maximum is {args.max_age_days:g} days."
        )
        return 1

    print(f"Blog freshness gate passed: newest briefing is {age_days:.1f} days old.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
