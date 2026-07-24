#!/usr/bin/env python3
"""Refresh verified price/rating signals from a trusted JSON export.

The website deliberately does not scrape or invent Amazon values. Configure
AMAZON_BOOK_SIGNALS_SOURCE to an approved HTTPS JSON feed or local JSON file.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "amazon-book-signals.json"


def load_source(source: str) -> Any:
    if source.startswith(("https://", "http://")):
        attempts = max(1, int(os.environ.get("AMAZON_SIGNALS_RETRY_ATTEMPTS", "4")))
        last: Exception | None = None
        for attempt in range(attempts):
            try:
                req = urllib.request.Request(source, headers={"Accept": "application/json", "User-Agent": "jonathan-harris-site-signals/1"})
                with urllib.request.urlopen(req, timeout=15) as response:
                    return json.load(response)
            except Exception as exc:
                last = exc
                if attempt + 1 < attempts:
                    time.sleep(0.75 * (2 ** attempt))
        raise RuntimeError(f"signal refresh failed after {attempts} attempts: {last}")
    return json.loads(Path(source).expanduser().read_text(encoding="utf-8"))


def normalise(payload: Any) -> dict[str, Any]:
    rows = payload.get("books", payload) if isinstance(payload, dict) else payload
    items = rows.items() if isinstance(rows, dict) else ((str(row.get("asin") or row.get("slug") or ""), row) for row in rows if isinstance(row, dict))
    clean: dict[str, Any] = {}
    for key, raw in items:
        if not isinstance(raw, dict):
            continue
        asin = str(raw.get("asin") or key or "").strip().upper()
        slug = str(raw.get("slug") or "").strip()
        rating = raw.get("rating")
        count = raw.get("rating_count", raw.get("review_count"))
        price = str(raw.get("kindle_price") or raw.get("price") or "").strip()
        source_url = str(raw.get("source_url") or "").strip()
        checked_at = str(raw.get("checked_at") or raw.get("updated_at") or "").strip()
        if rating is not None:
            rating = float(rating)
            if not 1 <= rating <= 5:
                raise ValueError(f"invalid rating for {asin or slug}: {rating}")
        if count is not None:
            count = int(count)
            if count < 0:
                raise ValueError(f"invalid rating count for {asin or slug}: {count}")
        if not (asin or slug) or not source_url or not checked_at:
            continue
        clean[asin or slug] = {
            "asin": asin,
            "slug": slug,
            "rating": rating,
            "rating_count": count,
            "kindle_price": price,
            "currency": str(raw.get("currency") or "").strip(),
            "source_url": source_url,
            "checked_at": checked_at,
        }
    return {"schema_version": 1, "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "books": clean}


def main() -> int:
    source = os.environ.get("AMAZON_BOOK_SIGNALS_SOURCE", "").strip()
    if not source:
        print("Amazon signals refresh skipped: AMAZON_BOOK_SIGNALS_SOURCE is not configured.")
        return 0
    OUT.write_text(json.dumps(normalise(load_source(source)), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Updated {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
