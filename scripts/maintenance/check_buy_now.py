#!/usr/bin/env python3
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ebook_pipeline import load_master, run_release_checks


def main() -> int:
    errors = [err for err in run_release_checks(load_master()) if "Redirect rule missing" in err or "buy-now" in err]
    if errors:
        for error in errors:
            print(error)
        print(f"Buy-now validation failed with {len(errors)} issue(s).")
        return 1
    print("Buy-now routing check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
