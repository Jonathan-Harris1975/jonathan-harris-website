#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    required = [ROOT / 'robots.txt', ROOT / 'sitemap.xml', ROOT / 'llms.txt']
    missing = [path.name for path in required if not path.exists()]
    if missing:
        for name in missing:
            print(f"Crawler file missing: {name}")
        return 1
    print("Crawler file check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
