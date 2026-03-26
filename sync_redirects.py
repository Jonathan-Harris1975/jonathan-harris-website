#!/usr/bin/env python3
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
from scripts.ebook_pipeline import run_sync_redirects_command


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronise buy-now redirect rules from the master ebook record")
    parser.add_argument("--check", action="store_true", help="Validate the redirect block after synchronising")
    return run_sync_redirects_command(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
