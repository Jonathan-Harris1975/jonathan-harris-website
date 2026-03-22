#!/usr/bin/env python3
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
from scripts.ebook_pipeline import rebuild_all


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the full ebook rebuild: workbook import, page generation, derivative generation, redirects, and validation")
    parser.add_argument("workbook", help="Path to the workbook file")
    args = parser.parse_args()
    workbook_path = Path(args.workbook).expanduser().resolve()
    errors = rebuild_all(workbook_path)
    if errors:
        for error in errors:
            print(error)
        print(f"Rebuild finished with {len(errors)} issue(s).")
        return 1
    print("Ebook subsystem rebuild passed.")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
