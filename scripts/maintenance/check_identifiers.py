#!/usr/bin/env python3
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ebook_pipeline import load_master


def main() -> int:
    books = load_master()
    errors = []
    for key in ('slug', 'asin', 'identifier'):
        values = [book.get(key) for book in books if book.get(key)]
        if len(values) != len(set(values)):
            errors.append(f"Duplicate {key} values found.")
    if errors:
        for error in errors:
            print(error)
        return 1
    print("Identifier uniqueness check passed.")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
