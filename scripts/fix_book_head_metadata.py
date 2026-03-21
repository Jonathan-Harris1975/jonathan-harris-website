#!/usr/bin/env python3
import argparse
from ebook_pipeline import run_fix_pages_command


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenerate canonical ebook pages and per-book metadata from the master record")
    parser.add_argument("--check", action="store_true", help="Validate page metadata after generation")
    return run_fix_pages_command(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
