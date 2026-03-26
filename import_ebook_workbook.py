#!/usr/bin/env python3
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
from scripts.ebook_pipeline import run_import_command


def main() -> int:
    parser = argparse.ArgumentParser(description="Import the ebook workbook into data/ebooks-master.json")
    parser.add_argument("workbook", help="Path to the workbook file")
    parser.add_argument("--check", action="store_true", help="Validate the workbook structure without writing files")
    return run_import_command(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
