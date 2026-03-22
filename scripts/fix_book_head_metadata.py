#!/usr/bin/env python3
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
from scripts.ebook_pipeline import run_fix_pages_command


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenerate canonical ebook pages and per-book metadata from the master record")
    parser.add_argument("--check", action="store_true", help="Validate page metadata after generation")
    return run_fix_pages_command(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
