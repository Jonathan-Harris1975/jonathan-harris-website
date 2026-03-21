#!/usr/bin/env python3
from ebook_pipeline import load_master, run_release_checks


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
